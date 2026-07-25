import { useEffect, useState } from 'react'
import { Area, AreaChart, ResponsiveContainer, Tooltip, YAxis } from 'recharts'
import { Globe2, RefreshCw, TrendingDown, TrendingUp } from 'lucide-react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { fetchIndices } from '../api'
import type { IndexQuote } from '../types'

const UP = '#2FBF71'
const DOWN = '#E5484D'

const fmtLevel = (v: number) =>
  v.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

function IndexCard({ q, delay }: { q: IndexQuote; delay: number }) {
  const up = (q.change ?? 0) >= 0
  const color = up ? UP : DOWN
  const gradId = `idx-grad-${q.symbol.replace(/[^a-zA-Z0-9]/g, '')}`

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-30px' }}
      transition={{ delay, duration: 0.35 }}
      className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 hover:border-zinc-700 transition-colors min-w-0"
    >
      <div className="flex items-baseline justify-between gap-2 mb-0.5">
        <p className="text-[13px] font-medium text-zinc-200 truncate">{q.name}</p>
        <span className="font-mono text-[10px] text-zinc-600 shrink-0">{q.symbol}</span>
      </div>
      <div className="flex items-baseline gap-2 flex-wrap">
        <span className="font-mono text-lg font-semibold text-zinc-100">{fmtLevel(q.last)}</span>
        {q.change != null && q.change_pct != null && (
          <span className={clsx('flex items-center gap-1 text-xs font-mono', up ? 'text-emerald-400' : 'text-red-400')}>
            {up ? <TrendingUp size={11} /> : <TrendingDown size={11} />}
            {up ? '+' : ''}{fmtLevel(q.change)} ({up ? '+' : ''}{q.change_pct.toFixed(2)}%)
          </span>
        )}
      </div>
      <div className="h-16 mt-2 -mx-1">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={q.points} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
            <defs>
              <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={color} stopOpacity={0.28} />
                <stop offset="100%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <YAxis domain={['dataMin', 'dataMax']} hide />
            <Tooltip
              formatter={(v: number) => [fmtLevel(v), q.name]}
              labelFormatter={(d: string) => d}
              contentStyle={{ background: '#0A0E16', border: '1px solid #2A3446', borderRadius: 8, fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' }}
            />
            <Area type="monotone" dataKey="close" stroke={color} strokeWidth={1.5} fill={`url(#${gradId})`} dot={false} activeDot={{ r: 3 }} isAnimationActive={false} />
          </AreaChart>
        </ResponsiveContainer>
      </div>
      <p className="text-[10px] text-zinc-600 font-mono mt-1">Last 3 months · daily close</p>
    </motion.div>
  )
}

/** Major US and Indian index charts for the home page. Public — no sign-in needed. */
export function IndexStrip() {
  const [indices, setIndices] = useState<IndexQuote[] | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    fetchIndices()
      .then(res => { if (!cancelled) setIndices(res.indices) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [])

  // No data at all → render nothing rather than an empty section
  if (failed || (indices !== null && indices.length === 0)) return null

  const us = (indices ?? []).filter(i => i.region === 'US')
  const india = (indices ?? []).filter(i => i.region === 'IN')

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <Globe2 size={14} className="text-indigo-400" />
        <h2 className="font-display text-sm font-semibold text-zinc-200 tracking-wide">Major indices</h2>
        {indices === null && <RefreshCw size={11} className="animate-spin text-zinc-600" />}
      </div>

      {indices === null ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-36 rounded-xl bg-zinc-800/50 animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-4">
          {[
            { label: 'UNITED STATES · NYSE / NASDAQ', items: us },
            { label: 'INDIA · NSE / BSE', items: india },
          ].filter(g => g.items.length > 0).map(({ label, items }) => (
            <div key={label}>
              <p className="text-[10px] font-semibold tracking-widest text-zinc-500 mb-2">{label}</p>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {items.map((q, i) => <IndexCard key={q.symbol} q={q} delay={i * 0.06} />)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
