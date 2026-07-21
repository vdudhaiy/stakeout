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

export type View = 'home' | 'dashboard' | 'portfolio'

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

export interface StockDashboardResponse {
  ticker: string
  ohlcv: OHLCV[]
  info?: Record<string, unknown> | null
  analyst_price_targets?: Record<string, number | null> | null
  recommendations_summary?: RecommendationPeriod[] | null
  earnings_estimate?: EarningsEstimateRow[] | null
  revenue_estimate?: RevenueEstimateRow[] | null
  earnings_history?: EPSHistoryRow[] | null
  revenue_history?: RevenueHistoryRow[] | null
}

export interface StockPurchaseHistory {
  id: number
  sale: boolean
  ticker: string
  date: string
  shares: number
  bought_at: number
  sold_at: number
  shares_remaining: number
}

export interface StockHolding {
  ticker: string
  market: Market
  currency: 'USD' | 'INR'
  company_name: string
  shares: number
  sold_shares: number
  average_cost: number
  // These four are null when a live quote couldn't be fetched — render an
  // explicit "unavailable" state (greyed row), never treat null as 0.
  current_price: number | null
  stock_value: number | null
  profit_loss: number | null
  profit_loss_percentage: number | null
  total_earned: number
  total_invested: number
  trade_history: StockPurchaseHistory[]
}

export interface PortfolioResponse {
  market?: Market | null
  currency: 'USD' | 'INR'
  portfolio_value: number
  realized_gains: number
  total_shares: number
  total_invested: number
  total_return: number
  return_percentage: number
  net_profit_loss: number
  holdings: StockHolding[]
}

export type StockMap = Record<string, string>

export type Market = 'US' | 'IN'
export type MarketFilter = 'ALL' | 'US' | 'IN'

/** Per-user watchlist: ticker → display name + market it trades on */
export type WatchlistMap = Record<string, { name: string; market: Market }>

export interface NewsArticle {
  title: string
  url: string
  source: string
  published_at?: string | null
  image?: string | null
  provider: 'gdelt' | 'yahoo'
  region?: 'us' | 'in' | 'global'
  layer?: 'company' | 'industry' | 'market'
}

export interface NewsResponse {
  region: string
  articles: NewsArticle[]
}

export interface StockNewsResponse {
  ticker: string
  company_name?: string | null
  industry?: string | null
  market: Market
  articles: NewsArticle[]
}

export type GroupedStocks = Record<string, string[]>

export interface ComparisonGroup {
  name: string
  tickers: string[]
  type: 'industry' | 'sector' | 'all'
}

export interface EnrichedOHLCV extends OHLCV {
  bbUpper?: number | null
  bbMiddle?: number | null
  bbLower?: number | null
  // dynamic fields: sma_10, sma_20, ema_9, ema_50, etc.
  [key: string]: unknown
}

export interface IndicatorPoint {
  date: string
  value: number | null
}

export interface MACDDataPoint {
  date: string
  macd: number | null
  signal: number | null
  histogram: number | null
}

export interface BollingerPoint {
  date: string
  upper: number | null
  middle: number | null
  lower: number | null
}

export interface SMAResponse {
  ticker: string
  period: number
  values: IndicatorPoint[]
}

export interface EMAResponse {
  ticker: string
  period: number
  values: IndicatorPoint[]
}

export interface IndicatorsResponse {
  ticker: string
  days: number
  sma: SMAResponse[]
  ema: EMAResponse[]
  rsi: { ticker: string; period: number; values: IndicatorPoint[] } | null
  macd: { ticker: string; fast: number; slow: number; signal_period: number; values: MACDDataPoint[] } | null
  bollinger: { ticker: string; period: number; std_dev: number; values: BollingerPoint[] } | null
}
