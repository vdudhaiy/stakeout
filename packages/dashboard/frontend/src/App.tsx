import { useState, useEffect, useCallback, useRef } from 'react'
import clsx from 'clsx'
import { TrendingUp, TrendingDown, RefreshCw, Info, Trash2 } from 'lucide-react'
import { Navbar } from './components/Navbar'
import { HomePage } from './components/HomePage'
import { HealthDashboard } from './components/HealthDashboard'
import { TickerSidebar } from './components/TickerSidebar'
import { ComparisonView } from './components/ComparisonView'
import { PriceChart } from './components/PriceChart'
import { VolumeChart, volUnit } from './components/VolumeChart'
import { OHLCVStats } from './components/OHLCVStats'
import { StockInfoCard } from './components/StockInfoCard'
import { AnalystPanel } from './components/AnalystPanel'
import { EarningsHistoryPanel } from './components/EarningsHistoryPanel'
import { fetchAllStocks, fetchCurrentStock, fetchHealth, fetchIntradayStock, fetchMarketStatus, fetchStock, fetchStockDashboard, deleteStock } from './api'
import { parseEtDateStr, fmtHHMMWithTz, etToLocalHHMM, localTzAbbr, formatEtDate, formatLocalDate } from './utils/time'
import type { OHLCV, HealthInfo, LatencyRecord, View, StockDetails, StockMap, ComparisonGroup, EPSHistoryRow, RevenueHistoryRow } from './types'

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

const MAX_HISTORY = 50

export default function App() {
  const [view, setView] = useState<View>('home')
  const [ticker, setTicker] = useState('')
  const [allTickers, setAllTickers] = useState<StockMap | null>(null)
  const [days, setDays] = useState(30)
  const [data, setData] = useState<OHLCV[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [details, setDetails] = useState<StockDetails | null>(null)
  const [comparisonGroup, setComparisonGroup] = useState<ComparisonGroup | null>(null)
  const [health, setHealth] = useState<HealthInfo>({ status: 'loading', latencyMs: null })
  const [lastChecked, setLastChecked] = useState<Date | null>(null)
  const [latencyHistory, setLatencyHistory] = useState<LatencyRecord[]>([])
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null)
  const [currentData, setCurrentData] = useState<OHLCV | null>(null)
  const [currentFetchedAt, setCurrentFetchedAt] = useState<Date | null>(null)
  const [currentLoading, setCurrentLoading] = useState(false)
  const [showMarketHours, setShowMarketHours] = useState(false)
  const [epsHistory, setEpsHistory] = useState<EPSHistoryRow[] | null>(null)
  const [revenueHistory, setRevenueHistory] = useState<RevenueHistoryRow[] | null>(null)
  const [intradayData, setIntradayData] = useState<OHLCV[] | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState(false)
  const [deleteLoading, setDeleteLoading] = useState(false)

  useEffect(() => {
    const check = () =>
      fetchHealth().then(info => {
        const now = new Date()
        setHealth(info)
        setLastChecked(now)
        setLatencyHistory(prev => {
          const record: LatencyRecord = {
            time: now.toLocaleTimeString(),
            latencyMs: info.latencyMs,
            status: info.status,
          }
          const next = [...prev, record]
          return next.length > MAX_HISTORY ? next.slice(next.length - MAX_HISTORY) : next
        })
      })
    check()
    const id = setInterval(check, 30_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const check = () => fetchMarketStatus().then(setMarketOpen)
    check()
    const id = setInterval(check, 60_000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    fetchAllStocks().then(setAllTickers).catch(() => setAllTickers({}))
  }, [])

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

    if (!marketOpen) return
    const id = setInterval(loadCurrent, 2 * 60_000)
    return () => clearInterval(id)
  }, [ticker, marketOpen, loadCurrent])

  // Pre-market: date string contains 'T' (e.g. "2026-06-09T07:30") vs plain "2026-06-09"
  const isPreMarket = !marketOpen && (currentData?.date?.includes('T') ?? false)

  useEffect(() => {
    if (!isPreMarket) return
    const id = setInterval(loadCurrent, 2 * 60_000)
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

  // Tracks which ticker was last loaded so we know whether to fetch details too
  const prevTicker = useRef<string>('')
  // Incremented on every load; stale responses from aborted loads are ignored
  const loadGen = useRef(0)
  const infoRef = useRef<HTMLDivElement>(null)
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
    }

    // When in 1D mode, fetch regular daily data at 30D for header metrics
    const effectiveDays = days === 0 ? 30 : days

    try {
      if (isNewTicker) {
        const [dashboardRes, intradayRes] = await Promise.all([
          fetchStockDashboard(ticker, effectiveDays),
          days === 0 ? fetchIntradayStock(ticker).catch(() => null) : Promise.resolve(null),
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
      } else if (days === 0) {
        // Switching into 1D mode — only fetch intraday, keep existing daily data for header
        const intradayRes = await fetchIntradayStock(ticker)
        if (gen !== loadGen.current) return
        setIntradayData(intradayRes.data)
      } else {
        // Only days changed — details are still valid
        const ohlcvRes = await fetchStock(ticker, days)
        if (gen !== loadGen.current) return
        setData(ohlcvRes.data)
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
  const displayData = marketOpen !== false ? data.filter(d => d.date !== today) : data

  // For charts: use intraday data in 1D mode, otherwise the regular daily series
  const chartData = days === 0 ? (intradayData ?? []) : displayData

  const latest = displayData[displayData.length - 1]
  const prev = displayData[displayData.length - 2]

  // Last complete trading day (archive)
  const archiveClose = latest?.close ?? null
  const archiveChange = archiveClose != null && prev?.close != null ? archiveClose - prev.close : null
  const archiveChangePct = archiveChange != null && prev?.close ? (archiveChange / prev.close) * 100 : null

  // Live intraday price — only valid while market is open
  const liveClose = marketOpen ? (currentData?.close ?? null) : null
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

  // OHLCV stats block source and its baseline for change calculation
  const mainOHLCV = marketOpen ? currentData : latest
  const mainOHLCVPrevClose = marketOpen ? archiveClose : (prev?.close ?? null)

  const displayName = details?.info?.displayName as string | undefined
  const shortName = details?.info?.shortName as string | undefined
  const primaryName = displayName ?? shortName

  return (
    <div className="flex flex-col h-screen bg-zinc-950 text-zinc-100 overflow-hidden">
      <Navbar view={view} onViewChange={setView} healthStatus={health.status} marketOpen={marketOpen} />

      {view === 'home' ? (
        <HomePage onNavigate={setView} />
      ) : view === 'health' ? (
        <HealthDashboard
          status={health.status}
          latencyMs={health.latencyMs}
          lastChecked={lastChecked}
          history={latencyHistory}
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
            <ComparisonView group={comparisonGroup} onBack={() => setComparisonGroup(null)} marketOpen={marketOpen} tickerNames={allTickers ?? {}} />
          ) : (
          <main className="flex-1 overflow-y-auto p-6 min-w-0">
            <div className="flex flex-col gap-5 max-w-6xl">
              {/* Ticker header row */}
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-baseline gap-3 flex-wrap">
                    <h1 className="text-2xl font-bold tracking-tight">
                      {primaryName ?? ticker}
                      {primaryName && (
                        <span className="text-zinc-500 font-normal text-lg ml-2">({ticker})</span>
                      )}
                    </h1>

                    {/* Primary price: archive close (or live when market open) */}
                    {headerPrice != null && (
                      <span className="font-mono text-xl font-semibold text-zinc-100">
                        ${headerPrice.toFixed(2)}
                      </span>
                    )}
                    {headerChange !== null && (
                      <span className={clsx(
                        'flex items-center gap-1 text-sm font-mono',
                        headerChange >= 0 ? 'text-emerald-400' : 'text-red-400',
                      )}>
                        {headerChange >= 0 ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                        {headerChange >= 0 ? '+' : ''}{headerChange.toFixed(2)} ({headerChange >= 0 ? '+' : ''}{headerChangePct!.toFixed(2)}%)
                      </span>
                    )}

                  </div>

                  {(latest ?? currentData) && (
                    <div className="flex items-center gap-1.5 mt-1">
                      <p className="text-zinc-500 text-xs">
                        {marketOpen && currentFetchedAt
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
                          'px-3 py-1.5 text-xs font-medium transition-colors',
                          days === value
                            ? 'bg-indigo-600 text-white'
                            : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                        )}
                      >
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
                    title={`Delete ${ticker}`}
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
                    ${preMarketClose.toFixed(2)}
                  </span>
                  {preMarketChange != null && (
                    <span className={clsx(
                      'flex items-center gap-1 text-sm font-mono',
                      preMarketChange >= 0 ? 'text-emerald-400' : 'text-red-400',
                    )}>
                      {preMarketChange >= 0 ? <TrendingUp size={12} /> : <TrendingDown size={12} />}
                      {preMarketChange >= 0 ? '+' : ''}{preMarketChange.toFixed(2)} ({preMarketChange >= 0 ? '+' : ''}{preMarketChangePct!.toFixed(2)}%)
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
                      {showMarketHours && (
                        <div className="absolute right-0 top-6 z-50 w-72 bg-zinc-950 border border-zinc-700 rounded-xl p-4 shadow-2xl">
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
                        </div>
                      )}
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
                />
              )}

              {/* Company info (sector / industry / summary) */}
              {details?.info && <StockInfoCard info={details.info} />}

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
                    Loading {ticker}...
                  </div>
                </div>
              ) : chartData.length > 0 ? (
                <>
                  <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
                    <div className="flex items-center justify-between mb-3">
                      <p className="text-[10px] text-zinc-500 tracking-widest font-medium">
                        CLOSE PRICE
                      </p>
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
                    </div>
                    <div className="h-64">
                      <PriceChart data={chartData} days={days} />
                    </div>
                  </div>

                  <EarningsHistoryPanel
                    key={ticker}
                    epsHistory={epsHistory}
                    revenueHistory={revenueHistory}
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
                    />
                  )}
                </>
              ) : null}
            </div>
          </main>
          )}
          </>}
        </div>
      )}
      {deleteConfirm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-6 w-80 shadow-2xl">
            <h2 className="text-sm font-semibold text-zinc-100 mb-1">Delete {ticker}?</h2>
            <p className="text-xs text-zinc-400 mb-5">
              All archived data for {ticker} will be removed. This cannot be undone.
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
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
