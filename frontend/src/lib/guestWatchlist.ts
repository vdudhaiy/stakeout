/**
 * Client-only watchlist for guest mode — sessionStorage instead of the
 * per-user `watchlist` table. Seeded once with a handful of default
 * tickers, so a new guest sees something on first load rather than a
 * blank dashboard.
 */
import type { WatchlistMap } from '../types'
import { marketOf } from '../utils/market'
import { resolveTickerName } from './guestApi'

const STORAGE_KEY = 'stakeout-guest-watchlist'
const DEFAULT_TICKERS = ['AAPL', 'MSFT', 'NVDA', 'RELIANCE.NS', 'TCS.NS']

function loadState(): WatchlistMap {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY)
    return raw ? (JSON.parse(raw) as WatchlistMap) : {}
  } catch {
    return {}
  }
}

function saveState(state: WatchlistMap): void {
  sessionStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function clearGuestWatchlist(): void {
  sessionStorage.removeItem(STORAGE_KEY)
}

export async function getWatchlist(): Promise<WatchlistMap> {
  const neverInitialized = sessionStorage.getItem(STORAGE_KEY) === null
  const state = loadState()
  if (!neverInitialized) return state

  // First call this session — seed with a small set of default tickers so a
  // new guest sees something rather than a blank dashboard. Resolved in
  // parallel: each is an independent archive lookup, and doing 5 tickers
  // sequentially would noticeably delay a guest's first load.
  const resolved = await Promise.allSettled(DEFAULT_TICKERS.map(resolveTickerName))
  resolved.forEach((result, i) => {
    if (result.status === 'fulfilled') {
      const ticker = DEFAULT_TICKERS[i]
      state[ticker] = { name: result.value, market: marketOf(ticker) }
    }
    // rejected — archive unavailable for this ticker, skip seeding it, not fatal.
  })
  saveState(state)
  return state
}

export async function addTicker(ticker: string): Promise<{ exist: boolean; stocks: WatchlistMap }> {
  ticker = ticker.toUpperCase().trim()
  const state = loadState()
  if (state[ticker]) return { exist: true, stocks: state }
  const name = await resolveTickerName(ticker)
  state[ticker] = { name, market: marketOf(ticker) }
  saveState(state)
  return { exist: false, stocks: state }
}

export async function removeTicker(ticker: string): Promise<void> {
  ticker = ticker.toUpperCase().trim()
  const state = loadState()
  delete state[ticker]
  saveState(state)
}
