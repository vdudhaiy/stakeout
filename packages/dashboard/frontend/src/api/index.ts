import type { OHLCVResponse, HealthInfo, StockDetails, GroupedStocks, StockMap, StockCreateResponse, EPSHistoryResponse, RevenueHistoryResponse, StockDashboardResponse, PortfolioResponse, StockHolding } from '../types'

export async function fetchHealth(): Promise<HealthInfo> {
  const start = Date.now()
  try {
    const res = await fetch('/health')
    const latencyMs = Date.now() - start
    if (!res.ok) return { status: 'error', latencyMs }
    const data = await res.json()
    return { status: data.status === 'ok' ? 'ok' : 'error', latencyMs }
  } catch {
    return { status: 'error', latencyMs: null }
  }
}

export async function fetchAllStocks(): Promise<StockMap> {
  const res = await fetch('/stocks/')
  if (!res.ok) throw new Error('Failed to fetch stocks list')
  const data = await res.json()
  return (data.stocks as StockMap) ?? {}
}

export async function fetchStockDetails(ticker: string): Promise<StockDetails> {
  const res = await fetch(`/stocks/${ticker}/details`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load details for ${ticker}`)
  }
  return res.json()
}

export async function fetchStock(ticker: string, days: number): Promise<OHLCVResponse> {
  const res = await fetch(`/stocks/${ticker}?days=${days}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load ${ticker}`)
  }
  return res.json()
}

export async function fetchIndustryMap(): Promise<GroupedStocks> {
  const res = await fetch('/stocks/industries')
  if (!res.ok) throw new Error('Failed to fetch industry map')
  const data = await res.json()
  return data.industries as GroupedStocks
}

export async function fetchSectorMap(): Promise<GroupedStocks> {
  const res = await fetch('/stocks/sectors')
  if (!res.ok) throw new Error('Failed to fetch sector map')
  const data = await res.json()
  return data.sectors as GroupedStocks
}

export async function fetchCurrentStock(ticker: string): Promise<OHLCVResponse> {
  const res = await fetch(`/stocks/${ticker}/current`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load current data for ${ticker}`)
  }
  return res.json()
}

export async function fetchIntradayStock(ticker: string): Promise<OHLCVResponse> {
  const res = await fetch(`/stocks/${ticker}/intraday`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load intraday data for ${ticker}`)
  }
  return res.json()
}

export async function addStock(ticker: string): Promise<StockCreateResponse> {
  const res = await fetch(`/stocks/${encodeURIComponent(ticker)}`, { method: 'POST' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to add ${ticker}`)
  }
  return res.json()
}

export async function deleteStock(ticker: string): Promise<void> {
  const res = await fetch(`/stocks/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to delete ${ticker}`)
  }
}

export async function fetchEpsHistory(ticker: string): Promise<EPSHistoryResponse> {
  const res = await fetch(`/stocks/${ticker}/eps`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load EPS history for ${ticker}`)
  }
  return res.json()
}

export async function fetchRevenueHistory(ticker: string): Promise<RevenueHistoryResponse> {
  const res = await fetch(`/stocks/${ticker}/revenue`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load revenue history for ${ticker}`)
  }
  return res.json()
}

export async function fetchStockDashboard(ticker: string, days: number): Promise<StockDashboardResponse> {
  const res = await fetch(`/stocks/${ticker}/dashboard?days=${days}`)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to load dashboard for ${ticker}`)
  }
  return res.json()
}

export async function fetchPortfolio(): Promise<PortfolioResponse> {
  const res = await fetch('/portfolio/')
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? 'Failed to load portfolio')
  }
  return res.json()
}

export async function logBuy(ticker: string, shares: number, bought_at: number): Promise<StockHolding> {
  const res = await fetch(
    `/portfolio/${encodeURIComponent(ticker)}/buy?shares=${shares}&bought_at=${bought_at}`,
    { method: 'POST' },
  )
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to record purchase of ${ticker}`)
  }
  return res.json()
}

export async function logSell(ticker: string, shares: number, sold_at: number): Promise<StockHolding> {
  const res = await fetch(
    `/portfolio/${encodeURIComponent(ticker)}/sell?shares=${shares}&sold_at=${sold_at}`,
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

export async function deletePortfolioHolding(ticker: string): Promise<void> {
  const res = await fetch(`/portfolio/${encodeURIComponent(ticker)}`, { method: 'DELETE' })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Failed to remove ${ticker}`)
  }
}

export async function fetchMarketStatus(): Promise<boolean | null> {
  try {
    const res = await fetch('/stocks/market')
    if (!res.ok) return null
    const data = await res.json()
    return data.status as boolean
  } catch {
    return null
  }
}
