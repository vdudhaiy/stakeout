import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PerformancePoint } from '../../types'
import { axisDecimals, computeXTicks, thinTicks, xTickFormatter } from '../../utils/chart'

// Enough to orient, few enough that the labels never collide at phone width.
const MAX_TICKS = 6

interface Props {
  points: PerformancePoint[]
  days: number
  benchmarkName: string
  /** False when the index couldn't be priced. The benchmark series is then
   *  all-zero filler and must not be drawn — a flat line at 0% reads as "the
   *  index went nowhere", which is a claim nobody measured. */
  benchmarkAvailable: boolean
}

const PORTFOLIO_COLOR = '#818cf8'  // indigo — remapped to brass by the Tailwind config
const BENCHMARK_COLOR = '#71717a'  // muted: the benchmark is the reference, not the subject

function pct(indexValue: number): string {
  const change = indexValue - 100
  return `${change >= 0 ? '+' : '−'}${Math.abs(change).toFixed(1)}%`
}

function GrowthTooltip({ active, payload, benchmarkName, benchmarkAvailable }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as PerformancePoint
  const lead = d.portfolio_index - d.benchmark_index
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs font-mono">
      <p className="text-zinc-400 mb-2">{d.date}</p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-1">
        <span style={{ color: PORTFOLIO_COLOR }}>Portfolio</span>
        <span className="text-zinc-100 text-right">{pct(d.portfolio_index)}</span>
        {benchmarkAvailable && <>
          <span className="text-zinc-400">{benchmarkName}</span>
          <span className="text-zinc-300 text-right">{pct(d.benchmark_index)}</span>
        </>}
      </div>
      {benchmarkAvailable && (
        <div className="mt-2 pt-2 border-t border-zinc-800 flex justify-between gap-4">
          <span className="text-zinc-500">Ahead by</span>
          <span className={lead >= 0 ? 'text-emerald-400' : 'text-red-400'}>
            {lead >= 0 ? '+' : '−'}{Math.abs(lead).toFixed(1)} pts
          </span>
        </div>
      )}
    </div>
  )
}

/**
 * Growth of the portfolio against its benchmark, both rebased to 100 at the
 * start of the window.
 *
 * Rebasing is what makes the two lines comparable at all: the portfolio
 * series has had contributions stripped out of it server-side (see
 * returns_math.daily_returns), so every divergence here is return, not
 * deposits. Plotting raw money against index points would just draw the
 * user's savings rate.
 */
export function GrowthChart({ points, days, benchmarkName, benchmarkAvailable }: Props) {
  if (points.length < 2) return null

  const ticks = thinTicks(computeXTicks(points.map(p => p.date), days), MAX_TICKS)
  const all = benchmarkAvailable
    ? points.flatMap(p => [p.portfolio_index, p.benchmark_index])
    : points.map(p => p.portfolio_index)
  const min = Math.min(...all, 100)
  const max = Math.max(...all, 100)
  const pad = (max - min) * 0.08 || 5
  const decimals = axisDecimals(max - min)
  // A handful of points drawn as a spline invents a smooth trend between
  // days that were never measured. Straight segments with visible dots say
  // what the data actually is.
  const sparse = points.length <= 10
  const curve = sparse ? 'linear' : 'monotone'

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="growthGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={PORTFOLIO_COLOR} stopOpacity={0.18} />
            <stop offset="95%" stopColor={PORTFOLIO_COLOR} stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          ticks={ticks}
          interval={0}
          tickFormatter={v => xTickFormatter(v, days)}
        />
        <YAxis
          domain={[min - pad, max + pad]}
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={54}
          tickFormatter={v => `${((v as number) - 100).toFixed(decimals)}%`}
        />
        <Tooltip content={
          <GrowthTooltip benchmarkName={benchmarkName} benchmarkAvailable={benchmarkAvailable} />
        } />
        {/* Break-even: the line the whole chart is read against. */}
        <ReferenceLine y={100} stroke="#3f3f46" strokeDasharray="4 4" />
        <Area
          type={curve}
          dataKey="portfolio_index"
          stroke={PORTFOLIO_COLOR}
          strokeWidth={1.8}
          fill="url(#growthGradient)"
          dot={sparse ? { r: 2.5, strokeWidth: 0, fill: PORTFOLIO_COLOR } : false}
          isAnimationActive={false}
          activeDot={{ r: 3, strokeWidth: 0, fill: PORTFOLIO_COLOR }}
          name="Portfolio"
        />
        {benchmarkAvailable && (
          <Line
            type={curve}
            dataKey="benchmark_index"
            stroke={BENCHMARK_COLOR}
            strokeWidth={1.4}
            strokeDasharray="5 3"
            dot={false}
            isAnimationActive={false}
            activeDot={{ r: 3, strokeWidth: 0, fill: BENCHMARK_COLOR }}
            name={benchmarkName}
          />
        )}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
