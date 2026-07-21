import { useState, useEffect, useCallback, useMemo } from 'react'
import clsx from 'clsx'
import { ArrowLeft, RefreshCw, CheckSquare, Square } from 'lucide-react'
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ReferenceLine,
} from 'recharts'
import { fetchStock } from '../api'
import type { OHLCV, ComparisonGroup } from '../types'

const DAYS_OPTIONS = [
  { label: '7D', value: 7 },
  { label: '14D', value: 14 },
  { label: '30D', value: 30 },
  { label: '90D', value: 90 },
  { label: '180D', value: 180 },
  { label: '1Yr', value: 365 },
  { label: '2Yr', value: 730 },
  { label: '3Yr', value: 1095 },
]

const PALETTE = [
  '#6366f1', '#f59e0b', '#10b981', '#ef4444', '#3b82f6',
  '#f97316', '#a855f7', '#14b8a6', '#ec4899', '#84cc16',
  '#06b6d4', '#fb7185', '#a3e635', '#fbbf24', '#8b5cf6',
]

interface Props {
  group: ComparisonGroup
  onBack: () => void
  marketOpen: boolean | null
  tickerNames?: Record<string, string>
}

export function ComparisonView({ group, onBack, marketOpen, tickerNames }: Props) {
  const [days, setDays] = useState(30)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [stockData, setStockData] = useState<Record<string, OHLCV[]>>({})
  const [enabled, setEnabled] = useState<Set<string>>(new Set(group.tickers))

  const loadAll = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const results = await Promise.all(
        group.tickers.map(t =>
          fetchStock(t, days)
            .then(r => [t, r.data] as [string, OHLCV[]])
            .catch(() => [t, []] as [string, OHLCV[]])
        )
      )
      const map: Record<string, OHLCV[]> = {}
      for (const [t, d] of results) map[t] = d
      setStockData(map)
      setEnabled(new Set(group.tickers.filter(t => (map[t]?.length ?? 0) > 0)))
    } catch {
      setError('Failed to load comparison data')
    } finally {
      setLoading(false)
    }
  }, [group, days])

  useEffect(() => {
    loadAll()
  }, [loadAll])

  const today = new Date().toISOString().slice(0, 10)

  // Normalise each ticker to % change from first close, then merge by date
  const activeTickers = group.tickers.filter(t => enabled.has(t) && (stockData[t]?.length ?? 0) > 0)

  const chartData = (() => {
    const dateMap = new Map<string, Record<string, number>>()
    for (const t of activeTickers) {
      const allRows = stockData[t]
      const rows = marketOpen !== false ? allRows?.filter(d => d.date !== today) : allRows
      if (!rows?.length) continue
      const base = rows[0].close
      for (const row of rows) {
        if (!dateMap.has(row.date)) dateMap.set(row.date, {})
        dateMap.get(row.date)![t] = ((row.close - base) / base) * 100
      }
    }
    return [...dateMap.entries()]
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([date, values]) => ({ date, ...values }))
  })()

  const tickersWithData = useMemo(
    () => group.tickers.filter(t => (stockData[t]?.length ?? 0) > 0),
    [group.tickers, stockData],
  )
  const allSelected = tickersWithData.length > 0 && tickersWithData.every(t => enabled.has(t))

  function toggleTicker(t: string) {
    setEnabled(prev => {
      const next = new Set(prev)
      if (next.has(t)) next.delete(t)
      else next.add(t)
      return next
    })
  }

  function toggleAll() {
    if (allSelected) {
      setEnabled(new Set())
    } else {
      setEnabled(new Set(tickersWithData))
    }
  }

  const typeLabel = group.type === 'industry' ? 'Industry' : group.type === 'sector' ? 'Sector' : 'All'

  return (
    <main className="flex-1 overflow-y-auto p-6 min-w-0">
      <div className="flex flex-col gap-5 max-w-6xl">
        {/* Header */}
        <div className="flex items-start justify-between gap-4">
          <div className="flex items-center gap-3">
            <button
              onClick={onBack}
              className="p-1.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 transition-colors shrink-0"
            >
              <ArrowLeft size={16} />
            </button>
            <div>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[11px] font-medium uppercase tracking-wider text-indigo-400 bg-indigo-500/10 px-2 py-0.5 rounded">
                  {typeLabel}
                </span>
                <h1 className="text-xl font-bold tracking-tight">{group.name}</h1>
              </div>
              <p className="text-xs text-zinc-500 mt-0.5">
                % change from period start · {group.tickers.length} stocks
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <div className="flex rounded-lg overflow-hidden border border-zinc-800">
              {DAYS_OPTIONS.map(({ label, value }) => (
                <button
                  key={value}
                  onClick={() => setDays(value)}
                  className={clsx(
                    'px-3 py-1.5 text-xs font-medium transition-colors',
                    days === value
                      ? 'bg-indigo-600 text-white'
                      : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <button
              onClick={loadAll}
              disabled={loading}
              title="Refresh"
              className="p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 rounded-lg transition-colors"
            >
              <RefreshCw size={13} className={loading ? 'animate-spin' : ''} />
            </button>
          </div>
        </div>

        {/* Ticker toggle chips */}
        <div className="flex flex-col gap-2">
        <button
          onClick={toggleAll}
          className="flex items-center gap-1.5 text-xs text-zinc-400 hover:text-zinc-200 transition-colors self-start"
        >
          {allSelected
            ? <CheckSquare size={13} className="text-indigo-400" />
            : <Square size={13} className="text-zinc-600" />
          }
          {allSelected ? 'Deselect all' : 'Select all'}
        </button>
        <div className="flex flex-wrap gap-2">
          {group.tickers.map((t, i) => {
            const color = PALETTE[i % PALETTE.length]
            const active = enabled.has(t)
            const hasData = (stockData[t]?.length ?? 0) > 0
            return (
              <button
                key={t}
                onClick={() => hasData && toggleTicker(t)}
                disabled={!hasData}
                title={!hasData ? 'No data available' : (tickerNames?.[t] ?? t)}
                className={clsx(
                  'px-3 py-1 rounded-full text-xs font-mono font-medium transition-all border',
                  active && hasData ? 'opacity-100' : 'opacity-30 grayscale',
                  !hasData && 'cursor-not-allowed',
                )}
                style={
                  active && hasData
                    ? { borderColor: color, color, backgroundColor: `${color}1a` }
                    : { borderColor: '#3f3f46', color: '#71717a' }
                }
              >
                {t}
              </button>
            )
          })}
        </div>
        </div>

        {/* Chart area */}
        {loading && chartData.length === 0 ? (
          <div className="flex items-center justify-center h-96 bg-zinc-900 border border-zinc-800 rounded-xl">
            <div className="flex items-center gap-2 text-zinc-500 text-sm">
              <RefreshCw size={13} className="animate-spin" />
              Loading comparison...
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center h-96 bg-zinc-900 border border-zinc-800 rounded-xl">
            <div className="text-center space-y-2">
              <p className="text-zinc-500 text-sm">{error}</p>
              <button
                onClick={loadAll}
                className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
              >
                Try again
              </button>
            </div>
          </div>
        ) : chartData.length > 0 ? (
          <div className="bg-zinc-900 rounded-xl border border-zinc-800 p-4">
            <p className="text-[10px] text-zinc-500 tracking-widest font-medium mb-3">
              NORMALISED % CHANGE
            </p>
            <div className="h-96">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#27272a" />
                  <XAxis
                    dataKey="date"
                    tick={{ fontSize: 10, fill: '#71717a' }}
                    tickLine={false}
                    axisLine={false}
                    interval="preserveStartEnd"
                  />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#71717a' }}
                    tickLine={false}
                    axisLine={false}
                    tickFormatter={v => `${v > 0 ? '+' : ''}${(v as number).toFixed(1)}%`}
                  />
                  <ReferenceLine y={0} stroke="#52525b" strokeDasharray="3 3" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#18181b',
                      border: '1px solid #27272a',
                      borderRadius: '8px',
                      fontSize: '11px',
                      color: '#e4e4e7',
                    }}
                    labelStyle={{ color: '#a1a1aa', marginBottom: 4 }}
                    formatter={(value: unknown, name: string) => {
                      const v = value as number
                      return [`${v > 0 ? '+' : ''}${v.toFixed(2)}%`, name]
                    }}
                  />
                  {activeTickers.map(t => (
                    <Line
                      key={t}
                      dataKey={t}
                      stroke={PALETTE[group.tickers.indexOf(t) % PALETTE.length]}
                      dot={false}
                      strokeWidth={1.5}
                      connectNulls
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-96 bg-zinc-900 border border-zinc-800 rounded-xl">
            <p className="text-zinc-500 text-sm">No data available for this group</p>
          </div>
        )}
      </div>
    </main>
  )
}
