import clsx from 'clsx'
import { InfoTip } from './InfoTip'
import type { GlossaryKey } from '../utils/glossary'

interface Props {
  open: number | null
  high: number | null
  low: number | null
  close: number | null
  volume: number | null
  prevClose?: number
  /** Currency-aware money formatter provided by the page (native → display ccy). */
  format?: (v: number | null | undefined, opts?: { sign?: boolean }) => string
}

function fmtPrice(n: number | null) {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtVolume(n: number | null) {
  if (n == null) return '—'
  if (n >= 1e9) return (n / 1e9).toFixed(2) + 'B'
  if (n >= 1e6) return (n / 1e6).toFixed(2) + 'M'
  if (n >= 1e3) return (n / 1e3).toFixed(0) + 'K'
  return n.toString()
}

export function OHLCVStats({ open, high, low, close, volume, prevClose, format }: Props) {
  const change = prevClose !== undefined && close != null ? close - prevClose : null
  const changePct = change !== null && prevClose ? (change / prevClose) * 100 : null
  const isPositive = change !== null ? change >= 0 : null
  const money = (v: number | null) => (v == null ? '—' : format ? format(v) : `$${fmtPrice(v)}`)

  const stats: Array<{ label: string; tip: GlossaryKey; value: string; colored: boolean; isPositive?: boolean | null }> = [
    { label: 'OPEN',  tip: 'open',  value: money(open),  colored: false },
    { label: 'HIGH',  tip: 'high',  value: money(high),  colored: false },
    { label: 'LOW',   tip: 'low',   value: money(low),   colored: false },
    { label: 'CLOSE', tip: 'close', value: money(close), colored: false },
    {
      label: 'CHANGE',
      tip: 'change',
      value:
        change !== null
          ? `${format ? format(change, { sign: true }) : `${isPositive ? '+' : ''}${fmtPrice(change)}`} (${isPositive ? '+' : ''}${changePct!.toFixed(2)}%)`
          : '—',
      colored: true,
      isPositive,
    },
    { label: 'VOLUME', tip: 'volume', value: fmtVolume(volume), colored: false },
  ]

  return (
    <div className="grid grid-cols-6 gap-px bg-zinc-800 rounded-xl overflow-hidden border border-zinc-800">
      {stats.map(({ label, tip, value, colored, isPositive: pos }) => (
        <div key={label} className="bg-zinc-900 px-4 py-3 flex flex-col gap-1.5">
          <span className="flex items-center gap-1.5 text-zinc-500 text-[10px] tracking-widest font-medium">{label} <InfoTip k={tip} /></span>
          <span
            className={clsx(
              'font-mono text-sm font-medium',
              colored
                ? pos
                  ? 'text-emerald-400'
                  : 'text-red-400'
                : 'text-zinc-100',
            )}
          >
            {value}
          </span>
        </div>
      ))}
    </div>
  )
}
