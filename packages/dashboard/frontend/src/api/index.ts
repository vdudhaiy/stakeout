import type { OHLCVResponse, HealthInfo, StockDetails, GroupedStocks, StockCreateResponse } from '../types'

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

export async function fetchAllStocks(): Promise<string[]> {
  const res = await fetch('/stocks/')
  if (!res.ok) throw new Error('Failed to fetch stocks list')
  const data = await res.json()
  return (data.stocks as string[]) ?? []
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
