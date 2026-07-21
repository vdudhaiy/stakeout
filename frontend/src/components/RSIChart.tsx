import {
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { IndicatorPoint } from '../types'
import { computeXTicks, xTickFormatter } from '../utils/chart'

interface TooltipProps {
  active?: boolean
  payload?: Array<{ payload: IndicatorPoint }>
}

function RSITooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 shadow-xl text-xs font-mono">
      <p className="text-zinc-400 mb-1">{d.date}</p>
      <p className="text-violet-400">RSI {d.value != null ? d.value.toFixed(2) : '—'}</p>
    </div>
  )
}

interface Props {
  data: IndicatorPoint[]
  days: number
}

export function RSIChart({ data, days }: Props) {
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
          domain={[0, 100]}
          ticks={[30, 50, 70]}
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={28}
        />
        <Tooltip content={<RSITooltip />} cursor={{ stroke: '#3f3f46', strokeWidth: 1 }} />
        <ReferenceLine y={70} stroke="#ef444450" strokeDasharray="3 3" strokeWidth={1} />
        <ReferenceLine y={50} stroke="#3f3f46" strokeDasharray="2 2" strokeWidth={1} />
        <ReferenceLine y={30} stroke="#22c55e50" strokeDasharray="3 3" strokeWidth={1} />
        <Line
          dataKey="value"
          stroke="#a78bfa"
          strokeWidth={1.5}
          dot={false}
          isAnimationActive={false}
          connectNulls={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  )
}
