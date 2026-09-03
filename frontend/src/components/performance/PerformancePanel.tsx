import { useCallback, useEffect, useMemo, useState } from 'react'
import clsx from 'clsx'
import { AnimatePresence, motion } from 'motion/react'
import { Activity, AlertTriangle, ChevronDown, ChevronUp, Scale, TrendingDown, TrendingUp } from 'lucide-react'
import { fetchPerformance } from '../../api'
import { formatMoney } from '../../utils/currency'
import { collapse, layoutSpring } from '../../lib/motion'
import { usePersistedState } from '../../utils/usePersistedState'
import type { Market, PerformanceRange, PerformanceResponse, ReturnSummary } from '../../types'
import { GrowthChart } from './GrowthChart'
import { ValueChart } from './ValueChart'
import { StatTile } from './StatTile'
import { InfoTip } from '../InfoTip'

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

/** The one-line verdict: money ahead of (or behind) simply buying the index. */
function Verdict({ data }: { data: PerformanceResponse }) {
  const ahead = data.value_added >= 0
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
            VS {data.benchmark_name.toUpperCase()} <InfoTip k="value_added" />
          </p>
          <p className={clsx(
            'mt-1 font-mono text-2xl sm:text-3xl tabular-nums',
            ahead ? 'text-emerald-400' : 'text-red-400',
          )}>
            {formatMoney(data.value_added, data.currency, { sign: true })}
          </p>
          <p className="mt-1.5 text-xs text-zinc-400 leading-relaxed">
            Your {formatMoney(data.net_invested, data.currency)} is worth{' '}
            <span className="text-zinc-200 font-mono">{formatMoney(data.current_value, data.currency)}</span>.
            The same contributions in {data.benchmark_name} would be{' '}
            <span className="text-zinc-200 font-mono">{formatMoney(data.benchmark_final_value, data.currency)}</span>.
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
      <span className={clsx('tabular-nums text-right w-16', toneOf(summary.time_weighted) === 'positive' ? 'text-emerald-400' : 'text-red-400')}>
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
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setData(await fetchPerformance(market, portfolioId, range))
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load performance')
      setData(null)
    } finally {
      setLoading(false)
    }
  }, [market, portfolioId, range])

  // Collapsed means not fetched: this is the most expensive thing on the
  // page to compute, and a user who folded it away has said they don't want
  // it. It loads on the first expand and whenever the scope changes after.
  useEffect(() => {
    if (!open) return
    load()
  }, [load, open])

  const excluded = data?.excluded_tickers ?? []

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
        detail: 'same money, same days, in the index',
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
        detail: `${data.benchmark_name} ${pct(data.benchmark.max_drawdown)}`,
        tone: 'neutral' as const,
        glossary: 'max_drawdown' as const,
      },
      {
        label: 'Volatility',
        value: pct(data.portfolio.volatility),
        detail: `${data.benchmark_name} ${pct(data.benchmark.volatility)}`,
        tone: 'neutral' as const,
        glossary: 'volatility' as const,
      },
      {
        label: 'Beta',
        value: data.beta == null ? '—' : data.beta.toFixed(2),
        detail: `sensitivity to ${data.benchmark_name}`,
        tone: 'neutral' as const,
        glossary: 'beta' as const,
      },
    ]
  }, [data])

  // The headline the collapsed state carries, so folding the panel away
  // doesn't hide the one number it exists to report.
  const summary = data && !data.insufficient_data
    ? `${formatMoney(data.value_added, data.currency, { sign: true, compact: true })} vs ${data.benchmark_name}`
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
        {!open && summary && (
          <span className={clsx(
            'ml-auto font-mono normal-case tracking-normal',
            data && data.value_added >= 0 ? 'text-emerald-400' : 'text-red-400',
          )}>
            {summary}
          </span>
        )}
        <button
          onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
          title={open ? 'Minimize' : 'Expand'}
          aria-label={open ? 'Minimize performance' : 'Expand performance'}
          className={clsx(
            'tap-target p-1.5 sm:p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors',
            (open || !summary) && 'ml-auto',
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
              <EmptyState guest={guest} market={market} excluded={excluded} />
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
                      <GrowthChart points={data.points} days={data.days} benchmarkName={data.benchmark_name} />
                    ) : (
                      <ValueChart
                        points={data.points}
                        days={data.days}
                        currency={data.currency}
                        benchmarkName={data.benchmark_name}
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
                    <SummaryRow label={data.benchmark_name} summary={data.benchmark} muted />
                  </div>
                </div>

                {excluded.length > 0 && (
                  <p className="flex items-start gap-2 text-xs text-amber-300/80">
                    <AlertTriangle size={13} className="shrink-0 mt-0.5" />
                    <span>
                      Not included — no price history archived yet:{' '}
                      <span className="font-mono">{excluded.join(', ')}</span>
                    </span>
                  </p>
                )}
                <p className="text-[0.6875rem] text-zinc-600 leading-relaxed">
                  Priced to the close on {data.end_date}, from the price archive rather than the
                  live quotes above. The {data.benchmark_name} comparison tracks the index level
                  only, so it excludes index dividends and will read slightly low over long
                  periods. Contributions are assumed to land at the end of their day.
                </p>
              </div>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

function EmptyState({ guest, market, excluded }: { guest?: boolean; market: Market; excluded: string[] }) {
  return (
    <div className="py-6 text-center">
      <p className="text-sm text-zinc-400">
        {guest ? 'Sign in to track performance' : 'Not enough history yet'}
      </p>
      <p className="mt-2 text-xs text-zinc-500 max-w-md mx-auto leading-relaxed">
        {guest
          ? 'Guest portfolios live only in this browser tab, so there is no transaction history to measure a return against. Create an account and your buys and sells build this chart as you go.'
          : `Record a buy in your ${market === 'IN' ? 'India' : 'US'} portfolio and this starts plotting it against the benchmark. It needs at least two days of archived prices to draw a line.`}
      </p>
      {excluded.length > 0 && (
        <p className="mt-3 text-xs text-amber-300/80">
          Waiting on price history for <span className="font-mono">{excluded.join(', ')}</span>.
        </p>
      )}
    </div>
  )
}
