import {
  ComposedChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { OHLCV } from '../types'
import { computeXTicks, xTickFormatter, computeIntradayTicks, intradayTickFormatter } from '../utils/chart'

interface TooltipProps {
  active?: boolean
  payload?: Array<{ payload: OHLCV }>
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const isIntraday = d.date.includes('T')
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs font-mono">
      <p className="text-zinc-400 mb-2">{isIntraday ? d.date.slice(11, 16) : d.date}</p>
      <div className="grid grid-cols-2 gap-x-5 gap-y-1">
        <span className="text-zinc-500">O</span>
        <span className="text-zinc-200">${d.open?.toFixed(2) ?? '—'}</span>
        <span className="text-zinc-500">H</span>
        <span className="text-emerald-400">${d.high?.toFixed(2) ?? '—'}</span>
        <span className="text-zinc-500">L</span>
        <span className="text-red-400">${d.low?.toFixed(2) ?? '—'}</span>
        <span className="text-zinc-500">C</span>
        <span className="text-white font-medium">${d.close.toFixed(2)}</span>
      </div>
    </div>
  )
}

function CandleShape(props: any) {
  const { x = 0, y = 0, width = 0, height = 0, open, high, low, close } = props
  if (open == null || high == null || low == null || close == null) return null

  const range = high - low
  const isGreen = close >= open
  const color = isGreen ? '#10b981' : '#ef4444'

  // y = pixel(high), y+height = pixel(low) — Recharts maps the [low,high] range here
  const openY  = range > 0 ? y + ((high - open)  / range) * height : y + height / 2
  const closeY = range > 0 ? y + ((high - close) / range) * height : y + height / 2

  const bodyTop = Math.min(openY, closeY)
  const bodyH   = Math.max(Math.abs(closeY - openY), 1)
  const cx       = x + width / 2
  const halfBody = Math.max(width * 0.4, 1)

  return (
    <g>
      {/* Wick — full high-to-low line; body rect covers the middle */}
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - halfBody} y={bodyTop} width={halfBody * 2} height={bodyH} fill={color} />
    </g>
  )
}

interface Props {
  data: OHLCV[]
  days: number
}

export function CandlestickChart({ data, days }: Props) {
  if (data.length === 0) return null

  const isIntraday = days === 0
  const xTicks = isIntraday
    ? computeIntradayTicks(data.map(d => d.date))
    : computeXTicks(data.map(d => d.date), days)
  const tickFmt = (v: string) =>
    isIntraday ? intradayTickFormatter(v) : xTickFormatter(v, days)

  const min = Math.min(...data.map(d => d.low ?? d.close)) * 0.99
  const max = Math.max(...data.map(d => d.high ?? d.close)) * 1.01

  // candleRange drives the ranged-bar positioning; other OHLCV fields remain
  // accessible as raw props inside CandleShape via Recharts' data spreading.
  const chartData = data.map(d => ({
    ...d,
    candleRange: [d.low ?? d.close, d.high ?? d.close] as [number, number],
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          ticks={xTicks}
          interval={0}
          tickFormatter={tickFmt}
        />
        <YAxis
          domain={[min, max]}
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={58}
          tickFormatter={v => `$${(v as number).toFixed(0)}`}
        />
        <Tooltip
          content={<CustomTooltip />}
          cursor={{ stroke: '#3f3f46', strokeWidth: 1 }}
        />
        <Bar
          dataKey="candleRange"
          shape={(props: any) => <CandleShape {...props} />}
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
