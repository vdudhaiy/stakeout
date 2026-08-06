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

export type View = 'home' | 'tracker' | 'portfolio' | 'settings' | 'get-started'

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

export interface BuyLot {
  shares: number
  bought_at: number
  date: string
}

export interface SellLot {
  shares: number
  sold_at: number
  date: string
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

export interface DividendEntry {
  id: number
  ticker: string
  date: string                // ex-dividend date
  amount_per_share: number
  shares_held: number          // shares held as of the ex-date when this was recorded
  total_amount: number         // amount_per_share * shares_held
  source: 'auto' | 'manual'
}

export interface StockHolding {
  ticker: string
  /** Which portfolio holds it — the portfolio tabs filter on this. 0 in guest mode. */
  portfolio_id: number
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
  total_dividends: number
  trade_history: StockPurchaseHistory[]
  dividends: DividendEntry[]
}

/** A portfolio itself, without position data — powers the tab bar. */
export interface PortfolioMeta {
  id: number
  name: string
  market: Market
  created_at: string
}

/** One portfolio's headline figures, in the same units as PortfolioResponse. */
export interface PortfolioStats {
  id: number
  name: string
  market: Market
  currency: 'USD' | 'INR'
  portfolio_value: number
  realized_gains: number
  total_shares: number
  total_invested: number
  total_return: number
  return_percentage: number
  total_dividends: number
  net_profit_loss: number
}

export interface PortfolioResponse {
  market?: Market | null
  currency: 'USD' | 'INR'
  // These are the COMBINED totals across every portfolio in the market — what
  // the bar above the tabs shows. Per-portfolio figures live in `portfolios`.
  portfolio_value: number
  realized_gains: number
  total_shares: number
  total_invested: number
  total_return: number
  return_percentage: number
  total_dividends: number
  net_profit_loss: number
  /** Flat across all portfolios in the market; filter by `portfolio_id` per tab. */
  holdings: StockHolding[]
  /** Per-portfolio breakdown, in tab (creation) order. */
  portfolios: PortfolioStats[]
}

// One data row from an uploaded import file, parsed and duplicate-checked
// but not yet applied. Returned by POST /portfolio/import/preview.
export interface ImportPreviewRow {
  row: number                  // 1-indexed spreadsheet row (header is row 1)
  market: string                 // market cell as given in the file (e.g. "US", "IND")
  ticker: string                  // resolved ticker, exchange suffix applied (e.g. "RELIANCE.NS")
  date: string | null            // null if the date itself failed to parse
  action: 'buy' | 'sell' | ''   // '' only when the row failed before the action could be parsed
  shares: number
  price: number
  valid: boolean                  // false if the row failed to parse — see `error`
  error: string | null
  duplicate: boolean               // true if this exactly matches another transaction
  duplicate_reason: string | null   // e.g. "Matches a transaction..." or "Duplicate of row 4 in this file"
  portfolio: string | null          // portfolio name as written in the file, if the column was present
  portfolio_id: number | null       // resolved portfolio; null if the name didn't resolve
}

// A problem that stops the whole import rather than skipping one row. Only
// portfolio-name errors produce these: a row naming a portfolio that doesn't
// exist can't be filed anywhere sensible, so the user fixes the file instead.
export interface ImportBlockingError {
  row: number       // 0 for a file-level problem not tied to one row
  message: string
}

export interface ImportPreviewResult {
  total_rows: number
  rows: ImportPreviewRow[]
  // Non-empty means nothing may be imported until the file is corrected.
  blocking_errors: ImportBlockingError[]
}

// A previously-previewed row (must have been `valid`), echoed back with the
// user's include/skip decision. Sent to POST /portfolio/import/apply.
export interface ImportApplyRow {
  row: number
  market: string
  ticker: string
  date: string
  action: 'buy' | 'sell'
  shares: number
  price: number
  include: boolean               // false = user chose to skip this one (usually a duplicate)
  // Name only — never an id. The server re-resolves it against the caller's
  // own portfolios, so a forged id can't redirect rows.
  portfolio?: string | null
}

export interface ImportRowResult {
  row: number
  market: string
  ticker: string
  date: string
  action: 'buy' | 'sell'
  shares: number
  price: number
  status: 'imported' | 'failed' | 'skipped'
  error: string | null
}

export interface PortfolioImportResult {
  total_rows: number
  imported_rows: number
  failed_rows: number
  skipped_rows: number
  rows: ImportRowResult[]
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
  layer?: 'company' | 'industry' | 'sector' | 'market'
}

export interface NewsResponse {
  region: string
  articles: NewsArticle[]
}

export interface StockNewsResponse {
  ticker: string
  company_name?: string | null
  sector?: string | null
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

export interface IndexPoint {
  date: string
  close: number
}

export interface IndexQuote {
  symbol: string
  name: string
  region: 'US' | 'IN'
  last: number
  change?: number | null
  change_pct?: number | null
  points: IndexPoint[]
}

export interface IndicesResponse {
  indices: IndexQuote[]
}

export interface TickerClassification {
  sector?: string | null
  industry?: string | null
}

export type ClassificationMap = Record<string, TickerClassification>

export interface TickerSuggestion {
  symbol: string    // bare ticker — no .NS/.BO suffix, the exchange picker applies that
  name: string
  exchange: string  // display label, e.g. "NASDAQ", "NSE"
}

// ── AI Explanation Layer ──────────────────────────────────────────────────

export interface RSIRecoveryStats {
  occurrences: number
  horizon_days: number
  recovered_pct: number
  avg_return_pct: number
}

export interface StockFacts {
  ticker: string
  as_of: string
  history_days: number
  close: number
  change_pct: number | null
  rsi: number | null
  rsi_zone: string | null
  bollinger_position: string | null
  macd_signal: string | null
  sma_trend: string | null
  volume_vs_avg_pct: number | null
  rsi_recovery: RSIRecoveryStats | null
  headlines: string[]
  confidence: 'low' | 'medium' | 'high'
}

export interface StockExplanationResponse {
  ticker: string
  summary: string
  facts: StockFacts
  confidence: 'low' | 'medium' | 'high'
  generated_at: string
  model: string
}

export interface ChatMessage {
  role: 'user' | 'assistant'
  content: string
}

export type ChatContext =
  | { kind: 'stock'; ticker: string }
  | { kind: 'portfolio'; facts: PortfolioResponse }
  | { kind: 'general' }

export interface ChatResponse {
  reply: string
}
