import { useState } from 'react'
import { InfoTip } from './InfoTip'
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell, ReferenceLine } from 'recharts'
import clsx from 'clsx'
import type { EPSHistoryRow, RevenueHistoryRow } from '../types'

function quarterLabel(dateStr: string | null | undefined): string {
  if (!dateStr) return ''
  const d = new Date(dateStr + 'T00:00:00Z')
  const m = d.getUTCMonth()
  const y = String(d.getUTCFullYear()).slice(2)
  const q = m < 3 ? 'Q1' : m < 6 ? 'Q2' : m < 9 ? 'Q3' : 'Q4'
  return `${q} '${y}`
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '—'
  return `${v >= 0 ? '+' : ''}${v.toFixed(1)}%`
}

function fmtRevenue(v: number | null | undefined): string {
  if (v == null) return '—'
  const abs = Math.abs(v)
  if (abs >= 1e12) return `$${(v / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(2)}M`
  return `$${v.toFixed(0)}`
}

const TOOLTIP_STYLE = {
  background: '#18181b',
  border: '1px solid #3f3f46',
  borderRadius: 8,
  fontSize: 12,
  fontFamily: 'JetBrains Mono',
}

const TICK_STYLE = { fill: '#71717a', fontSize: 10, fontFamily: 'JetBrains Mono' }

// ── Toggle ────────────────────────────────────────────────────────────────────

interface ToggleProps<T extends string> {
  options: { label: string; value: T }[]
  active: T
  onChange: (v: T) => void
}

function Toggle<T extends string>({ options, active, onChange }: ToggleProps<T>) {
  return (
    <div className="flex rounded-md overflow-hidden border border-zinc-800 text-[10px]">
      {options.map(o => (
        <button
          key={o.value}
          onClick={() => onChange(o.value)}
          className={clsx(
            'px-2 py-1 transition-colors',
            active === o.value ? 'bg-indigo-600 text-white' : 'text-zinc-400 hover:text-zinc-200',
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  )
}

// ── EPS chart ─────────────────────────────────────────────────────────────────

function EPSChart({ rows }: { rows: EPSHistoryRow[] }) {
  const [mode, setMode] = useState<'growth' | 'surprise'>('growth')

  const chartData = rows.map(r => ({
    label: quarterLabel(r.date),
    value: mode === 'growth' ? (r.eps_growth ?? null) : (r.surprise_percent ?? null),
  }))

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-[10px] text-zinc-500 tracking-widest font-medium">EPS <InfoTip k="earnings_surprise" /></p>
        <Toggle
          options={[
            { label: 'Growth', value: 'growth' },
            { label: 'Surprise %', value: 'surprise' },
          ]}
          active={mode}
          onChange={setMode}
        />
      </div>
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="label" tick={TICK_STYLE} tickLine={false} axisLine={false} />
            <YAxis
              tick={TICK_STYLE}
              tickLine={false}
              axisLine={false}
              width={48}
              tickFormatter={v => `${v}%`}
            />
            <ReferenceLine y={0} stroke="#3f3f46" />
            <Tooltip
              formatter={(v: number) => [fmtPct(v), mode === 'growth' ? 'EPS Growth' : 'Surprise']}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={{ color: '#a1a1aa' }}
              itemStyle={{ color: '#818cf8' }}
            />
            <Bar dataKey="value" radius={[2, 2, 0, 0]}>
              {chartData.map((d, i) => (
                <Cell key={i} fill={(d.value ?? 0) >= 0 ? '#10b981' : '#ef4444'} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ── Revenue chart ─────────────────────────────────────────────────────────────

function RevenueChart({ rows }: { rows: RevenueHistoryRow[] }) {
  const [mode, setMode] = useState<'growth' | 'actual'>('growth')

  const chartData = rows.map(r => ({
    label: quarterLabel(r.date),
    value: mode === 'growth' ? (r.percent_change ?? null) : (r.revenue ?? null),
  }))

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-1.5 text-[10px] text-zinc-500 tracking-widest font-medium">REVENUE <InfoTip k="revenue_estimate" /></p>
        <Toggle
          options={[
            { label: 'Growth', value: 'growth' },
            { label: 'Actual', value: 'actual' },
          ]}
          active={mode}
          onChange={setMode}
        />
      </div>
      <div className="h-36">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={chartData} margin={{ top: 4, right: 8, bottom: 0, left: 0 }}>
            <XAxis dataKey="label" tick={TICK_STYLE} tickLine={false} axisLine={false} />
            <YAxis
              tick={TICK_STYLE}
              tickLine={false}
              axisLine={false}
              width={mode === 'actual' ? 56 : 48}
              tickFormatter={v => mode === 'growth' ? `${v}%` : fmtRevenue(v)}
            />
            <ReferenceLine y={0} stroke="#3f3f46" />
            <Tooltip
              formatter={(v: number) => [
                mode === 'growth' ? fmtPct(v) : fmtRevenue(v),
                mode === 'growth' ? 'Growth' : 'Revenue',
              ]}
              contentStyle={TOOLTIP_STYLE}
              labelStyle={{ color: '#a1a1aa' }}
              itemStyle={{ color: '#818cf8' }}
            />
            <Bar dataKey="value" radius={[2, 2, 0, 0]}>
              {chartData.map((d, i) => (
                <Cell
                  key={i}
                  fill={mode === 'growth'
                    ? ((d.value ?? 0) >= 0 ? '#10b981' : '#ef4444')
                    : '#818cf8'}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

// ── Composed panel ────────────────────────────────────────────────────────────

interface Props {
  epsHistory: EPSHistoryRow[] | null
  revenueHistory: RevenueHistoryRow[] | null
}

export function EarningsHistoryPanel({ epsHistory, revenueHistory }: Props) {
  const hasEps = (epsHistory?.length ?? 0) > 0
  const hasRevenue = (revenueHistory?.length ?? 0) > 0
  if (!hasEps && !hasRevenue) return null

  return (
    <div className={clsx('grid gap-4', hasEps && hasRevenue ? 'grid-cols-2' : 'grid-cols-1')}>
      {hasEps && <EPSChart rows={epsHistory!} />}
      {hasRevenue && <RevenueChart rows={revenueHistory!} />}
    </div>
  )
}
