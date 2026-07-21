import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import type { OHLCV } from '../types'
import { computeXTicks, xTickFormatter, computeIntradayTicks, intradayTickFormatter } from '../utils/chart'

export function volUnit(data: { volume: number | null }[]): string {
  const max = Math.max(...data.map(d => d.volume ?? 0))
  if (max >= 1e9) return 'B'
  if (max >= 1e6) return 'M'
  return 'K'
}

function fmtVol(v: number) {
  if (v >= 1e9) return (v / 1e9).toFixed(2) + 'B'
  if (v >= 1e6) return (v / 1e6).toFixed(2) + 'M'
  if (v >= 1e3) return (v / 1e3).toFixed(1) + 'K'
  return v.toString()
}

interface Props {
  data: OHLCV[]
  days: number
}

export function VolumeChart({ data, days }: Props) {
  if (data.length === 0) return null

  const isIntraday = days === 0
  const xTicks = isIntraday
    ? computeIntradayTicks(data.map(d => d.date))
    : computeXTicks(data.map(d => d.date), days)
  const tickFmt = (v: string) => isIntraday ? intradayTickFormatter(v) : xTickFormatter(v, days)

  return (
    <ResponsiveContainer width="100%" height="100%">
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
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
          tick={{ fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }}
          tickLine={false}
          axisLine={false}
          width={58}
          tickFormatter={fmtVol}
        />
        <Tooltip
          formatter={(v: number) => [fmtVol(v), 'Volume']}
          contentStyle={{
            background: '#18181b',
            border: '1px solid #3f3f46',
            borderRadius: 8,
            fontSize: 12,
            fontFamily: 'JetBrains Mono',
          }}
          labelStyle={{ color: '#a1a1aa' }}
          itemStyle={{ color: '#818cf8' }}
        />
        <Bar dataKey="volume" radius={[2, 2, 0, 0]}>
          {data.map((d, i) => (
            <Cell key={i} fill={d.close >= (d.open ?? d.close) ? '#10b98128' : '#ef444428'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
