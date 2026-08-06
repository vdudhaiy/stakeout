/**
 * Client-only portfolio engine for guest mode.
 *
 * Guests never get a row in the `holdings`/`transactions` tables — everything
 * here lives in sessionStorage (cleared when the tab closes, survives
 * reloads) and mirrors portfolio_service.py's FIFO cost-basis logic exactly,
 * so a guest sees the same math a signed-in account would.
 */
import type { BuyLot, Market, PortfolioResponse, SellLot, StockHolding, StockPurchaseHistory } from '../types'

// Guests get exactly one implicit portfolio per market — creating more needs
// an account. This id tags every guest holding so the shared UI (which filters
// holdings by portfolio) works unchanged; the tab bar hides itself when there
// is only one portfolio, so guests never see it.
export const GUEST_PORTFOLIO_ID = 0
import { marketOf, type Exchange } from '../utils/market'
import { resolveTickerName, resolveGuestTicker, fetchGuestPrice } from './guestApi'
import * as guestWatchlist from './guestWatchlist'

interface GuestTxn {
  id: number
  sale: boolean
  date: string
  shares: number
  boughtAt: number
  soldAt: number
  sharesRemaining: number
}

interface GuestHoldingState {
  ticker: string
  market: Market
  companyName: string
  shares: number
  soldShares: number
  averageCost: number
  transactions: GuestTxn[]
}

type GuestPortfolioState = Record<string, GuestHoldingState>

const STORAGE_KEY = 'stakeout-guest-portfolio'

function loadState(): GuestPortfolioState {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as GuestPortfolioState) : {}
  } catch {
    return {}
  }
}

function saveState(state: GuestPortfolioState): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function clearGuestPortfolio(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}

function nextIdFor(state: GuestPortfolioState): number {
  let max = 0
  for (const h of Object.values(state)) for (const t of h.transactions) max = Math.max(max, t.id)
  return max + 1
}

function resolveDate(date?: string): string {
  const today = new Date().toISOString().slice(0, 10)
  if (!date) return today
  if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) throw new Error(`Invalid date '${date}'. Expected yyyy-mm-dd.`)
  if (date > today) throw new Error('Transaction date cannot be in the future.')
  return date
}

/** Ports portfolio_service._replay_fifo: resets buy lots, replays sells in FIFO
 * order, and recalculates each sell's cost basis + the holding's aggregates. */
function replayFifo(holding: GuestHoldingState, transactions: GuestTxn[]): void {
  const buys = transactions.filter(t => !t.sale)
  const sells = transactions.filter(t => t.sale)

  for (const t of buys) t.sharesRemaining = t.shares

  for (const sell of sells) {
    let remaining = sell.shares
    let fifoCost = 0
    for (const lot of buys) {
      if (remaining <= 0) break
      if (lot.date > sell.date) break
      const consumed = Math.min(lot.sharesRemaining, remaining)
      fifoCost += consumed * lot.boughtAt
      lot.sharesRemaining -= consumed
      remaining -= consumed
    }
    if (remaining > 0) {
      throw new Error(
        `Only ${sell.shares - remaining} share(s) were available on or before ${sell.date} — cannot sell ${sell.shares}.`
      )
    }
    sell.boughtAt = fifoCost / sell.shares
  }

  holding.transactions = transactions
  holding.shares = buys.reduce((s, t) => s + t.sharesRemaining, 0)
  holding.soldShares = sells.reduce((s, t) => s + t.shares, 0)
  const totalShares = buys.reduce((s, t) => s + t.shares, 0)
  const totalCost = buys.reduce((s, t) => s + t.shares * t.boughtAt, 0)
  holding.averageCost = totalShares > 0 ? totalCost / totalShares : 0
}

function realizedGains(transactions: GuestTxn[]): number {
  return transactions.filter(t => t.sale).reduce((s, t) => s + (t.soldAt - t.boughtAt) * t.shares, 0)
}

function buildStockHolding(holding: GuestHoldingState, price: number | null): StockHolding {
  const costBasis = holding.transactions
    .filter(t => !t.sale)
    .reduce((s, t) => s + t.sharesRemaining * t.boughtAt, 0)
  const totalEarned = realizedGains(holding.transactions)
  // price is null when the quote fetch failed — propagate that as "unavailable"
  // rather than treating it as $0 (which would render as a fabricated -100% loss).
  const stockValue = price == null ? null : holding.shares * price
  const profitLoss = stockValue == null ? null : stockValue - costBasis
  const profitLossPercentage = profitLoss == null ? null : (costBasis > 0 ? (profitLoss / costBasis) * 100 : 0)

  const tradeHistory: StockPurchaseHistory[] = holding.transactions.map(t => ({
    id: t.id, sale: t.sale, ticker: holding.ticker, date: t.date,
    shares: t.shares, bought_at: t.boughtAt, sold_at: t.soldAt, shares_remaining: t.sharesRemaining,
  }))

  return {
    ticker: holding.ticker,
    portfolio_id: GUEST_PORTFOLIO_ID,
    market: holding.market,
    currency: holding.market === 'IN' ? 'INR' : 'USD',
    company_name: holding.companyName,
    shares: holding.shares,
    sold_shares: holding.soldShares,
    average_cost: holding.averageCost,
    current_price: price,
    stock_value: stockValue,
    total_invested: costBasis,
    total_earned: totalEarned,
    total_dividends: 0,   // dividend tracking requires an account — not available in guest mode
    profit_loss: profitLoss,
    profit_loss_percentage: profitLossPercentage,
    trade_history: tradeHistory,
    dividends: [],
  }
}

async function getHolding(ticker: string): Promise<StockHolding> {
  const state = loadState()
  const holding = state[ticker]
  if (!holding) throw new Error(`No holding found for ticker: ${ticker}`)
  const price = await fetchGuestPrice(ticker)
  return buildStockHolding(holding, price)
}

export async function getStockHolding(ticker: string): Promise<StockHolding> {
  return getHolding(ticker.toUpperCase())
}

export async function buy(ticker: string, shares: number, boughtAt: number, date?: string, exchange?: Exchange): Promise<StockHolding> {
  const state = loadState()
  ticker = await resolveGuestTicker(ticker, exchange, t => !!state[t])
  const txnDate = resolveDate(date)
  let holding = state[ticker]
  if (!holding) {
    const companyName = await resolveTickerName(ticker)
    holding = { ticker, market: marketOf(ticker), companyName, shares: 0, soldShares: 0, averageCost: 0, transactions: [] }
    state[ticker] = holding
    // A newly-bought ticker should show up on the tracker too, not just the portfolio.
    await guestWatchlist.addTicker(ticker)
  }
  const newTxn: GuestTxn = {
    id: nextIdFor(state), sale: false, date: txnDate, shares, boughtAt, soldAt: 0, sharesRemaining: shares,
  }
  const allTxns = [...holding.transactions, newTxn].sort((a, b) => a.date.localeCompare(b.date))
  replayFifo(holding, allTxns)
  saveState(state)
  return getHolding(ticker)
}

/** Records several buy lots (backfilled purchase history) as one atomic write —
 * mirrors portfolio_service.add_stock_purchases_bulk's single-replay semantics. */
export async function buyBulk(ticker: string, lots: BuyLot[], exchange?: Exchange): Promise<StockHolding> {
  if (lots.length === 0) throw new Error('At least one purchase is required.')
  // Resolve every date up front so a bad row anywhere in the batch fails
  // before anything is written.
  const resolvedDates = lots.map(l => resolveDate(l.date))

  const state = loadState()
  ticker = await resolveGuestTicker(ticker, exchange, t => !!state[t])
  let holding = state[ticker]
  if (!holding) {
    const companyName = await resolveTickerName(ticker)
    holding = { ticker, market: marketOf(ticker), companyName, shares: 0, soldShares: 0, averageCost: 0, transactions: [] }
    state[ticker] = holding
    // A newly-bought ticker should show up on the tracker too, not just the portfolio.
    await guestWatchlist.addTicker(ticker)
  }
  const firstId = nextIdFor(state)
  const newTxns: GuestTxn[] = lots.map((lot, i) => ({
    id: firstId + i, sale: false, date: resolvedDates[i], shares: lot.shares, boughtAt: lot.bought_at, soldAt: 0, sharesRemaining: lot.shares,
  }))
  const allTxns = [...holding.transactions, ...newTxns].sort((a, b) => a.date.localeCompare(b.date))
  replayFifo(holding, allTxns)
  saveState(state)
  return getHolding(ticker)
}

/** Records several sell lots (different dates/prices) as one atomic write —
 * mirrors portfolio_service.sell_stock_shares_bulk's single-replay semantics. */
export async function sellBulk(ticker: string, lots: SellLot[]): Promise<StockHolding> {
  ticker = ticker.toUpperCase()
  if (lots.length === 0) throw new Error('At least one sale is required.')
  const resolvedDates = lots.map(l => resolveDate(l.date))

  const state = loadState()
  const holding = state[ticker]
  if (!holding) throw new Error(`No holding found for ticker: ${ticker}`)

  const earliestBuy = holding.transactions.filter(t => !t.sale).map(t => t.date).sort()[0]
  for (const d of resolvedDates) {
    if (earliestBuy && d < earliestBuy) {
      throw new Error(`Sale date ${d} is before the earliest purchase on ${earliestBuy}.`)
    }
  }

  const firstId = nextIdFor(state)
  const newTxns: GuestTxn[] = lots.map((lot, i) => ({
    id: firstId + i, sale: true, date: resolvedDates[i], shares: lot.shares, boughtAt: 0, soldAt: lot.sold_at, sharesRemaining: 0,
  }))
  const allTxns = [...holding.transactions, ...newTxns].sort((a, b) => a.date.localeCompare(b.date))
  replayFifo(holding, allTxns)
  saveState(state)
  return getHolding(ticker)
}

export async function deleteTransactionGuest(ticker: string, transactionId: number): Promise<StockHolding | null> {
  ticker = ticker.toUpperCase()
  const state = loadState()
  const holding = state[ticker]
  if (!holding) throw new Error(`No holding found for ticker: ${ticker}`)
  if (!holding.transactions.some(t => t.id === transactionId)) {
    throw new Error(`Transaction ${transactionId} not found for ${ticker}.`)
  }
  const remaining = holding.transactions.filter(t => t.id !== transactionId)
  if (remaining.length === 0) {
    delete state[ticker]
    saveState(state)
    return null
  }
  replayFifo(holding, remaining)
  saveState(state)
  return getHolding(ticker)
}

export async function deleteHolding(ticker: string): Promise<{ message: string }> {
  ticker = ticker.toUpperCase()
  const state = loadState()
  if (!state[ticker]) throw new Error(`No holding found for ticker: ${ticker}`)
  delete state[ticker]
  saveState(state)
  return { message: `Holding for ${ticker} deleted successfully.` }
}

export async function getPortfolio(market?: Market): Promise<PortfolioResponse> {
  const state = loadState()
  let holdings = Object.values(state)
  if (market) holdings = holdings.filter(h => h.market === market)

  const prices = await Promise.all(holdings.map(h => fetchGuestPrice(h.ticker)))
  const built = holdings.map((h, i) => buildStockHolding(h, prices[i]))

  // Holdings with no live quote are excluded from portfolio_value rather than
  // counted as worth $0 — see buildStockHolding.
  const portfolioValue = built.reduce((s, h) => s + (h.stock_value ?? 0), 0)
  const realizedG = built.reduce((s, h) => s + h.total_earned, 0)
  const totalShares = built.reduce((s, h) => s + h.shares, 0)
  const totalInvested = built.reduce((s, h) => s + h.total_invested, 0)
  const totalReturn = portfolioValue - totalInvested
  const returnPct = totalInvested > 0 ? (totalReturn / totalInvested) * 100 : 0
  const netProfitLoss = totalReturn + realizedG

  const currency = market === 'IN' ? 'INR' : 'USD'
  return {
    market: market ?? null,
    currency,
    portfolio_value: portfolioValue,
    realized_gains: realizedG,
    total_shares: totalShares,
    total_invested: totalInvested,
    total_return: totalReturn,
    return_percentage: returnPct,
    total_dividends: 0,
    net_profit_loss: netProfitLoss,
    holdings: built,
    // A single entry, so the tab bar stays hidden and no combined bar renders
    // — but the shape matches a signed-in response, so the page needs no
    // guest-specific branch to read it.
    portfolios: [{
      id: GUEST_PORTFOLIO_ID,
      name: 'main',
      market: market ?? 'US',
      currency,
      portfolio_value: portfolioValue,
      realized_gains: realizedG,
      total_shares: totalShares,
      total_invested: totalInvested,
      total_return: totalReturn,
      return_percentage: returnPct,
      total_dividends: 0,
      net_profit_loss: netProfitLoss,
    }],
  }
}
