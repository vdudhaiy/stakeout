import type { OHLCVResponse, StockDetails, GroupedStocks, WatchlistMap, EPSHistoryResponse, RevenueHistoryResponse, StockDashboardResponse, PortfolioResponse, StockHolding, DividendEntry, IndicatorsResponse, NewsResponse, StockNewsResponse, Market, IndicesResponse, ClassificationMap, TickerSuggestion, StockExplanationResponse, ChatMessage, ChatContext, ChatResponse, BuyLot, SellLot } from '../types'
import { applyExchange, type Exchange } from '../utils/market'
import * as guestPortfolio from '../lib/guestPortfolio'
import * as guestWatchlist from '../lib/guestWatchlist'
import { isGuestModeActive } from '../lib/guestMode'

// ── Transport ─────────────────────────────────────────────────────────────
// In dev, VITE_API_URL is empty and Vite proxies API paths to localhost:8000.
// In production (Vercel) it points at the Render service.
const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '')

// AuthContext registers a getter for the current Supabase access token so
// this module stays framework-free. Before sign-in (or in guest mode) it
// returns null and no Authorization header is sent.
let getAuthToken: () => Promise<string | null> = async () => null
export function setAuthTokenGetter(fn: () => Promise<string | null>) { getAuthToken = fn }

// When guest mode is active, watchlist/portfolio calls below are redirected
// to the local (sessionStorage-backed) engines instead of hitting the
// DB-backed API — guest data is never written to the database.
const isGuestMode = isGuestModeActive

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await getAuthToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}


export async function fetchAllStocks(): Promise<WatchlistMap> {
  if (isGuestMode()) return guestWatchlist.getWatchlist()
  const res = await apiFetch('/watchlist/')
  if (!res.ok) throw new Error('Failed to fetch watchlist')
  const data = await res.json()
  return (data.stocks as WatchlistMap) ?? {}
}

export async function fetchStockDetails(ticker: string): Promise<StockDetails> {
  const res = await apiFetch(`/stocks/${ticker}/details`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load details for ${ticker}`)
  }
  return res.json()
}

export async function fetchStock(ticker: string, days: number): Promise<OHLCVResponse> {
  const res = await apiFetch(`/stocks/${ticker}?days=${days}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load ${ticker}`)
  }
  return res.json()
}

export async function fetchIndustryMap(): Promise<GroupedStocks> {
  const res = await apiFetch('/stocks/industries')
  if (!res.ok) throw new Error('Failed to fetch industry map')
  const data = await res.json()
  return data.industries as GroupedStocks
}

export async function fetchSectorMap(): Promise<GroupedStocks> {
  const res = await apiFetch('/stocks/sectors')
  if (!res.ok) throw new Error('Failed to fetch sector map')
  const data = await res.json()
  return data.sectors as GroupedStocks
}

export async function fetchCurrentStock(ticker: string): Promise<OHLCVResponse> {
  const res = await apiFetch(`/stocks/${ticker}/current`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load current data for ${ticker}`)
  }
  return res.json()
}

export async function fetchIntradayStock(ticker: string): Promise<OHLCVResponse> {
  const res = await apiFetch(`/stocks/${ticker}/intraday`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load intraday data for ${ticker}`)
  }
  return res.json()
}

export async function addStock(ticker: string, exchange?: Exchange): Promise<{ exist: boolean; stocks: WatchlistMap }> {
  if (isGuestMode()) return guestWatchlist.addTicker(exchange ? applyExchange(ticker, exchange) : ticker)
  const qs = exchange ? `?exchange=${exchange}` : ''
  const res = await apiFetch(`/watchlist/${encodeURIComponent(ticker)}${qs}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to add ${ticker}`)
  }
  return res.json()
}

export async function deleteStock(ticker: string): Promise<void> {
  if (isGuestMode()) return guestWatchlist.removeTicker(ticker)
  const res = await apiFetch(`/watchlist/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to remove ${ticker}`)
  }
}

export async function fetchEpsHistory(ticker: string): Promise<EPSHistoryResponse> {
  const res = await apiFetch(`/stocks/${ticker}/eps`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load EPS history for ${ticker}`)
  }
  return res.json()
}

export async function fetchRevenueHistory(ticker: string): Promise<RevenueHistoryResponse> {
  const res = await apiFetch(`/stocks/${ticker}/revenue`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load revenue history for ${ticker}`)
  }
  return res.json()
}

export async function fetchStockDashboard(ticker: string, days: number): Promise<StockDashboardResponse> {
  const res = await apiFetch(`/stocks/${ticker}/dashboard?days=${days}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load tracker data for ${ticker}`)
  }
  return res.json()
}

export async function fetchPortfolio(market?: 'US' | 'IN'): Promise<PortfolioResponse> {
  if (isGuestMode()) return guestPortfolio.getPortfolio(market as Market | undefined)
  const res = await apiFetch(`/portfolio/${market ? `?market=${market}` : ''}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load portfolio')
  }
  return res.json()
}

export async function logBuy(ticker: string, shares: number, bought_at: number, date: string, exchange?: Exchange): Promise<StockHolding> {
  if (isGuestMode()) return guestPortfolio.buy(exchange ? applyExchange(ticker, exchange) : ticker, shares, bought_at, date)
  const exchangeQs = exchange ? `&exchange=${exchange}` : ''
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/buy?shares=${shares}&bought_at=${bought_at}&date=${date}${exchangeQs}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record purchase of ${ticker}`)
  }
  return res.json()
}

export async function logBuyBulk(ticker: string, lots: BuyLot[], exchange?: Exchange): Promise<StockHolding> {
  if (isGuestMode()) return guestPortfolio.buyBulk(exchange ? applyExchange(ticker, exchange) : ticker, lots)
  const exchangeQs = exchange ? `?exchange=${exchange}` : ''
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/buy/bulk${exchangeQs}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(lots.map(l => ({ shares: l.shares, bought_at: l.bought_at, date: l.date }))),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record purchases of ${ticker}`)
  }
  return res.json()
}

export async function logSellBulk(ticker: string, lots: SellLot[]): Promise<StockHolding> {
  if (isGuestMode()) return guestPortfolio.sellBulk(ticker, lots)
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/sell/bulk`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(lots.map(l => ({ shares: l.shares, sold_at: l.sold_at, date: l.date }))),
    },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record sales of ${ticker}`)
  }
  return res.json()
}

export async function deleteTransaction(ticker: string, transactionId: number): Promise<void> {
  if (isGuestMode()) { await guestPortfolio.deleteTransactionGuest(ticker, transactionId); return }
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/transactions/${transactionId}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to delete transaction')
  }
}

// ── Dividends ─────────────────────────────────────────────────────────────
// Not available in guest mode — dividend history is stored server-side per
// holding, and guest positions never get a DB row to attach it to.

export async function fetchDividends(ticker: string): Promise<DividendEntry[]> {
  if (isGuestMode()) return []
  const res = await apiFetch(`/portfolio/${encodeURIComponent(ticker)}/dividends`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load dividends for ${ticker}`)
  }
  return res.json()
}

export async function syncDividends(ticker: string): Promise<DividendEntry[]> {
  if (isGuestMode()) throw new Error('Sign in to sync dividends.')
  const res = await apiFetch(`/portfolio/${encodeURIComponent(ticker)}/dividends/sync`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to sync dividends for ${ticker}`)
  }
  return res.json()
}

export async function addDividend(
  ticker: string, date: string, amountPerShare: number, sharesHeld?: number,
): Promise<DividendEntry> {
  if (isGuestMode()) throw new Error('Sign in to track dividends.')
  const sharesQs = sharesHeld != null ? `&shares_held=${sharesHeld}` : ''
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/dividends?date=${date}&amount_per_share=${amountPerShare}${sharesQs}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to add dividend for ${ticker}`)
  }
  return res.json()
}

export async function updateDividend(
  ticker: string, dividendId: number,
  fields: { date?: string; amountPerShare?: number; sharesHeld?: number },
): Promise<DividendEntry> {
  if (isGuestMode()) throw new Error('Sign in to track dividends.')
  const params = new URLSearchParams()
  if (fields.date != null) params.set('date', fields.date)
  if (fields.amountPerShare != null) params.set('amount_per_share', String(fields.amountPerShare))
  if (fields.sharesHeld != null) params.set('shares_held', String(fields.sharesHeld))
  const res = await apiFetch(
    `/portfolio/${encodeURIComponent(ticker)}/dividends/${dividendId}?${params.toString()}`,
    { method: 'PUT' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to update dividend')
  }
  return res.json()
}

export async function deleteDividend(ticker: string, dividendId: number): Promise<void> {
  if (isGuestMode()) throw new Error('Sign in to track dividends.')
  const res = await apiFetch(`/portfolio/${encodeURIComponent(ticker)}/dividends/${dividendId}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to delete dividend')
  }
}

export async function downloadPortfolio(market?: 'US' | 'IN'): Promise<void> {
  if (isGuestMode()) throw new Error('Sign in to export your portfolio.')
  const res = await apiFetch(`/portfolio/download${market ? `?market=${market}` : ''}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to download portfolio')
  }
  const blob = await res.blob()
  const suggestedName = `portfolio-${new Date().toISOString().split('T')[0]}.xlsx`

  // File System Access API: shows a native "Save As" dialog (Chrome/Edge)
  if ('showSaveFilePicker' in window) {
    try {
      const handle = await (window as typeof window & { showSaveFilePicker: Function }).showSaveFilePicker({
        suggestedName,
        types: [{
          description: 'Excel Workbook',
          accept: { 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': ['.xlsx'] },
        }],
      })
      const writable = await handle.createWritable()
      await writable.write(blob)
      await writable.close()
      return
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') return  // user cancelled — do nothing
      // Any other error: fall through to legacy download below
    }
  }

  // Fallback for browsers without File System Access API (Firefox, Safari)
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = suggestedName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export async function deletePortfolioHolding(ticker: string): Promise<void> {
  if (isGuestMode()) { await guestPortfolio.deleteHolding(ticker); return }
  const res = await apiFetch(`/portfolio/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to remove ${ticker}`)
  }
}

export async function deleteAccount(): Promise<void> {
  const res = await apiFetch('/account', { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to delete account')
  }
}

export async function fetchIndicators(ticker: string, days: number): Promise<IndicatorsResponse> {
  const res = await apiFetch(`/indicators/${ticker}?days=${days}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load indicators for ${ticker}`)
  }
  return res.json()
}

export async function fetchMarketStatus(market: 'US' | 'IN' = 'US'): Promise<boolean | null> {
  try {
    const res = await apiFetch(`/stocks/market?market=${market}`)
    if (!res.ok) return null
    const data = await res.json()
    return data.status as boolean
  } catch {
    return null
  }
}

// ── News ──────────────────────────────────────────────────────────────────

export async function fetchMarketNews(region: 'all' | 'us' | 'in' = 'all', limit = 12): Promise<NewsResponse> {
  const res = await apiFetch(`/news/market?region=${region}&limit=${limit}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load market news')
  }
  return res.json()
}

export async function fetchStockNews(ticker: string, limit = 10): Promise<StockNewsResponse> {
  const res = await apiFetch(`/news/stock/${encodeURIComponent(ticker)}?limit=${limit}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load news for ${ticker}`)
  }
  return res.json()
}

// ── Market indices & classification ───────────────────────────────────────

export async function fetchIndices(): Promise<IndicesResponse> {
  const res = await apiFetch('/stocks/indices')
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load market indices')
  }
  return res.json()
}

/**
 * Ticker/company-name autocomplete, scoped to `exchange` ("US" | "NSE" | "BSE").
 * Indian results come back with their .NS/.BO suffix already stripped — the
 * exchange picker in the UI is what applies it, not this list. Best-effort:
 * fails silently to an empty list rather than throwing, since it only
 * powers suggestions and shouldn't block manual ticker entry.
 */
export async function searchTickers(query: string, exchange: 'US' | 'NSE' | 'BSE'): Promise<TickerSuggestion[]> {
  if (!query.trim()) return []
  try {
    const res = await apiFetch(`/stocks/search?q=${encodeURIComponent(query)}&exchange=${exchange}`)
    if (!res.ok) return []
    const data = await res.json()
    return (data.results as TickerSuggestion[]) ?? []
  } catch {
    return []
  }
}

/** Sector/industry classification for a batch of tickers (24h-cached server-side). */
export async function fetchClassification(tickers: string[]): Promise<ClassificationMap> {
  if (tickers.length === 0) return {}
  const qs = encodeURIComponent(tickers.join(','))
  const res = await apiFetch(`/stocks/classification?tickers=${qs}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load sector/industry data')
  }
  const data = await res.json()
  return (data.classification as ClassificationMap) ?? {}
}

// ── AI Explanation Layer ──────────────────────────────────────────────────
// Backed by a locally-run Ollama model — both calls can 503 if it isn't
// running, which callers should render as an inline "unavailable" state
// rather than a hard error.

export async function fetchStockExplanation(ticker: string, refresh = false): Promise<StockExplanationResponse> {
  const res = await apiFetch(`/ai/stocks/${ticker}/explain${refresh ? '?refresh=true' : ''}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load AI insight for ${ticker}`)
  }
  return res.json()
}

export async function sendChatMessage(message: string, context: ChatContext, history: ChatMessage[]): Promise<ChatResponse> {
  const res = await apiFetch('/ai/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, context, history }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to reach the AI assistant')
  }
  return res.json()
}
