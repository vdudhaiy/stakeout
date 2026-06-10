export interface OHLCV {
  date: string
  open: number | null
  high: number | null
  low: number | null
  close: number
  volume: number | null
}

export interface OHLCVResponse {
  ticker: string
  data: OHLCV[]
}

export type HealthStatus = 'ok' | 'error' | 'loading'

export interface HealthInfo {
  status: HealthStatus
  latencyMs: number | null
}

export interface LatencyRecord {
  time: string
  latencyMs: number | null
  status: HealthStatus
}

export type View = 'home' | 'dashboard' | 'health'

export interface RecommendationPeriod {
  period?: string | null
  // backend Pydantic uses snake_case; yfinance DataFrame uses camelCase — handle both
  strong_buy?: number | null
  strongBuy?: number | null
  buy?: number | null
  hold?: number | null
  sell?: number | null
  strong_sell?: number | null
  strongSell?: number | null
}

export interface EarningsEstimateRow {
  period?: string | null
  number_of_analysts?: number | null
  avg?: number | null
  low?: number | null
  high?: number | null
  year_ago_eps?: number | null
  growth?: number | null
}

export interface RevenueEstimateRow {
  period?: string | null
  number_of_analysts?: number | null
  avg?: number | null
  low?: number | null
  high?: number | null
  year_ago_revenue?: number | null
  growth?: number | null
}

export interface StockDetails {
  ticker: string
  info?: Record<string, unknown> | null
  analyst_price_targets?: Record<string, number | null> | null
  recommendations_summary?: RecommendationPeriod[] | null
  earnings_estimate?: EarningsEstimateRow[] | null
  revenue_estimate?: RevenueEstimateRow[] | null
}

export interface StockCreateResponse {
  exist: boolean
  ohlcv: OHLCVResponse
  details: StockDetails
}

export interface EPSHistoryRow {
  date?: string | null
  surprise_percent?: number | null
  eps_growth?: number | null
}

export interface EPSHistoryResponse {
  ticker: string
  earnings_history: EPSHistoryRow[]
}

export interface RevenueHistoryRow {
  date?: string | null
  revenue?: number | null
  percent_change?: number | null
}

export interface RevenueHistoryResponse {
  ticker: string
  revenue_history: RevenueHistoryRow[]
}

export type StockMap = Record<string, string>

export type GroupedStocks = Record<string, string[]>

export interface ComparisonGroup {
  name: string
  tickers: string[]
  type: 'industry' | 'sector' | 'all'
}
