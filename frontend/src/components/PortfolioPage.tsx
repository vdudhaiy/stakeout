import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import clsx from 'clsx'
import {
  Plus, ChevronDown, ChevronUp,
  Trash2, RefreshCw, X, Briefcase, ArrowDownLeft, ArrowUpRight,
  BarChart2, AlertTriangle, FileDown,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { PieChart, Pie, Cell, Tooltip as ChartTooltip, Legend, ResponsiveContainer } from 'recharts'
import type { ClassificationMap, Market, PortfolioResponse, StockHolding, StockPurchaseHistory } from '../types'
import { fetchPortfolio, fetchClassification, logBuy, logSell, deletePortfolioHolding, deleteTransaction, downloadPortfolio } from '../api'
import { usePrefs } from '../contexts/PrefsContext'
import { CURRENCY_SYMBOL, formatMoney, type Currency } from '../utils/currency'
import { marketOf, currencyOfExchange, type Exchange } from '../utils/market'
import { ExchangeSelect } from './ExchangeSelect'
import { InfoTip } from './InfoTip'
import type { GlossaryKey } from '../utils/glossary'
import { PORTFOLIO_REFRESH_MS } from '../utils/env'
import { overlayFade, scaleIn, collapse, layoutSpring } from '../lib/motion'

type MoneyFmt = (v: number | null | undefined, opts?: { sign?: boolean; compact?: boolean }) => string

// ── Formatting ────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`

const gainText   = (n: number) => n >= 0 ? 'text-emerald-400' : 'text-red-400'
const gainBorder = (n: number) => n >= 0 ? 'border-l-emerald-500/50' : 'border-l-red-500/50'

const parseNum = (s: string) => parseFloat(s.replace(/[^0-9.+-]/g, ''))
const UP_FLASH   = 'rgba(16,185,129,0.35)'
const DOWN_FLASH = 'rgba(239,68,68,0.35)'
const FLAT_FLASH = 'rgba(161,161,170,0.25)'

// ── Stat card ─────────────────────────────────────────────────────────────────
//
// Values refresh on a poll (PORTFOLIO_REFRESH_MS) and otherwise overwrite the
// DOM silently — a brief background flash on change is the difference between
// "did anything move?" and having to re-read every card after each refresh.

function StatCard({
  label, value, sub, valueColor, subColor, accent, tip,
}: {
  label: string
  value: string
  sub?: string
  valueColor?: string
  subColor?: string
  accent?: boolean
  tip?: GlossaryKey
}) {
  const prevRef = useRef(value)
  const [flash, setFlash] = useState<'up' | 'down' | 'flat' | null>(null)
  const [tick, setTick] = useState(0)

  useEffect(() => {
    if (prevRef.current !== value) {
      const oldNum = parseNum(prevRef.current)
      const newNum = parseNum(value)
      setFlash(newNum > oldNum ? 'up' : newNum < oldNum ? 'down' : 'flat')
      setTick(t => t + 1)
      prevRef.current = value
    }
  }, [value])

  const flashColor = flash === 'up' ? UP_FLASH : flash === 'down' ? DOWN_FLASH : FLAT_FLASH

  return (
    <div className={clsx(
      'flex flex-col gap-1.5 rounded-xl border px-4 py-3.5 bg-zinc-900',
      accent ? 'border-indigo-500/25' : 'border-zinc-800',
    )}>
      <span className="flex items-center gap-1.5 text-[10px] font-semibold tracking-widest text-zinc-500">{label}{tip && <InfoTip k={tip} />}</span>
      <motion.span
        key={tick}
        initial={flash ? { backgroundColor: flashColor } : false}
        animate={{ backgroundColor: 'rgba(0,0,0,0)' }}
        transition={{ duration: 0.6, ease: 'easeOut' }}
        className={clsx('text-lg font-bold font-mono leading-none rounded px-0.5 -mx-0.5 w-fit', valueColor ?? 'text-zinc-100')}
      >
        {value}
      </motion.span>
      {sub && <span className={clsx('text-xs font-mono', subColor ?? 'text-zinc-500')}>{sub}</span>}
    </div>
  )
}

// ── Loading skeleton ──────────────────────────────────────────────────────────

function Skeleton() {
  return (
    <div className="space-y-4 animate-pulse">
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-[72px] rounded-xl bg-zinc-800/60" />
        ))}
      </div>
      <div className="h-10 rounded-xl bg-zinc-800/60" />
      {Array.from({ length: 5 }).map((_, i) => (
        <div key={i} className="h-14 rounded-xl bg-zinc-800/40" />
      ))}
    </div>
  )
}

// ── Empty state ───────────────────────────────────────────────────────────────

function EmptyState({ onAdd }: { onAdd: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-24 text-center">
      <div className="w-16 h-16 rounded-2xl bg-zinc-800 border border-zinc-700 flex items-center justify-center mb-5">
        <Briefcase size={26} className="text-zinc-500" />
      </div>
      <h3 className="text-sm font-semibold text-zinc-200 mb-1.5">No positions yet</h3>
      <p className="text-xs text-zinc-600 max-w-xs leading-relaxed mb-6">
        Start building your portfolio by logging your first purchase. Your holdings,
        cost basis, and unrealized gains will appear here.
      </p>
      <button
        onClick={onAdd}
        className="flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
      >
        <Plus size={14} />
        Add First Position
      </button>
    </div>
  )
}

// ── Allocation donut ──────────────────────────────────────────────────────────

const DONUT_COLORS = ['#E4B95B', '#2FBF71', '#5B9BE4', '#B45BE4', '#E45B7B', '#5BE4C4', '#E48A5B', '#8AE45B']

function AllocationCard({ holdings, money }: { holdings: StockHolding[]; money: MoneyFmt }) {
  const [open, setOpen] = useState(true)
  // Holdings with no live quote (stock_value == null) are left out of the
  // chart entirely rather than plotted as a $0 sliver — same reasoning as
  // excluding them from portfolio_value: an unpriced holding isn't "worth
  // nothing", it's "unknown", and the donut has no way to represent that.
  const withValue = holdings.filter((h): h is StockHolding & { stock_value: number } =>
    h.stock_value != null && h.stock_value > 0)
  if (withValue.length < 2) return null
  const total = withValue.reduce((sum, h) => sum + h.stock_value, 0)
  const sorted = [...withValue].sort((a, b) => b.stock_value - a.stock_value)
  const top = sorted.slice(0, 8)
  const rest = sorted.slice(8)
  const data = [
    ...top.map(h => ({ name: h.ticker, value: h.stock_value })),
    ...(rest.length ? [{ name: 'Other', value: rest.reduce((s, h) => s + h.stock_value, 0) }] : []),
  ]
  const unpriced = holdings.filter(h => h.stock_value == null).length

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div
        onClick={() => setOpen(o => !o)}
        className={clsx('flex items-center gap-1.5 text-[10px] font-semibold tracking-widest text-zinc-500 cursor-pointer', open && 'mb-2')}
      >
        ALLOCATION <InfoTip k="allocation" />
        {unpriced > 0 && (
          <span className="ml-auto text-zinc-600 font-normal normal-case tracking-normal">
            {unpriced} holding{unpriced > 1 ? 's' : ''} excluded (price unavailable)
          </span>
        )}
        <button
          onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
          title={open ? 'Minimize' : 'Expand'}
          className={clsx('p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors', !unpriced && 'ml-auto')}
        >
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
            <div className="flex items-center gap-6 flex-wrap">
              <div className="w-40 h-40 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={data} dataKey="value" nameKey="name" innerRadius={44} outerRadius={70} paddingAngle={2} stroke="none">
                      {data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
                    </Pie>
                    <ChartTooltip
                      formatter={(v: number, name: string) => [`${money(v)} · ${((v / total) * 100).toFixed(1)}%`, name]}
                      contentStyle={{ background: '#0A0E16', border: '1px solid #2A3446', borderRadius: 8, fontSize: 11, fontFamily: 'IBM Plex Mono, monospace' }}
                      itemStyle={{ color: '#E4E4E7' }}
                      labelStyle={{ color: '#E4E4E7' }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="flex-1 min-w-[180px] grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                {data.map((d, i) => (
                  <div key={d.name} className="flex items-center gap-2 text-xs font-mono">
                    <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                    <span className="text-zinc-300">{d.name}</span>
                    <span className="ml-auto text-zinc-500">{((d.value / total) * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Sector / industry breakdown ───────────────────────────────────────────────
//
// Groups the current market's holdings by sector and by industry (via the
// cached /stocks/classification endpoint) and charts them two ways:
//   · Invested value — each group's share of total cost basis (total_invested)
//   · Holdings count — how many positions fall in each group
// The US/India split comes from the page's existing market tabs.

type BreakdownMetric = 'invested' | 'count'

function groupBy(
  holdings: StockHolding[],
  classification: ClassificationMap,
  dim: 'sector' | 'industry',
  metric: BreakdownMetric,
): { name: string; value: number; tickers: string[] }[] {
  const groups = new Map<string, { value: number; tickers: string[] }>()
  for (const h of holdings) {
    const label = classification[h.ticker]?.[dim] ?? 'Unclassified'
    const weight = metric === 'invested' ? Number(h.total_invested) : 1
    if (metric === 'invested' && !(weight > 0)) continue
    const g = groups.get(label) ?? { value: 0, tickers: [] }
    g.value += weight
    g.tickers.push(h.ticker)
    groups.set(label, g)
  }
  return [...groups.entries()]
    .map(([name, g]) => ({ name, ...g }))
    .sort((a, b) => b.value - a.value)
}

function BreakdownPie({
  title, data, metric, money,
}: {
  title: string
  data: { name: string; value: number; tickers: string[] }[]
  metric: BreakdownMetric
  money: MoneyFmt
}) {
  const total = data.reduce((s, d) => s + d.value, 0)
  if (data.length === 0 || total <= 0) {
    return (
      <div className="flex-1 min-w-[260px]">
        <p className="text-[10px] font-semibold tracking-widest text-zinc-500 mb-2">{title}</p>
        <p className="text-xs text-zinc-600 py-6">Nothing to chart yet.</p>
      </div>
    )
  }
  return (
    <div className="flex-1 min-w-[260px]">
      <p className="text-[10px] font-semibold tracking-widest text-zinc-500 mb-1">{title}</p>
      <div className="h-56">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={data}
              dataKey="value"
              nameKey="name"
              innerRadius={40}
              outerRadius={68}
              paddingAngle={2}
              stroke="none"
            >
              {data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)}
            </Pie>
            <ChartTooltip
              formatter={(v: number, name: string, entry: { payload?: { tickers?: string[] } }) => {
                const pct = ((v / total) * 100).toFixed(1)
                const tickers = entry?.payload?.tickers ?? []
                const shown = tickers.slice(0, 6).join(', ') + (tickers.length > 6 ? ', …' : '')
                const amount = metric === 'invested'
                  ? `${money(v)} · ${pct}%`
                  : `${v} holding${v === 1 ? '' : 's'} · ${pct}%`
                return [`${amount}${shown ? ` — ${shown}` : ''}`, name]
              }}
              contentStyle={{
                background: '#0A0E16',
                border: '1px solid #2A3446',
                borderRadius: 8,
                fontSize: 11,
                fontFamily: 'IBM Plex Mono, monospace',
                maxWidth: 280,
                whiteSpace: 'normal',
                wordBreak: 'break-word',
              }}
              itemStyle={{ color: '#E4E4E7', whiteSpace: 'normal' }}
              labelStyle={{ color: '#E4E4E7' }}
            />
            <Legend
              verticalAlign="bottom"
              iconType="square"
              iconSize={8}
              formatter={(value: string) => <span className="text-[10px] font-mono text-zinc-400">{value}</span>}
            />
          </PieChart>
        </ResponsiveContainer>
      </div>
    </div>
  )
}

function BreakdownCard({
  holdings, market, money,
}: {
  holdings: StockHolding[]
  market: Market
  money: MoneyFmt
}) {
  const [classification, setClassification] = useState<ClassificationMap | null>(null)
  const [metric, setMetric] = useState<BreakdownMetric>('invested')
  const [failed, setFailed] = useState(false)
  const [open, setOpen] = useState(true)

  const tickers = useMemo(
    () => holdings.filter(h => h.shares > 0).map(h => h.ticker).sort(),
    [holdings],
  )
  const tickersKey = tickers.join(',')

  useEffect(() => {
    if (tickers.length === 0) { setClassification({}); return }
    let cancelled = false
    setClassification(null)
    setFailed(false)
    fetchClassification(tickers)
      .then(map => { if (!cancelled) setClassification(map) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tickersKey])

  const active = useMemo(() => holdings.filter(h => h.shares > 0), [holdings])
  if (active.length < 2) return null
  if (failed) return null

  const sectorData = classification ? groupBy(active, classification, 'sector', metric) : []
  const industryData = classification ? groupBy(active, classification, 'industry', metric) : []

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5">
      <div className={clsx('flex items-center gap-2 flex-wrap', open && 'mb-3')}>
        <p className="flex items-center gap-1.5 text-[10px] font-semibold tracking-widest text-zinc-500">
          SECTOR &amp; INDUSTRY BREAKDOWN <InfoTip k="allocation" />
        </p>
        <span className="text-[10px] text-zinc-600 font-mono">
          {market === 'IN' ? 'India · NSE/BSE' : 'US · NYSE/NASDAQ'} portfolio
        </span>
        {open && (
          <div className="ml-auto flex rounded-lg overflow-hidden border border-zinc-800">
            {([
              { value: 'invested' as BreakdownMetric, label: 'Invested value' },
              { value: 'count' as BreakdownMetric, label: 'Holdings count' },
            ]).map(({ value, label }) => (
              <button
                key={value}
                onClick={() => setMetric(value)}
                className={clsx(
                  'relative px-2.5 py-1 text-[10px] font-medium transition-colors',
                  metric === value ? 'text-white' : 'text-zinc-400 hover:bg-zinc-950 hover:text-zinc-200',
                )}
              >
                {metric === value && (
                  <motion.span
                    layoutId="breakdown-metric-pill"
                    transition={layoutSpring}
                    className="absolute inset-0 bg-indigo-600 -z-10"
                  />
                )}
                {label}
              </button>
            ))}
          </div>
        )}
        <button
          onClick={() => setOpen(o => !o)}
          title={open ? 'Minimize' : 'Expand'}
          className={clsx('p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors', !open && 'ml-auto')}
        >
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
            {classification === null ? (
              <div className="flex gap-6">
                <div className="flex-1 h-56 rounded-lg bg-zinc-800/50 animate-pulse" />
                <div className="flex-1 h-56 rounded-lg bg-zinc-800/50 animate-pulse" />
              </div>
            ) : (
              <div className="flex gap-6 flex-wrap">
                <BreakdownPie title="BY SECTOR" data={sectorData} metric={metric} money={money} />
                <BreakdownPie title="BY INDUSTRY" data={industryData} metric={metric} money={money} />
              </div>
            )}

            <p className="mt-2 text-[10px] text-zinc-600">
              {metric === 'invested'
                ? 'Slices are each group\u2019s share of your invested amount (cost basis of currently held shares).'
                : 'Slices are how many of your positions fall in each group.'}
            </p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}

// ── Transaction modal ─────────────────────────────────────────────────────────

interface TxModalProps {
  mode: 'buy' | 'sell'
  ticker: string
  tickerEditable?: boolean
  initialExchange?: Exchange
  maxShares?: number
  onClose: () => void
  onSubmit: (ticker: string, shares: number, price: number, date: string, exchange?: Exchange) => Promise<void>
}

function TxModal({ mode, ticker: initTicker, tickerEditable = false, initialExchange, maxShares, onClose, onSubmit }: TxModalProps) {
  const today = new Date().toLocaleDateString('en-CA')  // yyyy-mm-dd in local time
  const [ticker, setTicker]   = useState(initTicker.toUpperCase())
  const [exchange, setExchange] = useState<Exchange>(initialExchange ?? 'US')
  const [shares, setShares]   = useState('')
  const [price, setPrice]     = useState('')
  const [date, setDate]       = useState(today)
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const currency: Currency = tickerEditable ? currencyOfExchange(exchange) : (marketOf(ticker) === 'IN' ? 'INR' : 'USD')

  const sharesNum = parseInt(shares, 10)
  const priceNum  = parseFloat(price)
  const total     = !isNaN(sharesNum) && !isNaN(priceNum) && sharesNum > 0 && priceNum > 0
    ? sharesNum * priceNum
    : null

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    if (!ticker.trim() || isNaN(sharesNum) || sharesNum <= 0 || isNaN(priceNum) || priceNum <= 0) {
      setError('Please fill in all fields with valid values.')
      return
    }
    if (mode === 'sell' && maxShares !== undefined && sharesNum > maxShares) {
      setError(`Cannot sell ${sharesNum} shares — only ${maxShares} held.`)
      return
    }
    setLoading(true)
    setError(null)
    try {
      await onSubmit(ticker.trim().toUpperCase(), sharesNum, priceNum, date, tickerEditable ? exchange : undefined)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <motion.div
      variants={overlayFade}
      initial="hidden"
      animate="show"
      exit="exit"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        variants={scaleIn}
        className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl"
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              {mode === 'buy' ? 'Log Purchase' : 'Log Sale'}
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              {mode === 'buy' ? 'Record shares you purchased.' : 'Record shares you sold.'}
            </p>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handle} className="space-y-4">
          {/* Ticker */}
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              TICKER
            </label>
            <input
              type="text"
              value={ticker}
              onChange={e => setTicker(e.target.value.toUpperCase())}
              readOnly={!tickerEditable}
              className={clsx(
                'w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono',
                'text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors',
                !tickerEditable && 'opacity-50 cursor-not-allowed select-none',
              )}
              placeholder="e.g. AAPL"
            />
          </div>

          {/* Exchange — only relevant when adding a brand-new position */}
          {tickerEditable && (
            <div>
              <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
                EXCHANGE
              </label>
              <ExchangeSelect value={exchange} onChange={setExchange} />
            </div>
          )}

          {/* Shares */}
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              SHARES
              {mode === 'sell' && maxShares != null && (
                <span className="ml-2 normal-case font-normal tracking-normal text-zinc-600">
                  max {maxShares}
                </span>
              )}
            </label>
            <input
              type="number"
              min={1}
              max={mode === 'sell' ? maxShares : undefined}
              value={shares}
              onChange={e => setShares(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="0"
            />
          </div>

          {/* Price */}
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              {mode === 'buy' ? 'PRICE PAID PER SHARE' : 'PRICE SOLD PER SHARE'}
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 text-sm font-mono pointer-events-none">
                {CURRENCY_SYMBOL[currency]}
              </span>
              <input
                type="number"
                min={0.01}
                step="0.01"
                value={price}
                onChange={e => setPrice(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-7 pr-3 py-2 text-sm font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
                placeholder="0.00"
              />
            </div>
          </div>

          {/* Date */}
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              DATE
            </label>
            <input
              type="date"
              value={date}
              max={today}
              onChange={e => setDate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          {/* Total preview */}
          {total != null && (
            <div className="bg-zinc-800/80 border border-zinc-700/50 rounded-lg px-3 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                Total {mode === 'buy' ? 'cost' : 'proceeds'}
              </span>
              <span className="text-sm font-mono font-semibold text-zinc-200">
                {CURRENCY_SYMBOL[currency]}{fmt(total)}
              </span>
            </div>
          )}

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading}
            className={clsx(
              'w-full py-2.5 rounded-lg text-sm font-semibold transition-colors',
              'flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed',
              mode === 'buy'
                ? 'bg-emerald-600 hover:bg-emerald-500 text-white'
                : 'bg-red-600 hover:bg-red-500 text-white',
            )}
          >
            {loading && <RefreshCw size={13} className="animate-spin" />}
            {mode === 'buy' ? 'Record Purchase' : 'Record Sale'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  )
}

// ── Holding row ───────────────────────────────────────────────────────────────

function TxRow({ txn, money, onDeleteRequest }: { txn: StockPurchaseHistory; money: MoneyFmt; onDeleteRequest: () => void }) {
  const rowPl = txn.sale ? (txn.sold_at - txn.bought_at) * txn.shares : null

  return (
    <tr className="border-b border-zinc-800/40 hover:bg-zinc-800/20 transition-colors">
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-500 whitespace-nowrap">{txn.date}</td>
      <td className="px-5 py-2.5">
        <span className={clsx(
          'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold',
          txn.sale ? 'bg-red-500/10 text-red-400' : 'bg-emerald-500/10 text-emerald-400',
        )}>
          {txn.sale ? 'SELL' : 'BUY'}
        </span>
      </td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-300">{txn.shares}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">
        {txn.sale ? <span className="text-zinc-700">—</span> : txn.shares_remaining}
      </td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">{money(txn.bought_at)}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">
        {txn.sale ? money(txn.sold_at) : <span className="text-zinc-700">—</span>}
      </td>
      <td className="px-5 py-2.5 font-mono text-xs">
        {rowPl != null ? (
          <span className={gainText(rowPl)}>
            {money(rowPl, { sign: true })}
          </span>
        ) : <span className="text-zinc-700">—</span>}
      </td>
      <td className="px-4 py-2.5">
        <button
          onClick={onDeleteRequest}
          title="Delete transaction"
          className="p-0.5 text-zinc-700 hover:text-red-400 transition-colors"
        >
          <Trash2 size={11} />
        </button>
      </td>
    </tr>
  )
}

function HoldingRow({
  holding, money, expanded, onToggle, onBuy, onSell, onDelete, onViewTicker, onDeleteTxn,
}: {
  holding: StockHolding
  money: MoneyFmt
  expanded: boolean
  onToggle: () => void
  onBuy: () => void
  onSell: () => void
  onDelete: () => void
  onViewTicker: () => void
  onDeleteTxn: (txnId: number, isLast: boolean) => void
}) {
  const pl    = holding.profit_loss
  const plPct = holding.profit_loss_percentage
  // current_price (and everything derived from it) is null when the last quote
  // fetch failed — an unpriced holding is neither a gain nor a loss, it's
  // unknown, so it gets neutral styling instead of defaulting into "gain".
  const hasPrice = holding.current_price != null

  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0, height: 0 }}
      transition={layoutSpring}
      className={clsx('border-l-2 transition-colors overflow-hidden', hasPrice ? gainBorder(pl!) : 'border-l-zinc-700')}
    >
      {/* Main summary row — click anywhere to expand */}
      <div
        onClick={onToggle}
        className="grid grid-cols-[minmax(140px,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_32px_32px] gap-3 px-5 py-3.5 items-center hover:bg-zinc-800/40 cursor-pointer transition-colors group"
      >
        {/* Position: ticker badge + company name (ticker) */}
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={clsx(
            'px-2 py-1 rounded-md text-[11px] font-bold font-mono shrink-0 whitespace-nowrap',
            !hasPrice ? 'bg-zinc-700/30 text-zinc-400' : pl! >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400',
          )}>
            {holding.ticker}
          </span>
          <div
            className="min-w-0"
            title={holding.company_name ? `${holding.company_name} (${holding.ticker})` : holding.ticker}
          >
            <div className="text-sm font-medium text-zinc-100 truncate">
              {holding.company_name
                ? <>{holding.company_name} <span className="text-zinc-500 font-normal text-xs">({holding.ticker})</span></>
                : holding.ticker}
            </div>
            {holding.sold_shares > 0 && (
              <div className="text-[10px] text-zinc-600 leading-none mt-0.5">
                {holding.sold_shares} sold
              </div>
            )}
          </div>
        </div>

        {/* Shares */}
        <span className="text-sm font-mono text-zinc-300 text-right">{holding.shares}</span>

        {/* Avg cost */}
        <span className="text-sm font-mono text-zinc-400 text-right">{money(holding.average_cost)}</span>

        {/* Current */}
        <span
          className="text-sm font-mono text-zinc-300 text-right"
          title={hasPrice ? undefined : 'Price unavailable — last fetch failed'}
        >
          {hasPrice ? money(holding.current_price) : <span className="text-zinc-600 italic">unavailable</span>}
        </span>

        {/* Market value */}
        <span className="text-sm font-mono text-zinc-300 text-right">{money(holding.stock_value)}</span>

        {/* Unrealized P&L */}
        <div className="text-right">
          {hasPrice ? (
            <>
              <div className={clsx('text-sm font-mono font-medium leading-none', gainText(pl!))}>
                {money(pl, { sign: true })}
              </div>
              <div className={clsx('text-[10px] font-mono mt-0.5', gainText(pl!))}>
                {fmtPct(plPct!)}
              </div>
            </>
          ) : (
            <div className="text-sm font-mono text-zinc-600">—</div>
          )}
        </div>

        {/* Realized gains */}
        <span className={clsx(
          'text-sm font-mono text-right',
          holding.total_earned > 0 ? 'text-emerald-400' : 'text-zinc-500',
        )}>
          {money(holding.total_earned)}
        </span>

        {/* Tracker link */}
        <div className="flex items-center justify-center">
          <button
            onClick={e => { e.stopPropagation(); onViewTicker() }}
            title={`View ${holding.ticker} on the tracker`}
            className="p-1 text-zinc-600 hover:text-indigo-400 hover:bg-indigo-500/10 rounded transition-colors"
          >
            <BarChart2 size={13} />
          </button>
        </div>

        {/* Chevron */}
        <div className="flex items-center justify-center">
          {expanded
            ? <ChevronUp  size={13} className="text-zinc-500" />
            : <ChevronDown size={13} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />}
        </div>
      </div>

      {/* Expanded panel */}
      <AnimatePresence>
      {expanded && (
        <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }} className="border-t border-zinc-800/60 bg-zinc-950/60">
          {/* Actions bar */}
          <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-b border-zinc-800/40">
            <button
              onClick={e => { e.stopPropagation(); onBuy() }}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-lg transition-colors"
            >
              <ArrowDownLeft size={11} />
              Buy more
            </button>
            <button
              onClick={e => { e.stopPropagation(); onSell() }}
              disabled={holding.shares === 0}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium text-amber-400 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/20 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <ArrowUpRight size={11} />
              Sell
            </button>

            <div className="flex items-center gap-4 ml-3 text-xs text-zinc-600">
              <span>
                Cost basis{' '}
                <span className="font-mono text-zinc-400">{money(holding.total_invested)}</span>
              </span>
            </div>

            <button
              onClick={e => { e.stopPropagation(); onDelete() }}
              className="ml-auto flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-red-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors"
            >
              <Trash2 size={11} />
              Remove
            </button>
          </div>

          {/* Transaction history */}
          {holding.trade_history.length === 0 ? (
            <p className="px-5 py-4 text-xs text-zinc-600 italic">No transactions recorded.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-zinc-800/40">
                    {['Date', 'Type', 'Shares', 'Remaining', 'Bought @', 'Sold @', 'P&L', ''].map(col => (
                      <th
                        key={col}
                        className="px-5 py-2 text-left text-[10px] tracking-widest text-zinc-600 font-semibold whitespace-nowrap"
                      >
                        {col}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {[...holding.trade_history].reverse().map(txn => (
                    <TxRow
                      key={txn.id}
                      txn={txn}
                      money={money}
                      onDeleteRequest={() => onDeleteTxn(txn.id, holding.trade_history.length === 1)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </motion.div>
      )}
      </AnimatePresence>
    </motion.div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function PortfolioPage({
  onViewTicker,
  onTickerRemoved,
  onTickerAdded,
  onData,
}: {
  onViewTicker: (ticker: string) => void
  onTickerRemoved?: (ticker: string) => void
  onTickerAdded?: () => void
  /** Fired with the latest fetched portfolio — lets the AI chat widget stay aware of it without a duplicate fetch. */
  onData?: (portfolio: PortfolioResponse | null) => void
}) {
  const { market: prefsMarket, setMarket: setPrefsMarket } = usePrefs()
  const [tab, setTab] = useState<Market>(prefsMarket === 'IN' ? 'IN' : 'US')
  const [portfolio, setPortfolio]     = useState<PortfolioResponse | null>(null)
  const [loading, setLoading]         = useState(true)
  const [error, setError]             = useState<string | null>(null)
  const [expanded, setExpanded]       = useState<string | null>(null)
  const [modal, setModal]             = useState<{ mode: 'buy' | 'sell'; ticker: string } | null>(null)
  const [addOpen, setAddOpen]         = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [txnDeleteTarget, setTxnDeleteTarget] = useState<{ ticker: string; txnId: number; isLast: boolean } | null>(null)
  const [txnDeleteLoading, setTxnDeleteLoading] = useState(false)
  const [txnDeleteError, setTxnDeleteError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated]       = useState<Date | null>(null)
  const [downloading, setDownloading]       = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await fetchPortfolio(tab)
      setPortfolio(result)
      onData?.(result)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load portfolio')
    } finally {
      setLoading(false)
    }
  }, [tab, onData])

  // The tab's native currency: every aggregate below is stored in it.
  const nativeCcy: Currency = tab === 'IN' ? 'INR' : 'USD'
  const money: MoneyFmt = useCallback(
    (v, opts) => formatMoney(v, nativeCcy, opts),
    [nativeCcy],
  )

  function switchTab(m: Market) {
    setTab(m)
    if (prefsMarket !== 'ALL') setPrefsMarket(m)
    setExpanded(null)
  }

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const id = setInterval(load, PORTFOLIO_REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  async function submitBuy(ticker: string, shares: number, price: number, date: string, exchange?: Exchange) {
    await logBuy(ticker, shares, price, date, exchange)
    await load()
    onTickerAdded?.()
  }

  async function submitSell(ticker: string, shares: number, price: number, date: string) {
    await logSell(ticker, shares, price, date)
    await load()
  }

  function openTxnDelete(ticker: string, txnId: number, isLast: boolean) {
    setTxnDeleteTarget({ ticker, txnId, isLast })
    setTxnDeleteError(null)
  }

  async function handleConfirmDeleteTxn() {
    if (!txnDeleteTarget) return
    setTxnDeleteLoading(true)
    setTxnDeleteError(null)
    try {
      const removedTicker = txnDeleteTarget.ticker
      const wasLast = txnDeleteTarget.isLast
      await deleteTransaction(removedTicker, txnDeleteTarget.txnId)
      if (wasLast && expanded === removedTicker) setExpanded(null)
      setTxnDeleteTarget(null)
      await load()
      if (wasLast) onTickerRemoved?.(removedTicker)
    } catch (e) {
      setTxnDeleteError(e instanceof Error ? e.message : 'Failed to delete transaction.')
    } finally {
      setTxnDeleteLoading(false)
    }
  }

  async function handleDelete() {
    if (!deleteTarget) return
    setDeleteLoading(true)
    const removedTicker = deleteTarget
    try {
      await deletePortfolioHolding(removedTicker)
      if (expanded === removedTicker) setExpanded(null)
      setDeleteTarget(null)
      await load()
      onTickerRemoved?.(removedTicker)
    } catch {
      setDeleteLoading(false)
    } finally {
      setDeleteLoading(false)
    }
  }

  const holdings  = portfolio?.holdings ?? []
  const netPl     = portfolio?.net_profit_loss ?? 0
  const totalRet  = portfolio?.total_return ?? 0

  return (
    <div className="flex-1 overflow-y-auto p-6 min-w-0">
      <div className="max-w-6xl mx-auto flex flex-col gap-6">

        {/* ── Page header ──────────────────────────────────────────────── */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-5">
            <div>
              <h1 className="font-display text-lg font-bold tracking-tight text-zinc-100">My Portfolios</h1>
              <p className="text-xs text-zinc-500 mt-0.5">
                Track positions, log transactions, monitor performance
              </p>
            </div>
            {/* Market switch: separate portfolios for US and Indian stocks */}
            <div className="flex rounded-lg overflow-hidden border border-zinc-800">
              {([
                { value: 'US' as Market, label: 'US · NYSE/NASDAQ' },
                { value: 'IN' as Market, label: 'India · NSE/BSE' },
              ]).map(({ value, label }) => (
                <button
                  key={value}
                  onClick={() => switchTab(value)}
                  className={clsx(
                    'relative px-3.5 py-2 text-xs font-medium transition-colors',
                    tab === value ? 'text-white' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
                  )}
                >
                  {tab === value && (
                    <motion.span
                      layoutId="portfolio-market-tab-pill"
                      transition={layoutSpring}
                      className="absolute inset-0 bg-indigo-600 -z-10"
                    />
                  )}
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex flex-col items-center gap-0.5">
              <button
                onClick={load}
                disabled={loading}
                title="Refresh portfolio"
                className="p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 rounded-lg transition-colors disabled:opacity-40"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              </button>
              {lastUpdated && (
                <span className="text-[10px] text-zinc-600 whitespace-nowrap">
                  {lastUpdated.toLocaleString([], { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                </span>
              )}
            </div>
            <button
              onClick={async () => {
                setDownloading(true)
                try { await downloadPortfolio(tab) } catch {}
                setDownloading(false)
              }}
              disabled={downloading || !portfolio || portfolio.holdings.length === 0}
              title="Download portfolio as Excel"
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20 border border-emerald-500/20 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <FileDown size={14} className={downloading ? 'animate-bounce' : ''} />
              Export
            </button>
            <button
              onClick={() => setAddOpen(true)}
              className="flex items-center gap-2 px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
            >
              <Plus size={14} />
              Add Position
            </button>
          </div>
        </div>

        {/* ── Content ──────────────────────────────────────────────────── */}
        {loading ? (
          <Skeleton />
        ) : error ? (
          <div className="flex flex-col items-center justify-center py-20 text-center gap-3">
            <p className="text-sm text-red-400">{error}</p>
            <button
              onClick={load}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Try again
            </button>
          </div>
        ) : portfolio && (
          <>
            {/* ── Summary stats ──────────────────────────────────────── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
              <StatCard
                label="PORTFOLIO VALUE"
                tip="portfolio_value"
                value={money(portfolio.portfolio_value)}
                accent
              />
              <StatCard
                label="COST BASIS"
                tip="total_invested"
                value={money(portfolio.total_invested)}
              />
              <StatCard
                label="UNREALIZED RETURN"
                tip="total_return"
                value={money(totalRet, { sign: true })}
                valueColor={gainText(totalRet)}
                sub={fmtPct(portfolio.return_percentage)}
                subColor={gainText(totalRet)}
              />
              <StatCard
                label="REALIZED GAINS"
                tip="realized_gains"
                value={money(portfolio.realized_gains)}
                valueColor={portfolio.realized_gains > 0 ? gainText(1) : undefined}
              />
              <StatCard
                label="NET P&L"
                tip="net_pl"
                value={money(netPl, { sign: true })}
                valueColor={gainText(netPl)}
              />
            </div>

            {/* ── Allocation ─────────────────────────────────────────── */}
            <AllocationCard holdings={holdings} money={money} />

            {/* ── Sector / industry breakdown ─────────────────────────── */}
            <BreakdownCard holdings={holdings} market={tab} money={money} />

            {/* ── Holdings ───────────────────────────────────────────── */}
            {holdings.length === 0 ? (
              <EmptyState onAdd={() => setAddOpen(true)} />
            ) : (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                {/* Column headers */}
                <div className="grid grid-cols-[minmax(140px,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_32px_32px] gap-3 px-5 py-2.5 border-b border-zinc-800 text-[10px] font-semibold tracking-widest text-zinc-500">
                  <span>POSITION</span>
                  <span className="text-right">SHARES</span>
                  <span className="flex items-center justify-end gap-1">AVG COST <InfoTip k="avg_cost" align="right" /></span>
                  <span className="text-right">CURRENT</span>
                  <span className="text-right">VALUE</span>
                  <span className="flex items-center justify-end gap-1">UNREALIZED P&L <InfoTip k="total_return" align="right" /></span>
                  <span className="flex items-center justify-end gap-1">REALIZED <InfoTip k="realized_gains" align="right" /></span>
                  <span />
                  <span />
                </div>

                {/* Rows */}
                <div className="divide-y divide-zinc-800">
                  <AnimatePresence initial={false}>
                    {holdings.map(h => (
                      <HoldingRow
                        money={(v, opts) => formatMoney(v, h.currency ?? nativeCcy, opts)}
                        key={h.ticker}
                        holding={h}
                        expanded={expanded === h.ticker}
                        onToggle={() => setExpanded(p => p === h.ticker ? null : h.ticker)}
                        onBuy={()         => setModal({ mode: 'buy',  ticker: h.ticker })}
                        onSell={()        => setModal({ mode: 'sell', ticker: h.ticker })}
                        onDelete={()      => setDeleteTarget(h.ticker)}
                        onViewTicker={()           => onViewTicker(h.ticker)}
                        onDeleteTxn={(id, isLast)  => openTxnDelete(h.ticker, id, isLast)}
                      />
                    ))}
                  </AnimatePresence>
                </div>

                {/* Table footer */}
                <div className="flex items-center justify-between px-5 py-2.5 border-t border-zinc-800 bg-zinc-950/40">
                  <span className="text-[10px] text-zinc-600">
                    {holdings.length} position{holdings.length !== 1 ? 's' : ''} · {portfolio.total_shares} shares held
                  </span>
                  <span className={clsx('text-xs font-mono font-semibold', gainText(netPl))}>
                    Net {money(netPl, { sign: true })}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────────────────────── */}

      <AnimatePresence>
        {addOpen && (
          <TxModal
            key="add"
            mode="buy"
            ticker=""
            tickerEditable
            initialExchange={tab === 'IN' ? 'NSE' : 'US'}
            onClose={() => setAddOpen(false)}
            onSubmit={submitBuy}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {modal && (
          <TxModal
            key="txn"
            mode={modal.mode}
            ticker={modal.ticker}
            maxShares={modal.mode === 'sell'
              ? (holdings.find(h => h.ticker === modal.ticker)?.shares ?? 0)
              : undefined}
            onClose={() => setModal(null)}
            onSubmit={modal.mode === 'buy' ? submitBuy : submitSell}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {txnDeleteTarget && (
          <motion.div
            key="txn-delete"
            variants={overlayFade}
            initial="hidden"
            animate="show"
            exit="exit"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
            onClick={e => { if (e.target === e.currentTarget && !txnDeleteLoading) setTxnDeleteTarget(null) }}
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-96 shadow-2xl">
              <h2 className="text-sm font-semibold text-zinc-100 mb-3">Delete transaction?</h2>

              {txnDeleteTarget.isLast ? (
                <div className="flex items-start gap-3 bg-amber-500/8 border border-amber-500/25 rounded-xl px-4 py-3 mb-4">
                  <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <p className="text-xs font-semibold text-amber-400">This is the only transaction</p>
                    <p className="text-xs text-zinc-400 leading-relaxed">
                      Deleting it will permanently remove{' '}
                      <span className="font-mono text-zinc-200">{txnDeleteTarget.ticker}</span>{' '}
                      from your portfolio, including all history.
                    </p>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-zinc-400 leading-relaxed mb-4">
                  This transaction will be removed and your position recalculated using FIFO. This cannot be undone.
                </p>
              )}

              {txnDeleteError && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 mb-4">
                  <X size={13} className="text-red-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-400 leading-relaxed">{txnDeleteError}</p>
                </div>
              )}

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setTxnDeleteTarget(null); setTxnDeleteError(null) }}
                  disabled={txnDeleteLoading}
                  className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDeleteTxn}
                  disabled={txnDeleteLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors disabled:opacity-40"
                >
                  {txnDeleteLoading ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={11} />}
                  {txnDeleteTarget.isLast ? 'Remove Position' : 'Delete Transaction'}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {deleteTarget && (
          <motion.div
            key="holding-delete"
            variants={overlayFade}
            initial="hidden"
            animate="show"
            exit="exit"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
            onClick={e => { if (e.target === e.currentTarget) setDeleteTarget(null) }}
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-80 shadow-2xl">
              <h2 className="text-sm font-semibold text-zinc-100 mb-1">
                Remove {deleteTarget}?
              </h2>
              <p className="text-xs text-zinc-400 leading-relaxed mb-5">
                This permanently deletes the holding and all its transaction history.
                This cannot be undone.
              </p>
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setDeleteTarget(null)}
                  disabled={deleteLoading}
                  className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleDelete}
                  disabled={deleteLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors disabled:opacity-40"
                >
                  {deleteLoading
                    ? <RefreshCw size={11} className="animate-spin" />
                    : <Trash2 size={11} />}
                  Remove
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
