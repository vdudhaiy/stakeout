import { useMemo } from 'react'
import {
  ComposedChart,
  Bar,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { EnrichedOHLCV } from '../types'
import type { OverlayConfig } from '../utils/indicators'
import { SMA_COLORS, EMA_COLORS } from '../utils/indicators'
import { computeXTicks, xTickFormatter, computeIntradayTicks, intradayTickFormatter } from '../utils/chart'

function makeTooltip(overlays: OverlayConfig) {
  return function CustomTooltip(props: any) {
    const { active, payload } = props
    if (!active || !payload?.length) return null
    const d = payload[0].payload as EnrichedOHLCV
    const isIntraday = (d.date as string).includes('T')
    const hasOverlays = overlays.activeSMA.length > 0 || overlays.activeEMA.length > 0
    return (
      <div className="bg-zinc-900 border border-zinc-700 rounded-lg p-3 shadow-xl text-xs font-mono">
        <p className="text-zinc-400 mb-2">{isIntraday ? (d.date as string).slice(11, 16) : d.date as string}</p>
        <div className="grid grid-cols-2 gap-x-5 gap-y-1">
          <span className="text-zinc-500">O</span>
          <span className="text-zinc-200">${(d.open as number | null)?.toFixed(2) ?? '—'}</span>
          <span className="text-zinc-500">H</span>
          <span className="text-emerald-400">${(d.high as number | null)?.toFixed(2) ?? '—'}</span>
          <span className="text-zinc-500">L</span>
          <span className="text-red-400">${(d.low as number | null)?.toFixed(2) ?? '—'}</span>
          <span className="text-zinc-500">C</span>
          <span className="text-zinc-100 font-medium">${(d.close as number).toFixed(2)}</span>
        </div>
        {hasOverlays && (
          <div className="mt-2 pt-2 border-t border-zinc-800 space-y-0.5">
            {overlays.activeSMA.map(p => {
              const val = d[`sma_${p}`] as number | null
              return val != null ? (
                <div key={p} className="flex justify-between gap-4">
                  <span style={{ color: SMA_COLORS[p] }}>SMA {p}</span>
                  <span className="text-zinc-300">${val.toFixed(2)}</span>
                </div>
              ) : null
            })}
            {overlays.activeEMA.map(p => {
              const val = d[`ema_${p}`] as number | null
              return val != null ? (
                <div key={p} className="flex justify-between gap-4">
                  <span style={{ color: EMA_COLORS[p] }}>EMA {p}</span>
                  <span className="text-zinc-300">${val.toFixed(2)}</span>
                </div>
              ) : null
            })}
          </div>
        )}
      </div>
    )
  }
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
      <line x1={cx} x2={cx} y1={y} y2={y + height} stroke={color} strokeWidth={1} />
      <rect x={cx - halfBody} y={bodyTop} width={halfBody * 2} height={bodyH} fill={color} />
    </g>
  )
}

interface Props {
  data: EnrichedOHLCV[]
  days: number
  overlays: OverlayConfig
}

export function CandlestickChart({ data, days, overlays }: Props) {
  const tooltipContent = useMemo(() => makeTooltip(overlays), [overlays])

  if (data.length === 0) return null

  const isIntraday = days === 0
  const xTicks = isIntraday
    ? computeIntradayTicks(data.map(d => d.date as string))
    : computeXTicks(data.map(d => d.date as string), days)
  const tickFmt = (v: string) =>
    isIntraday ? intradayTickFormatter(v) : xTickFormatter(v, days)

  const priceVals = data.flatMap(d => [d.low as number ?? d.close as number, d.high as number ?? d.close as number])
  const overlayVals: number[] = [
    ...(overlays.bb
      ? data.flatMap(d => [d.bbUpper, d.bbLower]).filter((v): v is number => v != null)
      : []),
    ...overlays.activeSMA.flatMap(p =>
      data.map(d => d[`sma_${p}`] as number | null).filter((v): v is number => v != null)
    ),
    ...overlays.activeEMA.flatMap(p =>
      data.map(d => d[`ema_${p}`] as number | null).filter((v): v is number => v != null)
    ),
  ]
  const allVals = [...priceVals, ...overlayVals]
  const min = Math.min(...allVals) * 0.99
  const max = Math.max(...allVals) * 1.01

  const chartData = data.map(d => ({
    ...d,
    candleRange: [d.low as number ?? d.close as number, d.high as number ?? d.close as number] as [number, number],
  }))

  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }} syncId="ml-chart">
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
          content={tooltipContent}
          cursor={{ stroke: '#3f3f46', strokeWidth: 1 }}
        />
        <Bar
          dataKey="candleRange"
          shape={(props: any) => <CandleShape {...props} />}
          isAnimationActive={false}
        />
        {overlays.bb && <>
          <Line dataKey="bbUpper"  stroke="#3b82f6" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} connectNulls={false} />
          <Line dataKey="bbMiddle" stroke="#60a5fa" strokeWidth={1} strokeDasharray="6 2" dot={false} isAnimationActive={false} connectNulls={false} />
          <Line dataKey="bbLower"  stroke="#3b82f6" strokeWidth={1} strokeDasharray="3 3" dot={false} isAnimationActive={false} connectNulls={false} />
        </>}
        {overlays.activeSMA.map(period => (
          <Line
            key={`sma_${period}`}
            dataKey={`sma_${period}`}
            stroke={SMA_COLORS[period]}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        ))}
        {overlays.activeEMA.map(period => (
          <Line
            key={`ema_${period}`}
            dataKey={`ema_${period}`}
            stroke={EMA_COLORS[period]}
            strokeWidth={1.5}
            dot={false}
            isAnimationActive={false}
            connectNulls={false}
          />
        ))}
      </ComposedChart>
    </ResponsiveContainer>
  )
}
