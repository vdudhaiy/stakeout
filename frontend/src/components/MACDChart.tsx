import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { MACDDataPoint } from '../types'
import { computeXTicks, xTickFormatter } from '../utils/chart'

function HistogramBar(props: any) {
  const { x, y, width, height, payload } = props
  if (!payload) return null
  const positive = (payload.histogram ?? 0) >= 0
  // height can be negative in recharts when value is negative; normalize
  const barY = height < 0 ? y + height : y
  const barH = Math.max(Math.abs(height), 1)
  return (
    <rect
      x={x}
      y={barY}
      width={Math.max(width, 1)}
      height={barH}
      fill={positive ? '#10b981' : '#ef4444'}
      fillOpacity={0.6}
    />
  )
}

interface TooltipProps {
  active?: boolean
  payload?: Array<{ payload: MACDDataPoint }>
}

function MACDTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  const histPositive = (d.histogram ?? 0) >= 0
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-xs font-mono space-y-1">
      <p className="text-zinc-400">{d.date}</p>
      <p className="text-blue-400">MACD&nbsp;&nbsp;&nbsp;{d.macd != null ? d.macd.toFixed(3) : '—'}</p>
      <p className="text-orange-400">Signal&nbsp;{d.signal != null ? d.signal.toFixed(3) : '—'}</p>
      <p className={histPositive ? 'text-emerald-400' : 'text-red-400'}>
        Hist&nbsp;&nbsp;&nbsp;{d.histogram != null ? d.histogram.toFixed(3) : '—'}
      </p>
    </div>
  )
}

interface Props {
  data: MACDDataPoint[]
  days: number
}

export function MACDChart({ data, days }: Props) {
  if (data.length === 0) return null

  const xTicks = computeXTicks(data.map(d => d.date), days)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="ml-chart">
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
        <XAxis
          dataKey="date"
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          ticks={xTicks}
          interval={0}
          tickFormatter={v => xTickFormatter(v, days)}
        />
        <YAxis
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={45}
          tickFormatter={v => (v as number).toFixed(1)}
        />
        <Tooltip content={<MACDTooltip />} cursor={{ stroke: '#3f3f46', strokeWidth: 1 }} />
        <ReferenceLine y={0} stroke="#3f3f46" strokeWidth={1} />
        <Bar dataKey="histogram" shape={(props: any) => <HistogramBar {...props} />} isAnimationActive={false} />
        <Line dataKey="macd"   stroke="#60a5fa" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
        <Line dataKey="signal" stroke="#f97316" strokeWidth={1.5} dot={false} isAnimationActive={false} connectNulls={false} />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
