import type { OHLCVResponse, HealthInfo, StockDetails, GroupedStocks, WatchlistMap, EPSHistoryResponse, RevenueHistoryResponse, StockDashboardResponse, PortfolioResponse, StockHolding, IndicatorsResponse, NewsResponse, StockNewsResponse, FxRate } from '../types'

// ── Transport ─────────────────────────────────────────────────────────────
// In dev, VITE_API_URL is empty and Vite proxies API paths to localhost:8000.
// In production (Vercel) it points at the Render service.
const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '')

// AuthContext registers a getter for the current Supabase access token so
// this module stays framework-free. In local mode it returns null and no
// Authorization header is sent.
let getAuthToken: () => Promise<string | null> = async () => null
export function setAuthTokenGetter(fn: () => Promise<string | null>) { getAuthToken = fn }

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await getAuthToken()
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  return fetch(`${API_BASE}${path}`, { ...init, headers })
}


export async function fetchHealth(): Promise<HealthInfo> {
  const start = Date.now()
  try {
    const res = await apiFetch('/health')
    const latencyMs = Date.now() - start
    if (!res.ok) return { status: 'error', latencyMs }
    const data = await res.json()
    return { status: data.status === 'ok' ? 'ok' : 'error', latencyMs }
  } catch {
    return { status: 'error', latencyMs: null }
  }
}

export async function fetchAllStocks(): Promise<WatchlistMap> {
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

export async function addStock(ticker: string): Promise<{ exist: boolean; stocks: WatchlistMap }> {
  const res = await apiFetch(`/watchlist/${encodeURIComponent(ticker)}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to add ${ticker}`)
  }
  return res.json()
}

export async function deleteStock(ticker: string): Promise<void> {
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
    throw new Error(err.detail ?? `Failed to load dashboard for ${ticker}`)
  }
  return res.json()
}

export async function fetchPortfolio(market?: 'US' | 'IN'): Promise<PortfolioResponse> {
  const res = await apiFetch(`/portfolio/${market ? `?market=${market}` : ''}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load portfolio')
  }
  return res.json()
}

export async function logBuy(ticker: string, shares: number, bought_at: number, date: string): Promise<StockHolding> {
  const res = await fetch(
    `/portfolio/${encodeURIComponent(ticker)}/buy?shares=${shares}&bought_at=${bought_at}&date=${date}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record purchase of ${ticker}`)
  }
  return res.json()
}

export async function logSell(ticker: string, shares: number, sold_at: number, date: string): Promise<StockHolding> {
  const res = await fetch(
    `/portfolio/${encodeURIComponent(ticker)}/sell?shares=${shares}&sold_at=${sold_at}&date=${date}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record sale of ${ticker}`)
  }
  return res.json()
}

export async function deleteTransaction(ticker: string, transactionId: number): Promise<void> {
  const res = await fetch(
    `/portfolio/${encodeURIComponent(ticker)}/transactions/${transactionId}`,
    { method: 'DELETE' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to delete transaction')
  }
}

export async function downloadPortfolio(market?: 'US' | 'IN'): Promise<void> {
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
  const res = await apiFetch(`/portfolio/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to remove ${ticker}`)
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

// ── FX ────────────────────────────────────────────────────────────────────

export async function fetchFxRate(base: 'USD' | 'INR', quote: 'USD' | 'INR'): Promise<FxRate> {
  const res = await apiFetch(`/fx/${base}/${quote}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load exchange rate')
  }
  return res.json()
}
