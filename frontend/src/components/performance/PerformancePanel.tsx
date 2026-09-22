import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import clsx from 'clsx'
import { AnimatePresence, motion } from 'motion/react'
import { Activity, AlertTriangle, ChevronDown, ChevronUp, RefreshCw, Scale, TrendingDown, TrendingUp } from 'lucide-react'
import { fetchPerformance } from '../../api'
import { formatMoney } from '../../utils/currency'
import { collapse, layoutSpring } from '../../lib/motion'
import { usePersistedState } from '../../utils/usePersistedState'
import type { Market, PerformanceRange, PerformanceResponse, ReturnSummary } from '../../types'
import { GrowthChart } from './GrowthChart'
import { ValueChart } from './ValueChart'
import { StatTile } from './StatTile'
import { InfoTip } from '../InfoTip'
import { FreshnessBadge } from '../FreshnessBadge'

const RANGES: Array<{ value: PerformanceRange; label: string }> = [
  { value: '1y', label: '1Y' },
  { value: '3y', label: '3Y' },
  { value: '5y', label: '5Y' },
  { value: 'max', label: 'Max' },
]

type ChartMode = 'growth' | 'value'

/** A percentage, or an em dash when the backend said "not answerable". */
function pct(value: number | null | undefined, opts: { sign?: boolean } = {}): string {
  if (value == null || Number.isNaN(value)) return '—'
  const asPct = value * 100
  const sign = opts.sign ? (asPct >= 0 ? '+' : '−') : asPct < 0 ? '−' : ''
  return `${sign}${Math.abs(asPct).toFixed(1)}%`
}

function toneOf(value: number | null | undefined): 'positive' | 'negative' | 'neutral' {
  if (value == null) return 'neutral'
  return value >= 0 ? 'positive' : 'negative'
}

function formatSpan(days: number): string {
  if (days < 60) return `${days} days`
  if (days < 730) return `${Math.round(days / 30.44)} months`
  return `${(days / 365).toFixed(1)} years`
}

/** The one-line verdict: money ahead of (or behind) simply buying the index.
 *
 * Falls back to plain profit when the index couldn't be priced. It used to
 * treat an unavailable benchmark as one worth $0, which turned "we have no
 * S&P data" into "you beat the S&P by your entire portfolio". */
function Verdict({ data }: { data: PerformanceResponse }) {
  const comparable = data.benchmark_available && data.value_added != null
  const headline = comparable ? data.value_added! : data.current_value - data.net_invested
  const ahead = headline >= 0
  const Icon = ahead ? TrendingUp : TrendingDown
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className={clsx(
        'rounded-xl border p-4',
        ahead ? 'border-emerald-500/25 bg-emerald-500/5' : 'border-red-500/25 bg-red-500/5',
      )}
    >
      <div className="flex items-start gap-3">
        <span className={clsx(
          'flex items-center justify-center w-9 h-9 rounded-lg shrink-0',
          ahead ? 'bg-emerald-500/15 text-emerald-400' : 'bg-red-500/15 text-red-400',
        )}>
          <Icon size={17} />
        </span>
        <div className="min-w-0">
          <p className="flex items-center gap-1 text-[0.625rem] tracking-widest text-zinc-500 font-medium">
            {comparable ? <>VS {data.benchmark_name.toUpperCase()} <InfoTip k="value_added" /></> : 'TOTAL GAIN'}
          </p>
          <p className={clsx(
            'mt-1 font-mono text-2xl sm:text-3xl tabular-nums',
            ahead ? 'text-emerald-400' : 'text-red-400',
          )}>
            {formatMoney(headline, data.currency, { sign: true })}
          </p>
          <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed">
            Your {formatMoney(data.net_invested, data.currency)} is worth{' '}
            <span className="text-zinc-200 font-mono">{formatMoney(data.current_value, data.currency)}</span>.
            {comparable ? (
              <>
                {' '}The same contributions in {data.benchmark_name} would be{' '}
                <span className="text-zinc-200 font-mono">{formatMoney(data.benchmark_final_value, data.currency)}</span>.
              </>
            ) : (
              <> {data.benchmark_name} history isn&rsquo;t available for this period, so there&rsquo;s
              nothing to compare against yet.</>
            )}
          </p>
        </div>
      </div>
    </motion.div>
  )
}

function SummaryRow({ label, summary, muted }: { label: string; summary: ReturnSummary; muted?: boolean }) {
  return (
    <div className="grid grid-cols-[1fr_auto_auto] sm:grid-cols-[1fr_auto_auto_auto] items-center gap-x-4 gap-y-1 py-2 text-xs font-mono">
      <span className={clsx('truncate', muted ? 'text-zinc-500' : 'text-zinc-200')}>{label}</span>
      <span className={clsx(
        'tabular-nums text-right w-16',
        summary.time_weighted == null ? 'text-zinc-600'
          : summary.time_weighted >= 0 ? 'text-emerald-400' : 'text-red-400',
      )}>
        {pct(summary.time_weighted, { sign: true })}
      </span>
      <span className="tabular-nums text-right w-16 text-zinc-400">{pct(summary.annualized, { sign: true })}</span>
      <span className="hidden sm:block tabular-nums text-right w-16 text-zinc-500">{pct(summary.max_drawdown)}</span>
    </div>
  )
}

interface Props {
  market: Market
  /** null covers every portfolio in the market, matching the "All" tab. */
  portfolioId: number | null
  guest?: boolean
}

/**
 * Portfolio performance against its market's benchmark index, as a
 * collapsible section of the Portfolio page.
 *
 * Scoped by the page's own market tab and portfolio tab rather than owning
 * switchers of its own — two sets of controls choosing the same thing on one
 * screen is how they end up disagreeing. Open by default: the comparison is
 * the point of the section, and a collapsed panel reads as an advert for
 * itself rather than an answer.
 *
 * Fetching is deliberately independent of the page's portfolio poll: this
 * payload only moves when a session closes or the user trades (which
 * invalidates it server-side), so it must not ride the two-minute live-price
 * refresh.
 */
export function PerformancePanel({ market, portfolioId, guest }: Props) {
  const [open, setOpen] = usePersistedState('portfolio-performance-open', true)
  const [range, setRange] = usePersistedState<PerformanceRange>('performance-range', 'max')
  const [chartMode, setChartMode] = usePersistedState<ChartMode>('performance-chart', 'growth')
  const [data, setData] = useState<PerformanceResponse | null>(null)
  // Read inside `load` so comparing against the previous result doesn't put
  // `data` in its dependency list and re-fetch on every response.
  const dataRef = useRef<PerformanceResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [retryNotice, setRetryNotice] = useState<string | null>(null)

  const load = useCallback(async (refresh = false) => {
    if (refresh) setRefreshing(true)
    else setLoading(true)
    setError(null)
    setRetryNotice(null)
    try {
      const before = dataRef.current?.excluded_tickers ?? []
      const result = await fetchPerformance(market, portfolioId, range, refresh)
      setData(result)
      // A refresh that leaves the same holdings unarchived has silently done
      // nothing, and the user is left clicking a button that looks broken.
      // Say so instead.
      if (refresh && result.excluded_tickers.length > 0
          && result.excluded_tickers.join() === before.join()) {
        setRetryNotice(
          `Couldn't fetch price history for ${result.excluded_tickers.join(', ')} just now. `
          + 'The market-data provider may be rate-limiting — try again in a minute.',
        )
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load performance')
      // A failed refresh keeps whatever is already on screen — losing a good
      // chart because a retry timed out would be a strictly worse outcome.
      if (!refresh) setData(null)
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [market, portfolioId, range])

  // Collapsed means not fetched: this is the most expensive thing on the
  // page to compute, and a user who folded it away has said they don't want
  // it. It loads on the first expand and whenever the scope changes after.
  useEffect(() => {
    if (!open) return
    load()
  }, [load, open])

  useEffect(() => { dataRef.current = data }, [data])

  const excluded = data?.excluded_tickers ?? []
  const hasBenchmark = data?.benchmark_available ?? false

  const tiles = useMemo(() => {
    if (!data) return []
    return [
      {
        label: 'Money-weighted return',
        value: pct(data.portfolio.money_weighted, { sign: true }),
        detail: 'per year, your timing included',
        tone: toneOf(data.portfolio.money_weighted),
        glossary: 'xirr' as const,
        emphasis: true,
      },
      {
        label: `${data.benchmark_name} equivalent`,
        value: pct(data.benchmark.money_weighted, { sign: true }),
        detail: data.benchmark_available
          ? 'same money, same days, in the index'
          : 'index history unavailable',
        tone: toneOf(data.benchmark.money_weighted),
        glossary: 'benchmark_equivalent' as const,
      },
      {
        label: 'Annualized return',
        value: pct(data.portfolio.annualized, { sign: true }),
        detail: `time-weighted · ${formatSpan(data.days)}`,
        tone: toneOf(data.portfolio.annualized),
        glossary: 'cagr' as const,
      },
      {
        label: 'Max drawdown',
        value: pct(data.portfolio.max_drawdown),
        detail: data.benchmark_available
          ? `${data.benchmark_name} ${pct(data.benchmark.max_drawdown)}` : undefined,
        tone: 'neutral' as const,
        glossary: 'max_drawdown' as const,
      },
      {
        label: 'Volatility',
        value: pct(data.portfolio.volatility),
        detail: data.benchmark_available
          ? `${data.benchmark_name} ${pct(data.benchmark.volatility)}` : undefined,
        tone: 'neutral' as const,
        glossary: 'volatility' as const,
      },
      {
        label: 'Beta',
        value: data.beta == null ? '—' : data.beta.toFixed(2),
        detail: data.benchmark_available
          ? `sensitivity to ${data.benchmark_name}` : 'index history unavailable',
        tone: 'neutral' as const,
        glossary: 'beta' as const,
      },
    ]
  }, [data])

  // The headline the collapsed state carries, so folding the panel away
  // doesn't hide the one number it exists to report. Falls back to plain
  // profit when the index couldn't be priced — quoting a "vs S&P 500" figure
  // that was never measured against the S&P is worse than quoting nothing.
  const headlineValue = data && !data.insufficient_data
    ? (data.benchmark_available && data.value_added != null
        ? data.value_added
        : data.current_value - data.net_invested)
    : null
  const summary = data && !data.insufficient_data && headlineValue != null
    ? `${formatMoney(headlineValue, data.currency, { sign: true, compact: true })}`
      + (data.benchmark_available ? ` vs ${data.benchmark_name}` : ' total gain')
    : null

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-5">
      <div
        onClick={() => setOpen(o => !o)}
        className={clsx(
          'flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.625rem] font-semibold tracking-widest text-zinc-500 cursor-pointer',
          open && 'mb-3',
        )}
      >
        PERFORMANCE <InfoTip k="xirr" />
        {open && (
          <span onClick={e => e.stopPropagation()} className="normal-case tracking-normal">
            <FreshnessBadge path="/performance/" align="left" />
          </span>
        )}
        {!open && summary && (
          <span className={clsx(
            'ml-auto font-mono normal-case tracking-normal',
            (headlineValue ?? 0) >= 0 ? 'text-emerald-400' : 'text-red-400',
          )}>
            {summary}
          </span>
        )}
        {/* Reload. Does more than re-fetch: it asks the server to archive any
            holding that has no price history yet, which is the only way a
            ticker whose first backfill failed ever gets one. Tinted amber
            while something is missing, so the fix is where the problem is. */}
        {open && (
          <button
            onClick={e => { e.stopPropagation(); load(true) }}
            disabled={refreshing}
            title={excluded.length > 0
              ? `Reload and fetch missing price history (${excluded.join(', ')})`
              : 'Reload performance'}
            aria-label="Reload performance"
            className={clsx(
              'tap-target ml-auto p-1.5 sm:p-1 rounded-lg transition-colors disabled:opacity-40',
              excluded.length > 0
                ? 'text-amber-400 hover:text-amber-300 hover:bg-zinc-800'
                : 'text-zinc-600 hover:text-zinc-300 hover:bg-zinc-800',
            )}
          >
            <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          </button>
        )}
        <button
          onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
          title={open ? 'Minimize' : 'Expand'}
          aria-label={open ? 'Minimize performance' : 'Expand performance'}
          className={clsx(
            'tap-target p-1.5 sm:p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors',
            !open && !summary && 'ml-auto',
          )}
        >
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
            {error ? (
              <p className="text-xs text-red-300 py-3">{error}</p>
            ) : loading && !data ? (
              <div className="space-y-3">
                <div className="h-24 rounded-xl bg-zinc-800 animate-pulse" />
                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  {Array.from({ length: 6 }).map((_, i) => (
                    <div key={i} className="h-20 rounded-xl bg-zinc-800 animate-pulse" />
                  ))}
                </div>
                <div className="h-64 rounded-xl bg-zinc-800 animate-pulse" />
              </div>
            ) : !data || data.insufficient_data ? (
              <EmptyState
                guest={guest}
                market={market}
                excluded={excluded}
                staleArchive={data?.stale_archive ?? false}
                refreshing={refreshing}
                onRetry={() => load(true)}
              />
            ) : (
              <div className="space-y-4">
                <Verdict data={data} />

                <div className="grid grid-cols-2 lg:grid-cols-3 gap-3">
                  {tiles.map((tile, i) => (
                    <StatTile key={tile.label} index={i} {...tile} />
                  ))}
                </div>

                <div className="rounded-xl border border-zinc-800 p-3 sm:p-4">
                  <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
                    <div className="flex rounded-lg overflow-hidden border border-zinc-800">
                      {([
                        { value: 'growth' as ChartMode, label: 'Return', icon: Activity },
                        { value: 'value' as ChartMode, label: 'Money', icon: Scale },
                      ]).map(({ value, label, icon: Icon }) => (
                        <button
                          key={value}
                          onClick={() => setChartMode(value)}
                          className={clsx(
                            'relative flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium transition-colors',
                            chartMode === value ? 'text-white' : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300',
                          )}
                        >
                          {chartMode === value && (
                            <motion.span
                              layoutId="performance-chart-pill"
                              transition={layoutSpring}
                              className="absolute inset-0 bg-indigo-600 -z-10"
                            />
                          )}
                          <Icon size={11} />
                          {label}
                        </button>
                      ))}
                    </div>

                    <div className="flex rounded-lg overflow-hidden border border-zinc-800">
                      {RANGES.map(({ value, label }) => (
                        <button
                          key={value}
                          onClick={() => setRange(value)}
                          className={clsx(
                            'relative px-3 py-1.5 text-xs font-mono transition-colors',
                            range === value ? 'text-white' : 'text-zinc-500 hover:bg-zinc-800 hover:text-zinc-300',
                          )}
                        >
                          {range === value && (
                            <motion.span
                              layoutId="performance-range-pill"
                              transition={layoutSpring}
                              className="absolute inset-0 bg-indigo-600 -z-10"
                            />
                          )}
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  <div className="h-[16rem] sm:h-[20rem]">
                    {chartMode === 'growth' ? (
                      <GrowthChart
                        points={data.points}
                        days={data.days}
                        benchmarkName={data.benchmark_name}
                        benchmarkAvailable={hasBenchmark}
                      />
                    ) : (
                      <ValueChart
                        points={data.points}
                        days={data.days}
                        currency={data.currency}
                        benchmarkName={data.benchmark_name}
                        benchmarkAvailable={hasBenchmark}
                      />
                    )}
                  </div>

                  <div className="mt-4 pt-4 border-t border-zinc-800">
                    <div className="grid grid-cols-[1fr_auto_auto] sm:grid-cols-[1fr_auto_auto_auto] gap-x-4 text-[0.625rem] tracking-widest text-zinc-600 font-medium pb-1 border-b border-zinc-800">
                      <span />
                      <span className="text-right w-16">TOTAL</span>
                      <span className="text-right w-16">PER YEAR</span>
                      <span className="hidden sm:block text-right w-16">MAX DD</span>
                    </div>
                    <SummaryRow label="Portfolio" summary={data.portfolio} />
                    {hasBenchmark && (
                      <SummaryRow label={data.benchmark_name} summary={data.benchmark} muted />
                    )}
                  </div>
                </div>

                {retryNotice && (
                  <p className="flex items-start gap-2 text-xs text-red-300/90">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                    <span>{retryNotice}</span>
                  </p>
                )}
                {excluded.length > 0 && (
                  <div className="flex flex-wrap items-center gap-2 text-xs text-amber-300/80">
                    <AlertTriangle size={13} className="shrink-0" />
                    <span>
                      Not included — no price history archived yet:{' '}
                      <span className="font-mono">{excluded.join(', ')}</span>
                    </span>
                    <button
                      onClick={() => load(true)}
                      disabled={refreshing}
                      className="ml-auto shrink-0 flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-amber-500/30 hover:bg-amber-500/10 text-amber-300 transition-colors disabled:opacity-40"
                    >
                      <RefreshCw size={11} className={refreshing ? 'animate-spin' : ''} />
                      {refreshing ? 'Fetching…' : 'Fetch now'}
                    </button>
                  </div>
                )}
                <p className="text-[0.6875rem] text-zinc-600 leading-relaxed">
                  Priced to the close on {data.end_date}, from the price archive rather than the
                  live quotes above.{' '}
                  {hasBenchmark
                    ? `The ${data.benchmark_name} comparison tracks the index level only, so it excludes index dividends and will read slightly low over long periods. `
                    : `${data.benchmark_name} history isn't available for this window, so no comparison is shown. `}
                  Contributions are assumed to land at the end of their day.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

interface EmptyStateProps {
  guest?: boolean
  market: Market
  excluded: string[]
  /** The chart is empty because prices haven't been archived yet, not
   *  because there are no positions. Very different message. */
  staleArchive: boolean
  refreshing: boolean
  onRetry: () => void
}

function EmptyState({ guest, market, excluded, staleArchive, refreshing, onRetry }: EmptyStateProps) {
  const title = guest
    ? 'Sign in to track performance'
    : staleArchive
      ? 'Catching up on price history'
      : 'Not enough history yet'

  return (
    <div className="py-6 text-center">
      <p className="text-sm text-zinc-400">{title}</p>
      <p className="mt-2 text-xs text-zinc-500 max-w-md mx-auto leading-relaxed">
        {guest
          ? 'Guest portfolios live only in this browser tab, so there is no transaction history to measure a return against. Create an account and your buys and sells build this chart as you go.'
          : staleArchive
            ? 'Daily prices for your positions are still being downloaded — this happens the first time you hold a stock over a weekend or a market holiday. Refresh in a moment and the chart will draw itself.'
            : `Record a buy in your ${market === 'IN' ? 'India' : 'US'} portfolio and this starts plotting it against the benchmark. It needs at least two days of archived prices to draw a line.`}
      </p>
      {excluded.length > 0 && (
        <p className="mt-3 text-xs text-amber-300/80">
          Waiting on price history for <span className="font-mono">{excluded.join(', ')}</span>.
        </p>
      )}
      {/* The empty state is the one place a user can be stuck with nothing to
          click, so the retry lives here too rather than only in the header. */}
      {!guest && (excluded.length > 0 || staleArchive) && (
        <button
          onClick={onRetry}
          disabled={refreshing}
          className="mt-4 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800 text-xs text-zinc-300 transition-colors disabled:opacity-40"
        >
          <RefreshCw size={12} className={refreshing ? 'animate-spin' : ''} />
          {refreshing ? 'Fetching price history…' : 'Fetch price history now'}
        </button>
      )}
    </div>
  )
}
