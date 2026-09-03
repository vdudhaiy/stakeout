import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { PerformancePoint } from '../../types'
import { computeXTicks, thinTicks, xTickFormatter } from '../../utils/chart'
import { formatMoney, type Currency } from '../../utils/currency'

// Enough to orient, few enough that the labels never collide at phone width.
const MAX_TICKS = 6

interface Props {
  points: PerformancePoint[]
  days: number
  currency: Currency
  benchmarkName: string
  /** False when the index couldn't be priced — `benchmark_value` is then a
   *  flat zero series, and drawing it claims the index was worth nothing. */
  benchmarkAvailable: boolean
}

const VALUE_COLOR = '#818cf8'
const INVESTED_COLOR = '#52525b'
const BENCHMARK_COLOR = '#f59e0b'

function ValueTooltip({ active, payload, currency, benchmarkName, benchmarkAvailable }: any) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload as PerformancePoint
  const gain = d.value - d.invested
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs font-mono">
      <p className="text-zinc-400 mb-2">{d.date}</p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-1">
        <span style={{ color: VALUE_COLOR }}>Value</span>
        <span className="text-zinc-100 text-right">{formatMoney(d.value, currency, { compact: true })}</span>
        <span className="text-zinc-500">Invested</span>
        <span className="text-zinc-300 text-right">{formatMoney(d.invested, currency, { compact: true })}</span>
        {benchmarkAvailable && <>
          <span style={{ color: BENCHMARK_COLOR }}>In {benchmarkName}</span>
          <span className="text-zinc-300 text-right">{formatMoney(d.benchmark_value, currency, { compact: true })}</span>
        </>}
      </div>
      <div className="mt-2 pt-2 border-t border-zinc-800 flex justify-between gap-4">
        <span className="text-zinc-500">Gain</span>
        <span className={gain >= 0 ? 'text-emerald-400' : 'text-red-400'}>
          {formatMoney(gain, currency, { compact: true, sign: true })}
        </span>
      </div>
    </div>
  )
}

/**
 * The same story in money rather than percentages: what the portfolio is
 * worth, what was actually paid in, and what that identical sequence of
 * payments would be worth in the benchmark instead.
 *
 * The gap between value and invested is profit; the gap between value and
 * the benchmark line is the part attributable to picking these holdings over
 * the index. Two charts rather than one because the percentage view answers
 * "did I beat it?" and this one answers "by how much money?" — and a single
 * axis can't carry both without one of them becoming unreadable.
 */
export function ValueChart({ points, days, currency, benchmarkName, benchmarkAvailable }: Props) {
  if (points.length < 2) return null

  const ticks = thinTicks(computeXTicks(points.map(p => p.date), days), MAX_TICKS)
  const all = points.flatMap(p => benchmarkAvailable
    ? [p.value, p.invested, p.benchmark_value]
    : [p.value, p.invested])
  const max = Math.max(...all)
  const min = Math.min(...all, 0)
  // See GrowthChart: a spline through three points draws a trend that was
  // never observed.
  const sparse = points.length <= 10
  const curve = sparse ? 'linear' : 'monotone'

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={points} margin={{ top: 8, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="valueGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={VALUE_COLOR} stopOpacity={0.2} />
            <stop offset="95%" stopColor={VALUE_COLOR} stopOpacity={0} />
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
          domain={[min, max * 1.05]}
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={64}
          tickFormatter={v => formatMoney(v as number, currency, { compact: true })}
        />
        <Tooltip content={
          <ValueTooltip
            currency={currency}
            benchmarkName={benchmarkName}
            benchmarkAvailable={benchmarkAvailable}
          />
        } />
        {/* Drawn first so the filled value area sits on top of both lines. */}
        <Line
          type="stepAfter"
          dataKey="invested"
          stroke={INVESTED_COLOR}
          strokeWidth={1.4}
          dot={false}
          isAnimationActive={false}
          name="Invested"
        />
        {benchmarkAvailable && (
          <Line
            type={curve}
            dataKey="benchmark_value"
            stroke={BENCHMARK_COLOR}
            strokeWidth={1.4}
            strokeDasharray="5 3"
            dot={false}
            isAnimationActive={false}
            name={benchmarkName}
          />
        )}
        <Area
          type={curve}
          dataKey="value"
          stroke={VALUE_COLOR}
          strokeWidth={1.8}
          fill="url(#valueGradient)"
          dot={sparse ? { r: 2.5, strokeWidth: 0, fill: VALUE_COLOR } : false}
          isAnimationActive={false}
          activeDot={{ r: 3, strokeWidth: 0, fill: VALUE_COLOR }}
          name="Value"
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
