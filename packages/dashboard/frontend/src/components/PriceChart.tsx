import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import type { OHLCV } from '../types'
import { computeXTicks, xTickFormatter } from '../utils/chart'

interface TooltipProps {
  active?: boolean
  payload?: Array<{ payload: OHLCV }>
}

function CustomTooltip({ active, payload }: TooltipProps) {
  if (!active || !payload?.length) return null
  const d = payload[0].payload
  return (
    <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs font-mono">
      <p className="text-zinc-400 mb-2">{d.date}</p>
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

interface Props {
  data: OHLCV[]
  days: number
}

export function PriceChart({ data, days }: Props) {
  if (data.length === 0) return null

  const xTicks = computeXTicks(data.map(d => d.date), days)

  const min = Math.min(...data.map(d => d.low ?? d.close)) * 0.99
  const max = Math.max(...data.map(d => d.high ?? d.close)) * 1.01
  const firstClose = data[0].close
  const lastClose = data[data.length - 1].close
  const isPositive = lastClose >= firstClose
  const color = isPositive ? '#10b981' : '#ef4444'

  return (
    <ResponsiveContainer width="100%" height="100%">
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id="priceGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.15} />
            <stop offset="95%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
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
          domain={[min, max]}
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={58}
          tickFormatter={v => `$${(v as number).toFixed(0)}`}
        />
        <Tooltip content={<CustomTooltip />} />
        <ReferenceLine y={firstClose} stroke="#3f3f46" strokeDasharray="4 4" />
        <Area
          type="monotone"
          dataKey="close"
          stroke={color}
          strokeWidth={1.5}
          fill="url(#priceGradient)"
          dot={false}
          activeDot={{ r: 3, strokeWidth: 0, fill: color }}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
