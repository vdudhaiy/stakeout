import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import clsx from 'clsx'
import { motion, AnimatePresence } from 'motion/react'
import { TrendingUp, TrendingDown, RefreshCw, Info, Trash2, CandlestickChart as CandleIcon, LineChart as LineChartIcon, ChevronDown, ChevronUp } from 'lucide-react'
import { Navbar } from './components/Navbar'
import { HomePage } from './components/HomePage'
import { GetStartedPage } from './components/GetStartedPage'
import { SettingsPage } from './components/SettingsPage'
import { PortfolioPage } from './components/PortfolioPage'
import { TickerSidebar } from './components/TickerSidebar'
import { ComparisonView } from './components/ComparisonView'
import { PriceChart } from './components/PriceChart'
import { CandlestickChart } from './components/CandlestickChart'
import { RSIChart } from './components/RSIChart'
import { MACDChart } from './components/MACDChart'
import { VolumeChart, volUnit } from './components/VolumeChart'
import { OHLCVStats } from './components/OHLCVStats'
import { StockInfoCard } from './components/StockInfoCard'
import { AnalystPanel } from './components/AnalystPanel'
import { EarningsHistoryPanel } from './components/EarningsHistoryPanel'
import { Footer } from './components/Footer'
import { AIInsightCard } from './components/AIInsightCard'
import { AIChatWidget } from './components/AIChatWidget'
import { fetchAllStocks, fetchCurrentStock, fetchIntradayStock, fetchMarketStatus, fetchStock, fetchStockDashboard, deleteStock, addStock, fetchIndicators } from './api'
import { parseEtDateStr, fmtHHMMWithTz, etToLocalHHMM, localTzAbbr, formatEtDate, formatLocalDate } from './utils/time'
import { NewsPanel } from './components/NewsPanel'
import { TickerTape } from './components/TickerTape'
import { InfoTip } from './components/InfoTip'
import { SignInGate } from './components/SignInGate'
import { PasswordRecoveryModal } from './components/PasswordRecoveryModal'
import { useAuth } from './contexts/AuthContext'
import { usePrefs } from './contexts/PrefsContext'
import { CURRENCY_SYMBOL, formatMoney } from './utils/currency'
import { marketOf, displayTicker } from './utils/market'
import { MARKET_STATUS_REFRESH_MS, PRICE_REFRESH_MS } from './utils/env'
import { usePersistedState } from './utils/usePersistedState'
import type { OHLCV, View, StockDetails, WatchlistMap, StockMap, ComparisonGroup, EPSHistoryRow, RevenueHistoryRow, IndicatorsResponse, EnrichedOHLCV, PortfolioResponse, ChatContext } from './types'
import { SMA_PERIODS, EMA_PERIODS, SMA_COLORS, EMA_COLORS } from './utils/indicators'
import type { OverlayConfig } from './utils/indicators'
import { overlayFade, scaleIn, popIn, viewFade, layoutSpring, collapse } from './lib/motion'

const DAYS_OPTIONS = [
  { label: '1D', value: 0 },
  { label: '7D', value: 7 },
  { label: '14D', value: 14 },
  { label: '30D', value: 30 },
  { label: '90D', value: 90 },
  { label: '180D', value: 180 },
  { label: '1Yr', value: 365 },
  { label: '2Yr', value: 730 },
  { label: '3Yr', value: 1095 },
]

const PATH_TO_VIEW: Record<string, View> = {
  '/': 'home',
  '/tracker': 'tracker',
  '/dashboard': 'tracker',   // legacy alias — the Dashboard was renamed to Tracker
  '/portfolio': 'portfolio',
  '/settings': 'settings',
  '/get-started': 'get-started',
}

export default function App() {
  const location = useLocation()
  const navigate = useNavigate()
  const view: View = PATH_TO_VIEW[location.pathname] ?? 'home'
  const { canUseApp, passwordRecovery } = useAuth()
  const { aiEnabled } = usePrefs()

  const [ticker, setTicker] = useState('')
  const [allTickers, setAllTickers] = useState<WatchlistMap | null>(null)
  const [days, setDays] = useState(30)
  const [data, setData] = useState<OHLCV[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState<StockDetails | null>(null)
  const [comparisonGroup, setComparisonGroup] = useState<ComparisonGroup | null>(null)
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null)
  const [marketOpenIN, setMarketOpenIN] = useState<boolean | null>(null)
  const [currentData, setCurrentData] = useState<OHLCV | null>(null)
  const [currentFetchedAt, setCurrentFetchedAt] = useState<Date | null>(null)
  const [currentLoading, setCurrentLoading] = useState(false)
  const [showMarketHours, setShowMarketHours] = useState(false)
  const [epsHistory, setEpsHistory] = useState<EPSHistoryRow[] | null>(null)
  const [revenueHistory, setRevenueHistory] = useState<RevenueHistoryRow[] | null>(null)
  const [intradayData, setIntradayData] = useState<OHLCV[] | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [preparingTicker, setPreparingTicker] = useState<string | null>(null)
  const [chartType, setChartType] = useState<'candle' | 'area'>('candle')
  const [indicators, setIndicators] = useState<IndicatorsResponse | null>(null)
  const [activeSMA, setActiveSMA] = useState<number[]>([])
  const [activeEMA, setActiveEMA] = useState<number[]>([])
  const [overlayBB, setOverlayBB] = useState(false)
  const [openDropdown, setOpenDropdown] = useState<'sma' | 'ema' | null>(null)
  const [subCharts, setSubCharts] = usePersistedState('tracker-subcharts', { rsi: true, macd: true })
  const [portfolioSnapshot, setPortfolioSnapshot] = useState<PortfolioResponse | null>(null)

  const checkMarket = useCallback(() => Promise.all([
    fetchMarketStatus('US').then(setMarketOpen),
    fetchMarketStatus('IN').then(setMarketOpenIN),
  ]).then(() => {}), [])

  useEffect(() => {
    checkMarket()
    const id = setInterval(checkMarket, MARKET_STATUS_REFRESH_MS)
    return () => clearInterval(id)
  }, [checkMarket])

  useEffect(() => {
    if (!canUseApp) { setAllTickers({}); return }
    fetchAllStocks().then(setAllTickers).catch(() => setAllTickers({}))
  }, [canUseApp])

  // Which exchange does the selected ticker trade on? Drives live-vs-archive logic.
  const tickerMarket = marketOf(ticker)
  const tickerMarketOpen = tickerMarket === 'IN' ? marketOpenIN : marketOpen
  const nativeCurrency = tickerMarket === 'IN' ? 'INR' as const : 'USD' as const
  const currencySymbol = CURRENCY_SYMBOL[nativeCurrency]
  const fmt = (v: number | null | undefined, opts?: { sign?: boolean }) =>
    formatMoney(v, nativeCurrency, opts)

  const loadCurrent = useCallback(() => {
    if (!ticker) return Promise.resolve()
    setCurrentLoading(true)
    return fetchCurrentStock(ticker)
      .then(res => {
        setCurrentData(res.data[0] ?? null)
        setCurrentFetchedAt(new Date())
      })
      .catch(() => {})
      .finally(() => setCurrentLoading(false))
  }, [ticker])

  useEffect(() => {
    setCurrentData(null)
    setCurrentFetchedAt(null)

    loadCurrent()

    if (!tickerMarketOpen) return
    const id = setInterval(loadCurrent, PRICE_REFRESH_MS)
    return () => clearInterval(id)
  }, [ticker, tickerMarketOpen, loadCurrent])

  // Pre-market: date string contains 'T' (e.g. "2026-06-09T07:30") vs plain "2026-06-09"
  const isPreMarket = !tickerMarketOpen && (currentData?.date?.includes('T') ?? false)

  useEffect(() => {
    if (!isPreMarket) return
    const id = setInterval(loadCurrent, PRICE_REFRESH_MS)
    return () => clearInterval(id)
  }, [isPreMarket, loadCurrent])

  useEffect(() => {
    if (!showMarketHours) return
    function close(e: MouseEvent) {
      if (!infoRef.current?.contains(e.target as Node)) setShowMarketHours(false)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [showMarketHours])

  useEffect(() => {
    if (!openDropdown) return
    function close(e: MouseEvent) {
      if (!overlayRef.current?.contains(e.target as Node)) setOpenDropdown(null)
    }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [openDropdown])

  // Tracks which ticker was last loaded so we know whether to fetch details too
  const prevTicker = useRef<string>('')
  // Incremented on every load; stale responses from aborted loads are ignored
  const loadGen = useRef(0)
  const infoRef = useRef<HTMLDivElement>(null)
  const overlayRef = useRef<HTMLDivElement>(null)
  const initialTickerSet = useRef(false)

  useEffect(() => {
    if (!initialTickerSet.current && allTickers && Object.keys(allTickers).length > 0) {
      initialTickerSet.current = true
      setTicker(Object.keys(allTickers)[0])
    }
  }, [allTickers])

  const load = useCallback(async () => {
    if (!ticker) return
    const gen = ++loadGen.current
    const isNewTicker = prevTicker.current !== ticker
    prevTicker.current = ticker

    setError(null)
    setLoading(true)

    if (isNewTicker) {
      // Clear all so nothing renders until data arrives
      setData([])
      setDetails(null)
      setEpsHistory(null)
      setRevenueHistory(null)
      setIntradayData(null)
      setIndicators(null)
    }

    // When in 1D mode, fetch regular daily data at 30D for header metrics
    const effectiveDays = days === 0 ? 30 : days

    try {
      if (isNewTicker) {
        const [dashboardRes, intradayRes, indicatorsRes] = await Promise.all([
          fetchStockDashboard(ticker, effectiveDays),
          days === 0 ? fetchIntradayStock(ticker).catch(() => null) : Promise.resolve(null),
          days > 0 ? fetchIndicators(ticker, effectiveDays).catch(() => null) : Promise.resolve(null),
        ])
        if (gen !== loadGen.current) return
        setData(dashboardRes.ohlcv)
        setDetails({
          ticker: dashboardRes.ticker,
          info: dashboardRes.info,
          analyst_price_targets: dashboardRes.analyst_price_targets,
          recommendations_summary: dashboardRes.recommendations_summary,
          earnings_estimate: dashboardRes.earnings_estimate,
          revenue_estimate: dashboardRes.revenue_estimate,
        } as StockDetails)
        setEpsHistory(dashboardRes.earnings_history ?? null)
        setRevenueHistory(dashboardRes.revenue_history ?? null)
        setIntradayData(intradayRes?.data ?? null)
        setIndicators(indicatorsRes)
      } else if (days === 0) {
        // Switching into 1D mode — only fetch intraday, keep existing daily data for header
        setIndicators(null)
        const intradayRes = await fetchIntradayStock(ticker)
        if (gen !== loadGen.current) return
        setIntradayData(intradayRes.data)
      } else {
        // Only days changed — details are still valid
        const [ohlcvRes, indicatorsRes] = await Promise.all([
          fetchStock(ticker, days),
          fetchIndicators(ticker, days).catch(() => null),
        ])
        if (gen !== loadGen.current) return
        setData(ohlcvRes.data)
        setIndicators(indicatorsRes)
      }
    } catch (e) {
      if (gen !== loadGen.current) return
      setError(e instanceof Error ? e.message : 'Failed to load data')
      if (isNewTicker) {
        setData([])
        setEpsHistory(null)
        setRevenueHistory(null)
        setIntradayData(null)
      }
    } finally {
      if (gen === loadGen.current) setLoading(false)
    }
  }, [ticker, days])

  useEffect(() => {
    load()
  }, [load])

  const handleDelete = useCallback(async () => {
    setDeleteLoading(true)
    try {
      await deleteStock(ticker)
      const updated = await fetchAllStocks()
      setAllTickers(updated)
      const next = Object.keys(updated)[0] ?? ''
      setTicker(next)
      setData([])
      setDetails(null)
    } finally {
      setDeleteLoading(false)
      setDeleteConfirm(false)
    }
  }, [ticker])

  const today = new Date().toISOString().slice(0, 10)
  // Strip today's entry unless market is confirmed closed — partial candles skew the chart
  const displayData = tickerMarketOpen !== false ? data.filter(d => d.date !== today) : data

  // For charts: use intraday data in 1D mode, otherwise the regular daily series
  const chartData = days === 0 ? (intradayData ?? []) : displayData

  const enrichedChartData = useMemo((): EnrichedOHLCV[] => {
    if (!indicators) return chartData as EnrichedOHLCV[]
    const smaMaps = new Map(
      indicators.sma.map(s => [s.period, new Map(s.values.map(p => [p.date, p.value]))])
    )
    const emaMaps = new Map(
      indicators.ema.map(e => [e.period, new Map(e.values.map(p => [p.date, p.value]))])
    )
    const bbMap = new Map(indicators.bollinger?.values.map(p => [p.date, p]) ?? [])
    return chartData.map(d => {
      const result: Record<string, unknown> = {
        ...d,
        bbUpper:  bbMap.get(d.date)?.upper  ?? null,
        bbMiddle: bbMap.get(d.date)?.middle ?? null,
        bbLower:  bbMap.get(d.date)?.lower  ?? null,
      }
      for (const [period, map] of smaMaps) result[`sma_${period}`] = map.get(d.date) ?? null
      for (const [period, map] of emaMaps) result[`ema_${period}`] = map.get(d.date) ?? null
      return result as EnrichedOHLCV
    })
  }, [chartData, indicators])

  const latest = displayData[displayData.length - 1]
  const prev = displayData[displayData.length - 2]

  // Last complete trading day (archive)
  const archiveClose = latest?.close ?? null
  const archiveChange = archiveClose != null && prev?.close != null ? archiveClose - prev.close : null
  const archiveChangePct = archiveChange != null && prev?.close ? (archiveChange / prev.close) * 100 : null

  // Live intraday price — only valid while market is open
  const liveClose = tickerMarketOpen ? (currentData?.close ?? null) : null
  const liveChange = liveClose != null && archiveClose != null ? liveClose - archiveClose : null
  const liveChangePct = liveChange != null && archiveClose ? (liveChange / archiveClose) * 100 : null

  // Pre-market price — only valid when isPreMarket
  const preMarketClose = isPreMarket ? (currentData?.close ?? null) : null
  const preMarketChange = preMarketClose != null && archiveClose != null ? preMarketClose - archiveClose : null
  const preMarketChangePct = preMarketChange != null && archiveClose ? (preMarketChange / archiveClose) * 100 : null
  const preMarketTime = isPreMarket ? (currentData?.date?.split('T')[1] ?? null) : null
  const offHoursLabel = preMarketTime != null && preMarketTime >= '16:00' ? 'AFTER-HOURS' : 'PRE-MARKET'
  const preMarketLocalTime = isPreMarket && currentData?.date
    ? fmtHHMMWithTz(parseEtDateStr(currentData.date))
    : null
  const localTz = localTzAbbr()
  const scheduleLocal = {
    pmStart:  etToLocalHHMM('04:00'),
    mktOpen:  etToLocalHHMM('09:30'),
    mktClose: etToLocalHHMM('16:00'),
    ahEnd:    etToLocalHHMM('20:00'),
  }

  // Header primary price: live when market open, otherwise archive close
  const headerPrice = liveClose ?? archiveClose
  const headerChange = liveClose != null ? liveChange : archiveChange
  const headerChangePct = liveClose != null ? liveChangePct : archiveChangePct

  // Flash the header price on change so a poll-driven update is noticeable,
  // not just a silent DOM overwrite — green/red matches the move's direction.
  const prevHeaderPrice = useRef(headerPrice)
  const [priceFlash, setPriceFlash] = useState<'up' | 'down' | null>(null)
  const [priceFlashTick, setPriceFlashTick] = useState(0)
  useEffect(() => {
    if (headerPrice != null && prevHeaderPrice.current != null && headerPrice !== prevHeaderPrice.current) {
      setPriceFlash(headerPrice > prevHeaderPrice.current ? 'up' : 'down')
      setPriceFlashTick(t => t + 1)
    }
    prevHeaderPrice.current = headerPrice
  }, [headerPrice])

  // OHLCV stats block source and its baseline for change calculation
  const mainOHLCV = tickerMarketOpen ? currentData : latest
  const mainOHLCVPrevClose = tickerMarketOpen ? archiveClose : (prev?.close ?? null)

  const tickerNames: StockMap = useMemo(
    () => Object.fromEntries(Object.entries(allTickers ?? {}).map(([t, v]) => [t, v.name])),
    [allTickers],
  )

  const displayName = details?.info?.displayName as string | undefined
  const shortName = details?.info?.shortName as string | undefined
  const primaryName = displayName ?? shortName

  // The AI chat is only wired up with real context on the Tracker (watchlist +
  // per-stock details) and Portfolio pages — nowhere else has anything for it
  // to talk about, so it stays hidden there rather than showing an empty shell.
  const showAIChat = view === 'tracker' || view === 'portfolio'
  const aiChatContext: ChatContext =
    view === 'tracker' && ticker
      ? { kind: 'stock', ticker }
      : view === 'portfolio' && portfolioSnapshot
        ? { kind: 'portfolio', facts: portfolioSnapshot }
        : { kind: 'general' }

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      <Navbar
        marketOpen={marketOpen}
        marketOpenIN={marketOpenIN}
        onRefreshMarket={checkMarket}
      />

      {view !== 'home' && view !== 'get-started' && <TickerTape tickers={allTickers} />}

      <AnimatePresence mode="wait">
      <motion.div key={view} variants={viewFade} initial="hidden" animate="show" exit="exit" className="flex-1 flex flex-col overflow-hidden min-h-0">
      {view === 'home' ? (
        <HomePage />
      ) : view === 'get-started' ? (
        <GetStartedPage />
      ) : !canUseApp ? (
        <SignInGate view={view} />
      ) : view === 'settings' ? (
        <SettingsPage />
      ) : view === 'portfolio' ? (
        <PortfolioPage
          onViewTicker={async (t) => {
            navigate('/tracker')
            if (allTickers && t in allTickers) {
              setTicker(t)
              return
            }
            setPreparingTicker(t)
            try {
              await addStock(t)
              setAllTickers(await fetchAllStocks())
            } catch {}
            setPreparingTicker(null)
            setTicker(t)
          }}
          onTickerRemoved={async (t) => {
            const updated = await fetchAllStocks()
            setAllTickers(updated)
            if (ticker === t) {
              const next = Object.keys(updated).find(k => k !== t) ?? ''
              setTicker(next)
            }
          }}
          onTickerAdded={async () => { setAllTickers(await fetchAllStocks()) }}
          onData={setPortfolioSnapshot}
        />
      ) : (
        <div className="flex flex-1 overflow-hidden">
          {allTickers === null ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <RefreshCw size={14} className="animate-spin" />
                Loading stocks...
              </div>
            </div>
          ) : <>
          <TickerSidebar
            selected={ticker}
            tickers={allTickers ?? {}}
            onSelect={t => { setComparisonGroup(null); setTicker(t) }}
            onCompare={setComparisonGroup}
            onTickersUpdated={setAllTickers}
          />

          {comparisonGroup ? (
            <ComparisonView group={comparisonGroup} onBack={() => setComparisonGroup(null)} marketOpen={tickerMarketOpen} tickerNames={tickerNames} />
          ) : preparingTicker ? (
            <div className="flex flex-1 items-center justify-center">
              <div className="flex items-center gap-2 text-zinc-500 text-sm">
                <RefreshCw size={14} className="animate-spin" />
                Loading {preparingTicker && displayTicker(preparingTicker)}...
              </div>
            </div>
          ) : (
          <main className="flex-1 overflow-y-auto p-6 min-w-0">
            <div className="flex flex-col gap-5 max-w-6xl">
              {/* Ticker header row */}
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-baseline gap-3 flex-wrap">
                    <h1 className="text-2xl font-bold tracking-tight">
                      {primaryName ?? displayTicker(ticker)}
                      {primaryName && (
                        <span className="text-zinc-500 font-normal text-lg ml-2">({displayTicker(ticker)})</span>
                      )}
                    </h1>

                    {/* Primary price: archive close (or live when market open) */}
                    {headerPrice != null && (
                      <motion.span
                        key={priceFlashTick}
                        initial={priceFlash ? {
                          backgroundColor: priceFlash === 'up' ? 'rgba(16,185,129,0.35)' : 'rgba(239,68,68,0.35)',
                        } : false}
                        animate={{ backgroundColor: 'rgba(0,0,0,0)' }}
                        transition={{ duration: 0.6, ease: 'easeOut' }}
                        className="font-mono text-xl font-semibold text-zinc-100 rounded px-0.5 -mx-0.5"
                      >
                        {fmt(headerPrice)}
                      </motion.span>
                    )}
                    {headerChange !== null && (
                      <span className={clsx(
                        'flex items-center gap-1 text-sm font-mono',
                        headerChange >= 0 ? 'text-emerald-400' : 'text-red-400',
                      )}>
                        {headerChange >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                        {fmt(headerChange, { sign: true })} ({headerChange >= 0 ? '+' : ''}{headerChangePct!.toFixed(2)}%)
                      </span>
                    )}

                  </div>

                  {(latest ?? currentData) && (
                    <div className="flex items-center gap-1.5 mt-1">
                      <p className="text-zinc-500 text-xs">
                        {tickerMarketOpen && currentFetchedAt
                          ? `Live · ${currentFetchedAt.toLocaleTimeString()}`
                          : `Last updated ${latest?.date ?? ''}`}
                      </p>
                      <button
                        onClick={loadCurrent}
                        disabled={currentLoading}
                        title="Refresh current price"
                        className="text-zinc-600 hover:text-zinc-400 disabled:opacity-40 transition-colors"
                      >
                        <RefreshCw size={10} className={currentLoading ? 'animate-spin' : ''} />
                      </button>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2 shrink-0">
                  <div className="flex rounded-lg overflow-hidden border border-zinc-800">
                    {DAYS_OPTIONS.map(({ label, value }) => (
                      <button
                        key={value}
                        onClick={() => setDays(value)}
                        className={clsx(
                          'relative px-3 py-1.5 text-xs font-medium transition-colors',
                          days === value ? 'text-white' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                        )}
                      >
                        {days === value && (
                          <motion.span
                            layoutId="days-option-pill"
                            transition={layoutSpring}
                            className="absolute inset-0 bg-indigo-600 -z-10"
                          />
                        )}
                        {label}
                      </button>
                    ))}
                  </div>
                  <button
                    onClick={load}
                    disabled={loading}
                    title="Refresh"
                    className="p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 rounded-lg transition-colors"
                  >
                    <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
                  </button>
                  <button
                    onClick={() => setDeleteConfirm(true)}
                    title={`Remove ${displayTicker(ticker)} from watchlist`}
                    className="p-2 text-red-600 hover:text-red-400 hover:bg-zinc-900 rounded-lg transition-colors"
                  >
                    <Trash2 size={13} />
                  </button>
                </div>
              </div>

              {/* Pre-market / after-hours block */}
              {isPreMarket && preMarketClose != null && (
                <div className="flex items-center gap-5 bg-zinc-900 border border-amber-500/20 rounded-xl px-5 py-3">
                  <span className="text-[10px] font-semibold tracking-widest text-amber-400 shrink-0">
                    {offHoursLabel}
                  </span>
                  <span className="font-mono text-sm font-semibold text-zinc-100">
                    {fmt(preMarketClose)}
                  </span>
                  {preMarketChange != null && (
                    <span className={clsx(
                      'flex items-center gap-1 text-sm font-mono',
                      preMarketChange >= 0 ? 'text-emerald-400' : 'text-red-400',
                    )}>
                      {preMarketChange >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {fmt(preMarketChange, { sign: true })} ({preMarketChange >= 0 ? '+' : ''}{preMarketChangePct!.toFixed(2)}%)
                    </span>
                  )}

                  <div className="ml-auto flex items-center gap-2.5 shrink-0">
                    {preMarketTime && (
                      <span className="text-zinc-600 text-xs">
                        as of {preMarketTime} ET
                        {preMarketLocalTime && <> ({preMarketLocalTime})</>}
                      </span>
                    )}

                    {/* Market hours info popover */}
                    <div ref={infoRef} className="relative">
                      <button
                        onClick={() => setShowMarketHours(s => !s)}
                        title="NYSE market hours"
                        className="text-zinc-600 hover:text-zinc-400 transition-colors"
                      >
                        <Info size={14} />
                      </button>
                      <AnimatePresence>
                        {showMarketHours && (
                          <motion.div
                            variants={popIn}
                            initial="hidden"
                            animate="show"
                            exit="exit"
                            style={{ transformOrigin: 'top right' }}
                            className="absolute right-0 top-6 z-50 w-72 bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl"
                          >
                            <p className="text-[10px] font-semibold tracking-widest text-zinc-400 mb-3">
                              NYSE MARKET HOURS
                            </p>
                            <div className="space-y-3">
                              {([
                                { label: 'Pre-market',  color: 'text-amber-400',   et: '04:00 – 09:30', local: `${scheduleLocal.pmStart} – ${scheduleLocal.mktOpen}` },
                                { label: 'Regular',     color: 'text-emerald-400', et: '09:30 – 16:00', local: `${scheduleLocal.mktOpen} – ${scheduleLocal.mktClose}` },
                                { label: 'After-hours', color: 'text-blue-400',    et: '16:00 – 20:00', local: `${scheduleLocal.mktClose} – ${scheduleLocal.ahEnd}` },
                              ] as const).map(({ label, color, et, local }) => (
                                <div key={label} className="space-y-0.5">
                                  <span className={`text-[10px] font-semibold tracking-widest ${color}`}>
                                    {label.toUpperCase()}
                                  </span>
                                  <div className="flex items-center justify-between text-xs font-mono">
                                    <span className="text-zinc-400">{et} ET</span>
                                    <span className="text-zinc-300">({local} {localTz})</span>
                                  </div>
                                </div>
                              ))}
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  </div>
                </div>
              )}

              {/* OHLCV stats — last complete trading day, or live today when market is open */}
              {mainOHLCV && (
                <OHLCVStats
                  open={mainOHLCV.open}
                  high={mainOHLCV.high}
                  low={mainOHLCV.low}
                  close={mainOHLCV.close}
                  volume={mainOHLCV.volume}
                  prevClose={mainOHLCVPrevClose ?? undefined}
                  format={fmt}
                />
              )}

              {/* Company info (sector / industry / summary) */}
              {details?.info && <StockInfoCard info={details.info} />}

              {/* AI-generated plain-English summary of the indicators below */}
              {aiEnabled && ticker && <AIInsightCard key={ticker} ticker={ticker} />}

              {/* Charts */}
              {error ? (
                <div className="flex items-center justify-center h-64 bg-zinc-900 border border-zinc-800 rounded-xl">
                  <div className="text-center space-y-2">
                    <p className="text-zinc-500 text-sm">{error}</p>
                    <button
                      onClick={load}
                      className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
                    >
                      Try again
                    </button>
                  </div>
                </div>
              ) : loading && chartData.length === 0 ? (
                <div className="flex items-center justify-center h-64 bg-zinc-900 border border-zinc-800 rounded-xl">
                  <div className="flex items-center gap-2 text-zinc-500 text-sm">
                    <RefreshCw size={13} className="animate-spin" />
                    Loading {displayTicker(ticker)}...
                  </div>
                </div>
              ) : chartData.length > 0 ? (
                <>
                  <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-[10px] text-zinc-500 tracking-widest font-medium">
                        {chartType === 'candle' ? 'PRICE' : 'CLOSE PRICE'}
                      </p>
                      <div className="flex items-center gap-2">
                        {days === 0 && chartData.length > 0 && (() => {
                          const dateStr = chartData[0].date.slice(0, 10)
                          const etDate = formatEtDate(dateStr)
                          const localDate = formatLocalDate(dateStr)
                          const tz = localTzAbbr()
                          return (
                            <span className="text-[10px] font-mono text-zinc-500">
                              {etDate} ET{etDate !== localDate ? ` (${localDate} ${tz})` : ` (${tz})`}
                            </span>
                          )
                        })()}

                        {/* Overlay controls — hidden in 1D mode */}
                        {days > 0 && indicators && (
                          <div ref={overlayRef} className="flex items-center gap-1">
                            {/* SMA dropdown */}
                            <div className="relative">
                              <button
                                onClick={() => setOpenDropdown(d => d === 'sma' ? null : 'sma')}
                                title="Simple Moving Average"
                                className={clsx(
                                  'flex items-center gap-0.5 px-2 py-0.5 text-[9px] rounded border transition-colors uppercase tracking-wider font-medium',
                                  activeSMA.length > 0
                                    ? 'border-amber-500/50 text-amber-300 bg-amber-950/50'
                                    : 'border-zinc-700 text-zinc-500 hover:text-zinc-300',
                                )}
                              >
                                SMA <ChevronDown size={8} />
                              </button>
                              <AnimatePresence>
                                {openDropdown === 'sma' && (
                                  <motion.div
                                    variants={popIn}
                                    initial="hidden"
                                    animate="show"
                                    exit="exit"
                                    style={{ transformOrigin: 'top right' }}
                                    className="absolute right-0 top-full mt-1 bg-zinc-950 border border-zinc-700 rounded-lg p-1 z-50 shadow-xl"
                                  >
                                    {SMA_PERIODS.map(period => (
                                      <button
                                        key={period}
                                        onClick={() => setActiveSMA(prev =>
                                          prev.includes(period) ? prev.filter(p => p !== period) : [...prev, period]
                                        )}
                                        title={`${period}-day Simple Moving Average`}
                                        className="flex items-center gap-2 w-full px-2 py-1 text-[10px] rounded hover:bg-zinc-800 transition-colors"
                                      >
                                        <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: SMA_COLORS[period] }} />
                                        <span className={activeSMA.includes(period) ? 'text-zinc-200' : 'text-zinc-500'}>
                                          {period}
                                        </span>
                                        {activeSMA.includes(period) && (
                                          <span className="ml-auto text-zinc-400 text-[8px]">✓</span>
                                        )}
                                      </button>
                                    ))}
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                            {/* Active SMA chips */}
                            {[...activeSMA].sort((a, b) => a - b).map(period => (
                              <span
                                key={`chip-sma-${period}`}
                                className="flex items-center px-1.5 py-0.5 text-[9px] rounded border"
                                style={{ borderColor: `${SMA_COLORS[period]}60`, color: SMA_COLORS[period] }}
                              >
                                {period}
                                <button
                                  onClick={() => setActiveSMA(prev => prev.filter(p => p !== period))}
                                  className="ml-0.5 opacity-60 hover:opacity-100 leading-none"
                                >×</button>
                              </span>
                            ))}
                            <div className="w-px h-3 bg-zinc-800 mx-0.5" />
                            {/* EMA dropdown */}
                            <div className="relative">
                              <button
                                onClick={() => setOpenDropdown(d => d === 'ema' ? null : 'ema')}
                                title="Exponential Moving Average"
                                className={clsx(
                                  'flex items-center gap-0.5 px-2 py-0.5 text-[9px] rounded border transition-colors uppercase tracking-wider font-medium',
                                  activeEMA.length > 0
                                    ? 'border-violet-500/50 text-violet-300 bg-violet-950/50'
                                    : 'border-zinc-700 text-zinc-500 hover:text-zinc-300',
                                )}
                              >
                                EMA <ChevronDown size={8} />
                              </button>
                              <AnimatePresence>
                                {openDropdown === 'ema' && (
                                  <motion.div
                                    variants={popIn}
                                    initial="hidden"
                                    animate="show"
                                    exit="exit"
                                    style={{ transformOrigin: 'top right' }}
                                    className="absolute right-0 top-full mt-1 bg-zinc-950 border border-zinc-700 rounded-lg p-1 z-50 shadow-xl"
                                  >
                                    {EMA_PERIODS.map(period => (
                                      <button
                                        key={period}
                                        onClick={() => setActiveEMA(prev =>
                                          prev.includes(period) ? prev.filter(p => p !== period) : [...prev, period]
                                        )}
                                        title={`${period}-day Exponential Moving Average`}
                                        className="flex items-center gap-2 w-full px-2 py-1 text-[10px] rounded hover:bg-zinc-800 transition-colors"
                                      >
                                        <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: EMA_COLORS[period] }} />
                                        <span className={activeEMA.includes(period) ? 'text-zinc-200' : 'text-zinc-500'}>
                                          {period}
                                        </span>
                                        {activeEMA.includes(period) && (
                                          <span className="ml-auto text-zinc-400 text-[8px]">✓</span>
                                        )}
                                      </button>
                                    ))}
                                  </motion.div>
                                )}
                              </AnimatePresence>
                            </div>
                            {/* Active EMA chips */}
                            {[...activeEMA].sort((a, b) => a - b).map(period => (
                              <span
                                key={`chip-ema-${period}`}
                                className="flex items-center px-1.5 py-0.5 text-[9px] rounded border"
                                style={{ borderColor: `${EMA_COLORS[period]}60`, color: EMA_COLORS[period] }}
                              >
                                {period}
                                <button
                                  onClick={() => setActiveEMA(prev => prev.filter(p => p !== period))}
                                  className="ml-0.5 opacity-60 hover:opacity-100 leading-none"
                                >×</button>
                              </span>
                            ))}
                            <div className="w-px h-3 bg-zinc-800 mx-0.5" />
                            {/* BB toggle */}
                            <button
                              title="Bollinger Bands (20-day, ±2σ)"
                              onClick={() => setOverlayBB(prev => !prev)}
                              className={clsx(
                                'px-2 py-0.5 text-[9px] rounded border transition-colors uppercase tracking-wider font-medium',
                                overlayBB
                                  ? 'border-blue-500 text-blue-300 bg-blue-950'
                                  : 'border-zinc-700 text-zinc-500 hover:text-zinc-300',
                              )}
                            >
                              BB
                            </button>
                          </div>
                        )}

                        <div className="w-px h-4 bg-zinc-800" />

                        <div className="flex items-center rounded-md border border-zinc-700 overflow-hidden">
                          <button
                            onClick={() => setChartType('candle')}
                            className={clsx(
                              'relative flex items-center gap-1 px-2 py-1 text-[10px] font-medium transition-colors',
                              chartType === 'candle' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'
                            )}
                          >
                            {chartType === 'candle' && (
                              <motion.span layoutId="chart-type-pill" transition={layoutSpring} className="absolute inset-0 bg-zinc-700 -z-10" />
                            )}
                            <CandleIcon size={11} />
                            Candle
                          </button>
                          <button
                            onClick={() => setChartType('area')}
                            className={clsx(
                              'relative flex items-center gap-1 px-2 py-1 text-[10px] font-medium transition-colors',
                              chartType === 'area' ? 'text-white' : 'text-zinc-500 hover:text-zinc-300'
                            )}
                          >
                            {chartType === 'area' && (
                              <motion.span layoutId="chart-type-pill" transition={layoutSpring} className="absolute inset-0 bg-zinc-700 -z-10" />
                            )}
                            <LineChartIcon size={11} />
                            Line
                          </button>
                        </div>
                      </div>
                    </div>
                    <div className="h-64">
                      {(() => {
                        const overlayConfig: OverlayConfig = { activeSMA, activeEMA, bb: overlayBB }
                        return chartType === 'candle'
                          ? <CandlestickChart data={enrichedChartData} days={days} overlays={overlayConfig} currencySymbol={currencySymbol} />
                          : <PriceChart data={enrichedChartData} days={days} overlays={overlayConfig} currencySymbol={currencySymbol} />
                      })()}
                    </div>
                  </div>

                  {/* RSI — its own collapsible block */}
                  {days > 0 && indicators?.rsi && (
                    <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                      <div
                        onClick={() => setSubCharts(prev => ({ ...prev, rsi: !prev.rsi }))}
                        className={clsx('flex items-center justify-between cursor-pointer', subCharts.rsi && 'mb-3')}
                      >
                        <p className="flex items-center gap-1.5 text-[10px] text-zinc-500 tracking-widest font-medium">
                          RSI ({indicators.rsi.period}) <InfoTip k="rsi" />
                        </p>
                        <div className="flex items-center gap-3">
                          {subCharts.rsi && (
                            <div className="flex items-center gap-3 text-[9px] font-mono text-zinc-600">
                              <span><span className="text-red-400/60">—</span> 70 overbought</span>
                              <span><span className="text-emerald-400/60">—</span> 30 oversold</span>
                            </div>
                          )}
                          <button
                            onClick={e => { e.stopPropagation(); setSubCharts(prev => ({ ...prev, rsi: !prev.rsi })) }}
                            title={subCharts.rsi ? 'Minimize' : 'Expand'}
                            className="p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors"
                          >
                            {subCharts.rsi ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          </button>
                        </div>
                      </div>
                      <AnimatePresence>
                        {subCharts.rsi && (
                          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
                            <div className="h-32">
                              <RSIChart data={indicators.rsi.values} days={days} />
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )}

                  {/* MACD — its own collapsible block */}
                  {days > 0 && indicators?.macd && (
                    <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                      <div
                        onClick={() => setSubCharts(prev => ({ ...prev, macd: !prev.macd }))}
                        className={clsx('flex items-center justify-between cursor-pointer', subCharts.macd && 'mb-3')}
                      >
                        <p className="flex items-center gap-1.5 text-[10px] text-zinc-500 tracking-widest font-medium">
                          MACD ({indicators.macd.fast}, {indicators.macd.slow}, {indicators.macd.signal_period}) <InfoTip k="macd" />
                        </p>
                        <div className="flex items-center gap-3">
                          {subCharts.macd && (
                            <div className="flex items-center gap-3 text-[9px] font-mono text-zinc-600">
                              <span><span className="text-blue-400">—</span> MACD</span>
                              <span><span className="text-orange-400">—</span> Signal</span>
                            </div>
                          )}
                          <button
                            onClick={e => { e.stopPropagation(); setSubCharts(prev => ({ ...prev, macd: !prev.macd })) }}
                            title={subCharts.macd ? 'Minimize' : 'Expand'}
                            className="p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors"
                          >
                            {subCharts.macd ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
                          </button>
                        </div>
                      </div>
                      <AnimatePresence>
                        {subCharts.macd && (
                          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
                            <div className="h-32">
                              <MACDChart data={indicators.macd.values} days={days} />
                            </div>
                          </motion.div>
                        )}
                      </AnimatePresence>
                    </div>
                  )}

                  <EarningsHistoryPanel
                    key={ticker}
                    epsHistory={epsHistory}
                    revenueHistory={revenueHistory}
                    currencySymbol={currencySymbol}
                  />

                  <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                    <p className="text-[10px] text-zinc-500 tracking-widest font-medium mb-3">
                      VOLUME ({volUnit(chartData)})
                    </p>
                    <div className="h-36">
                      <VolumeChart data={chartData} days={days} />
                    </div>
                  </div>

                  {/* Analyst section — only rendered once details arrive */}
                  {details && (
                    <AnalystPanel
                      targets={details.analyst_price_targets}
                      recommendations={details.recommendations_summary}
                      earningsEstimates={details.earnings_estimate}
                      revenueEstimates={details.revenue_estimate}
                      currentPrice={latest?.close}
                      format={fmt}
                      currencySymbol={currencySymbol}
                    />
                  )}

                  {/* Layered headlines: company → industry → market */}
                  <NewsPanel key={`news-${ticker}`} mode={{ kind: 'stock', ticker }} limit={10} />
                </>
              ) : null}
            </div>
          </main>
          )}
          </>}
        </div>
      )}
      </motion.div>
      </AnimatePresence>

      <Footer />

      {aiEnabled && showAIChat && <AIChatWidget context={aiChatContext} />}

      <AnimatePresence>
        {passwordRecovery && <PasswordRecoveryModal />}
      </AnimatePresence>

      <AnimatePresence>
        {deleteConfirm && (
          <motion.div
            variants={overlayFade}
            initial="hidden"
            animate="show"
            exit="exit"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-80 shadow-2xl">
              <h2 className="text-sm font-semibold text-zinc-100 mb-1">Remove {displayTicker(ticker)}?</h2>
              <p className="text-xs text-zinc-400 mb-5">
                {displayTicker(ticker)} will be removed from your watchlist. You can add it back at any time.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setDeleteConfirm(false)}
                  disabled={deleteLoading}
                  className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleteLoading}
                  className="px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors disabled:opacity-40 flex items-center gap-1.5"
                >
                  {deleteLoading ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={11} />}
                  Remove
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
