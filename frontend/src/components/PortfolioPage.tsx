import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import clsx from 'clsx'
import {
  Plus, ChevronDown, ChevronUp,
  Trash2, RefreshCw, X, Briefcase, ArrowDownLeft, ArrowUpRight,
  BarChart2, AlertTriangle, FileDown, FileUp, Upload, Pencil, Coins,
} from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import { PieChart, Pie, Cell, Tooltip as ChartTooltip, ResponsiveContainer } from 'recharts'
import type { BuyLot, ClassificationMap, DividendEntry, ImportApplyRow, ImportBlockingError, ImportPreviewRow, ImportRowResult, Market, PortfolioImportResult, PortfolioResponse, PortfolioStats, SellLot, StockHolding, StockPurchaseHistory } from '../types'
import {
  fetchPortfolio, fetchClassification, logBuyBulk, logSellBulk, deletePortfolioHolding, deleteTransaction, downloadPortfolio,
  previewPortfolioImport, applyPortfolioImport, syncDividends, addDividend, updateDividend, deleteDividend,
  createPortfolio, renamePortfolio, deletePortfolio,
} from '../api'
import { PortfolioTabs } from './portfolio/PortfolioTabs'
import { CombinedStatsBar } from './portfolio/CombinedStatsBar'
import { PortfolioNameModal } from './portfolio/PortfolioNameModal'
import { DeletePortfolioModal } from './portfolio/DeletePortfolioModal'
import { isGuestModeActive } from '../lib/guestMode'
import { usePrefs } from '../contexts/PrefsContext'
import { CURRENCY_SYMBOL, formatMoney, type Currency } from '../utils/currency'
import { marketOf, currencyOfExchange, displayTicker, type Exchange } from '../utils/market'
import { ExchangeSelect } from './ExchangeSelect'
import { TickerAutocomplete } from './TickerAutocomplete'
import { InfoTip } from './InfoTip'
import type { GlossaryKey } from '../utils/glossary'
import { PORTFOLIO_REFRESH_MS } from '../utils/env'
import { usePersistedState } from '../utils/usePersistedState'
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
      <span className="flex items-center gap-1.5 text-[0.625rem] font-semibold tracking-widest text-zinc-500">{label}{tip && <InfoTip k={tip} />}</span>
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
          <div key={i} className="h-[4.5rem] rounded-xl bg-zinc-800/60" />
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
  const [open, setOpen] = usePersistedState('portfolio-allocation-open', true)
  // Holdings with no live quote (stock_value == null) are left out of the
  // chart entirely rather than plotted as a $0 sliver — same reasoning as
  // excluding them from portfolio_value: an unpriced holding isn't "worth
  // nothing", it's "unknown", and the donut has no way to represent that.
  const withValue = holdings.filter((h): h is StockHolding & { stock_value: number } =>
    h.stock_value != null && h.stock_value > 0)
  if (withValue.length < 2) return null
  const total = withValue.reduce((sum, h) => sum + h.stock_value, 0)
  const sorted = [...withValue].sort((a, b) => b.stock_value - a.stock_value)
  // The chart itself plots every holding — nothing is folded away, it's just
  // a thin slice you can hover. The text list beside it is capped to the
  // top 10 so it doesn't run off the page; the rest is still reachable on hover.
  const data = sorted.map(h => ({ name: h.ticker, value: h.stock_value }))
  const listItems = sorted.slice(0, 10)
  const listRestCount = sorted.length - listItems.length
  const unpriced = holdings.filter(h => h.stock_value == null).length

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-5">
      <div
        onClick={() => setOpen(o => !o)}
        className={clsx('flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[0.625rem] font-semibold tracking-widest text-zinc-500 cursor-pointer', open && 'mb-2')}
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
          className={clsx('tap-target p-1.5 sm:p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors', !unpriced && 'ml-auto')}
        >
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>
      <AnimatePresence>
        {open && (
          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
            <div className="flex flex-col sm:flex-row sm:items-center gap-4 sm:gap-6 sm:flex-wrap">
              <div className="w-40 h-40 shrink-0 self-center sm:self-auto">
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
              <div className="flex-1 min-w-0 sm:min-w-[11.25rem]">
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-1.5">
                  {listItems.map((h, i) => (
                    <div key={h.ticker} className="flex items-center gap-2 text-xs font-mono">
                      <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                      <span className="text-zinc-300">{h.ticker}</span>
                      <span className="ml-auto text-zinc-500">{((h.stock_value / total) * 100).toFixed(1)}%</span>
                    </div>
                  ))}
                </div>
                {listRestCount > 0 && (
                  <p className="mt-1.5 text-[0.625rem] text-zinc-600">
                    +{listRestCount} more — hover the chart to see the rest.
                  </p>
                )}
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
      <div className="flex-1 min-w-0 sm:min-w-[16.25rem]">
        <p className="text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-2">{title}</p>
        <p className="text-xs text-zinc-600 py-6">Nothing to chart yet.</p>
      </div>
    )
  }
  // The chart plots every group (data is already sorted descending by
  // groupBy) — the text list below is capped to the top 5, with the rest
  // still reachable by hovering the chart itself.
  const listItems = data.slice(0, 5)
  const listRestCount = data.length - listItems.length
  return (
    <div className="flex-1 min-w-0 sm:min-w-[16.25rem]">
      <p className="text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1">{title}</p>
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
          </PieChart>
        </ResponsiveContainer>
      </div>
      <div className="mt-1.5 space-y-1">
        {listItems.map((d, i) => (
          <div key={d.name} className="flex items-center gap-2 text-xs font-mono">
            <span className="w-2 h-2 rounded-sm shrink-0" style={{ background: DONUT_COLORS[i % DONUT_COLORS.length] }} />
            <span className="text-zinc-300 truncate">{d.name}</span>
            <span className="ml-auto text-zinc-500 shrink-0">{((d.value / total) * 100).toFixed(1)}%</span>
          </div>
        ))}
        {listRestCount > 0 && (
          <p className="text-[0.625rem] text-zinc-600 pt-0.5">
            +{listRestCount} more — hover the chart to see the rest.
          </p>
        )}
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
  const [open, setOpen] = usePersistedState('portfolio-breakdown-open', true)

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
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-5">
      <div className={clsx('flex items-center gap-2 flex-wrap', open && 'mb-3')}>
        <p className="flex items-center gap-1.5 text-[0.625rem] font-semibold tracking-widest text-zinc-500">
          SECTOR &amp; INDUSTRY BREAKDOWN <InfoTip k="allocation" />
        </p>
        <span className="text-[0.625rem] text-zinc-600 font-mono">
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
                  'relative px-2.5 py-1 text-[0.625rem] font-medium transition-colors',
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
          className={clsx('tap-target p-1.5 sm:p-0.5 text-zinc-600 hover:text-zinc-300 transition-colors', !open && 'ml-auto')}
        >
          {open ? <ChevronUp size={13} /> : <ChevronDown size={13} />}
        </button>
      </div>

      <AnimatePresence>
        {open && (
          <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }}>
            {classification === null ? (
              <div className="flex flex-col lg:flex-row gap-6">
                <div className="flex-1 h-56 rounded-lg bg-zinc-800/50 animate-pulse" />
                <div className="flex-1 h-56 rounded-lg bg-zinc-800/50 animate-pulse" />
              </div>
            ) : (
              <div className="flex flex-col lg:flex-row gap-6 lg:flex-wrap">
                <BreakdownPie title="BY SECTOR" data={sectorData} metric={metric} money={money} />
                <BreakdownPie title="BY INDUSTRY" data={industryData} metric={metric} money={money} />
              </div>
            )}

            <p className="mt-2 text-[0.625rem] text-zinc-600">
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

interface LotDraft {
  key: string
  shares: string
  price: string
  date: string
}

interface ParsedLot {
  shares: number
  price: number
  date: string
  touched: boolean   // user has put something in this row
  valid: boolean      // touched and every field parses to a usable value
}

function parseLot(l: LotDraft): ParsedLot {
  const shares = parseInt(l.shares, 10)
  const price = parseFloat(l.price)
  const touched = l.shares.trim() !== '' || l.price.trim() !== ''
  const valid = touched && !isNaN(shares) && shares > 0 && !isNaN(price) && price > 0 && !!l.date
  return { shares, price, date: l.date, touched, valid }
}

interface TxModalProps {
  mode: 'buy' | 'sell'
  ticker: string
  tickerEditable?: boolean
  initialExchange?: Exchange
  maxShares?: number
  onClose: () => void
  /** Both modes accept one or more lots recorded in a single atomic request —
   *  lets a whole purchase/sale history (different dates/prices) be
   *  backfilled at once instead of one round trip per transaction. */
  onSubmitBuy?: (ticker: string, lots: BuyLot[], exchange?: Exchange) => Promise<void>
  onSubmitSell?: (ticker: string, lots: SellLot[]) => Promise<void>
}

function TxModal({ mode, ticker: initTicker, tickerEditable = false, initialExchange, maxShares, onClose, onSubmitBuy, onSubmitSell }: TxModalProps) {
  const today = new Date().toLocaleDateString('en-CA')  // yyyy-mm-dd in local time
  const [ticker, setTicker]   = useState(initTicker.toUpperCase())
  const [exchange, setExchange] = useState<Exchange>(initialExchange ?? 'US')

  // One or more lots (shares/price/date each), so a whole purchase or sale
  // history can be entered in one sitting instead of reopening the modal
  // per transaction.
  const lotKey = useRef(0)
  function makeLot(): LotDraft {
    lotKey.current += 1
    return { key: String(lotKey.current), shares: '', price: '', date: today }
  }
  const [lots, setLots] = useState<LotDraft[]>(() => [makeLot()])

  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

  const currency: Currency = tickerEditable ? currencyOfExchange(exchange) : (marketOf(ticker) === 'IN' ? 'INR' : 'USD')

  function updateLot(key: string, patch: Partial<LotDraft>) {
    setLots(prev => prev.map(l => l.key === key ? { ...l, ...patch } : l))
  }
  function addLot() {
    setLots(prev => [...prev, makeLot()])
  }
  function removeLot(key: string) {
    setLots(prev => prev.length > 1 ? prev.filter(l => l.key !== key) : prev)
  }

  const parsedLots = lots.map(parseLot)
  const validLotCount = parsedLots.filter(l => l.valid).length
  const total = parsedLots.reduce((sum, l) => l.valid ? sum + l.shares * l.price : sum, 0)
  const noun = mode === 'buy' ? 'purchase' : 'sale'

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    if (!ticker.trim()) {
      setError('Please enter a ticker.')
      return
    }

    const touchedLots = parsedLots.filter(l => l.touched)
    if (touchedLots.length === 0) {
      setError(`Add at least one ${noun}.`)
      return
    }
    const firstBadIdx = parsedLots.findIndex(l => l.touched && !l.valid)
    if (firstBadIdx !== -1) {
      setError(`${mode === 'buy' ? 'Purchase' : 'Sale'} #${firstBadIdx + 1} needs a valid share count, price, and date.`)
      return
    }
    if (mode === 'sell' && maxShares !== undefined) {
      const totalShares = touchedLots.reduce((sum, l) => sum + l.shares, 0)
      if (totalShares > maxShares) {
        setError(`Cannot sell ${totalShares} shares — only ${maxShares} held.`)
        return
      }
    }

    setLoading(true)
    setError(null)
    try {
      if (mode === 'buy') {
        const payload: BuyLot[] = touchedLots.map(l => ({ shares: l.shares, bought_at: l.price, date: l.date }))
        await onSubmitBuy?.(ticker.trim().toUpperCase(), payload, tickerEditable ? exchange : undefined)
      } else {
        const payload: SellLot[] = touchedLots.map(l => ({ shares: l.shares, sold_at: l.price, date: l.date }))
        await onSubmitSell?.(ticker.trim().toUpperCase(), payload)
      }
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div
        variants={scaleIn}
        className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-lg shadow-2xl max-h-[85dvh] overflow-y-auto"
      >
        {/* Header */}
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              {mode === 'buy' ? 'Log Purchase' : 'Log Sale'}
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              {mode === 'buy'
                ? 'Record one or more purchases — handy for backfilling your history.'
                : 'Record one or more sales — handy for a multi-lot exit.'}
            </p>
          </div>
          <button onClick={onClose} className="tap-target p-1.5 -m-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handle} className="space-y-4">
          {/* Exchange — only relevant when adding a brand-new position. Shown
              above the ticker field: it scopes the search below, and keeping
              it above means the suggestion dropdown never has to cover it. */}
          {tickerEditable && (
            <div>
              <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
                EXCHANGE
              </label>
              <ExchangeSelect value={exchange} onChange={setExchange} />
            </div>
          )}

          {/* Ticker */}
          <div>
            <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
              TICKER
            </label>
            {tickerEditable ? (
              <TickerAutocomplete
                value={ticker}
                onChange={setTicker}
                exchange={exchange}
                placeholder="e.g. AAPL"
              />
            ) : (
              <input
                type="text"
                value={ticker}
                readOnly
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors opacity-50 cursor-not-allowed select-none"
                placeholder="e.g. AAPL"
              />
            )}
          </div>

          {/* Purchases/sales — one row per lot */}
          <div>
            <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
              {mode === 'buy' ? 'PURCHASES' : 'SALES'}
              {mode === 'sell' && maxShares != null && (
                <span className="ml-2 normal-case font-normal tracking-normal text-zinc-600">
                  max {maxShares} total held
                </span>
              )}
            </label>
            <div className="grid grid-cols-[1fr_1fr_1.15fr_1.25rem] gap-2 px-0.5 mb-1">
              <span className="text-[0.5625rem] text-zinc-600 uppercase tracking-wider">Shares</span>
              <span className="text-[0.5625rem] text-zinc-600 uppercase tracking-wider">{mode === 'buy' ? 'Price paid' : 'Price sold'}</span>
              <span className="text-[0.5625rem] text-zinc-600 uppercase tracking-wider">Date</span>
              <span />
            </div>
            <div className="space-y-2">
              {lots.map(lot => (
                <div key={lot.key} className="grid grid-cols-[1fr_1fr_1.15fr_1.25rem] gap-2 items-center">
                  <input
                    type="number"
                    min={1}
                    value={lot.shares}
                    onChange={e => updateLot(lot.key, { shares: e.target.value })}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2.5 py-1.5 text-xs font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
                    placeholder="0"
                  />
                  <div className="relative">
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-zinc-500 text-xs font-mono pointer-events-none">
                      {CURRENCY_SYMBOL[currency]}
                    </span>
                    <input
                      type="number"
                      min={0.01}
                      step="0.01"
                      value={lot.price}
                      onChange={e => updateLot(lot.key, { price: e.target.value })}
                      className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-5 pr-2 py-1.5 text-xs font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
                      placeholder="0.00"
                    />
                  </div>
                  <input
                    type="date"
                    value={lot.date}
                    max={today}
                    onChange={e => updateLot(lot.key, { date: e.target.value })}
                    className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-2 py-1.5 text-xs font-mono text-zinc-100 focus:outline-none focus:border-indigo-500 transition-colors"
                  />
                  <button
                    type="button"
                    onClick={() => removeLot(lot.key)}
                    disabled={lots.length === 1}
                    title={`Remove this ${noun}`}
                    className="p-1 text-zinc-600 hover:text-red-400 disabled:opacity-30 disabled:cursor-not-allowed transition-colors"
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
            <button
              type="button"
              onClick={addLot}
              className="mt-2.5 flex items-center gap-1.5 text-[0.6875rem] text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              <Plus size={11} />
              Add another {noun}
            </button>
          </div>

          {/* Total preview */}
          {validLotCount > 0 && (
            <div className="bg-zinc-800/80 border border-zinc-700/50 rounded-lg px-3 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                Total {mode === 'buy' ? 'cost' : 'proceeds'}{validLotCount > 1 ? ` · ${validLotCount} ${noun}s` : ''}
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
            {lots.length > 1
              ? `Record ${lots.length} ${mode === 'buy' ? 'Purchases' : 'Sales'}`
              : mode === 'buy' ? 'Record Purchase' : 'Record Sale'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  )
}

// ── Dividend modal ────────────────────────────────────────────────────────────

interface DividendModalProps {
  mode: 'add' | 'edit'
  ticker: string
  currency: Currency
  entry?: DividendEntry
  onClose: () => void
  onSubmit: (date: string, amountPerShare: number, sharesHeld?: number) => Promise<void>
}

function DividendModal({ mode, ticker, currency, entry, onClose, onSubmit }: DividendModalProps) {
  const today = new Date().toLocaleDateString('en-CA')
  const [date, setDate] = useState(entry?.date ?? today)
  const [amountPerShare, setAmountPerShare] = useState(entry ? String(entry.amount_per_share) : '')
  const [sharesHeld, setSharesHeld] = useState(entry ? String(entry.shares_held) : '')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const amountNum = parseFloat(amountPerShare)
  const sharesNum = sharesHeld.trim() === '' ? undefined : parseInt(sharesHeld, 10)
  const total = !isNaN(amountNum) && amountNum > 0 && sharesNum != null && !isNaN(sharesNum) && sharesNum > 0
    ? amountNum * sharesNum
    : null

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    if (!date || isNaN(amountNum) || amountNum <= 0) {
      setError('Please fill in a valid date and amount per share.')
      return
    }
    if (sharesHeld.trim() !== '' && (sharesNum == null || isNaN(sharesNum) || sharesNum <= 0)) {
      setError('Shares held must be a positive whole number, or left blank.')
      return
    }
    setLoading(true)
    setError(null)
    try {
      await onSubmit(date, amountNum, sharesNum)
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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-sm shadow-2xl max-h-[85dvh] overflow-y-auto">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              {mode === 'add' ? 'Record Dividend' : 'Edit Dividend'}
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">{ticker} — cash dividend income.</p>
          </div>
          <button onClick={onClose} className="tap-target p-1.5 -m-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handle} className="space-y-4 mt-3">
          <div>
            <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
              EX-DIVIDEND DATE
            </label>
            <input
              type="date"
              value={date}
              max={today}
              onChange={e => setDate(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 focus:outline-none focus:border-indigo-500 transition-colors"
            />
          </div>

          <div>
            <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
              AMOUNT PER SHARE
            </label>
            <div className="relative">
              <span className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500 text-sm font-mono pointer-events-none">
                {CURRENCY_SYMBOL[currency]}
              </span>
              <input
                type="number"
                min={0.0001}
                step="0.0001"
                value={amountPerShare}
                onChange={e => setAmountPerShare(e.target.value)}
                className="w-full bg-zinc-800 border border-zinc-700 rounded-lg pl-7 pr-3 py-2 text-sm font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
                placeholder="0.00"
              />
            </div>
          </div>

          <div>
            <label className="block text-[0.625rem] font-semibold tracking-widest text-zinc-500 mb-1.5">
              SHARES HELD
              <span className="ml-2 normal-case font-normal tracking-normal text-zinc-600">
                optional — defaults to your position on this date
              </span>
            </label>
            <input
              type="number"
              min={1}
              value={sharesHeld}
              onChange={e => setSharesHeld(e.target.value)}
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
              placeholder="auto"
            />
          </div>

          {total != null && (
            <div className="bg-zinc-800/80 border border-zinc-700/50 rounded-lg px-3 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">Total</span>
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
            className="w-full py-2.5 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {loading && <RefreshCw size={13} className="animate-spin" />}
            {mode === 'add' ? 'Record Dividend' : 'Save Changes'}
          </button>
        </form>
      </motion.div>
    </motion.div>
  )
}

// ── Import modal ──────────────────────────────────────────────────────────────

// Parse failures (rows the file itself never let past validation) are shown
// alongside applied/skipped rows in the final summary, but they never go
// through the backend's apply step, so they may carry an empty `action` —
// unlike ImportRowResult, whose `action` reflects a row that was actually
// submitted for buy/sell.
type ImportSummaryRow = Omit<ImportRowResult, 'action'> & { action: string }
type ImportSummary = Omit<PortfolioImportResult, 'rows'> & { rows: ImportSummaryRow[] }

function ImportModal({ onClose, onImported }: { onClose: () => void; onImported: () => void }) {
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)   // preview fetch in flight
  const [applying, setApplying] = useState(false)  // apply call in flight
  const [error, setError] = useState<string | null>(null)
  // Portfolio-name problems stop the whole file rather than skipping rows —
  // a transaction that can't be filed where the user said must not be
  // quietly filed elsewhere. The user fixes the file and re-uploads.
  const [blocking, setBlocking] = useState<ImportBlockingError[]>([])

  const [previewRows, setPreviewRows] = useState<ImportPreviewRow[] | null>(null)
  // row -> include decision. Non-duplicate valid rows are seeded true;
  // duplicates are filled in as the user works through the review queue.
  const [decisions, setDecisions] = useState<Map<number, boolean>>(new Map())
  const [reviewIndex, setReviewIndex] = useState(0)

  const [result, setResult] = useState<ImportSummary | null>(null)

  // Only valid rows can be duplicates (see import_service._flag_duplicates),
  // so this is exactly the queue the review step walks through.
  const duplicateQueue = useMemo(
    () => (previewRows ?? []).filter(r => r.valid && r.duplicate),
    [previewRows],
  )
  const reviewingRow = reviewIndex < duplicateQueue.length ? duplicateQueue[reviewIndex] : null

  async function runApply(rows: ImportPreviewRow[], finalDecisions: Map<number, boolean>) {
    setApplying(true)
    setError(null)
    try {
      const applyRows: ImportApplyRow[] = rows
        .filter((r): r is ImportPreviewRow & { date: string } => r.valid && r.date != null && finalDecisions.has(r.row))
        .map(r => ({
          row: r.row, market: r.market, ticker: r.ticker, date: r.date,
          action: r.action as 'buy' | 'sell', shares: r.shares, price: r.price,
          // Name, not id — the server re-resolves it against the caller's own
          // portfolios, so this can't redirect rows anywhere they don't own.
          portfolio: r.portfolio,
          include: finalDecisions.get(r.row) ?? false,
        }))
      const applyResult = await applyPortfolioImport(applyRows)

      // Parse failures never go through /apply — fold them into the final
      // summary here so it reflects the whole file, not just what was sent.
      const parseFailures: ImportSummaryRow[] = rows
        .filter(r => !r.valid)
        .map(r => ({
          row: r.row, market: r.market, ticker: r.ticker, date: r.date ?? '',
          action: r.action, shares: r.shares, price: r.price,
          status: 'failed' as const, error: r.error,
        }))
      setResult({
        total_rows: applyResult.total_rows + parseFailures.length,
        imported_rows: applyResult.imported_rows,
        failed_rows: applyResult.failed_rows + parseFailures.length,
        skipped_rows: applyResult.skipped_rows,
        rows: [...applyResult.rows, ...parseFailures].sort((a, b) => a.row - b.row),
      })
      if (applyResult.imported_rows > 0) onImported()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Import failed')
    } finally {
      setApplying(false)
    }
  }

  async function handlePreview() {
    if (!file) return
    setLoading(true)
    setError(null)
    setBlocking([])
    try {
      const preview = await previewPortfolioImport(file)
      if (preview.blocking_errors.length > 0) {
        setBlocking(preview.blocking_errors)
        return
      }
      const initial = new Map<number, boolean>()
      for (const r of preview.rows) {
        if (r.valid && !r.duplicate) initial.set(r.row, true)  // auto-include non-duplicates
      }
      setPreviewRows(preview.rows)
      setDecisions(initial)
      setReviewIndex(0)

      const dupCount = preview.rows.filter(r => r.valid && r.duplicate).length
      if (dupCount === 0) await runApply(preview.rows, initial)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to read file')
    } finally {
      setLoading(false)
    }
  }

  function decideOne(include: boolean) {
    if (!reviewingRow || !previewRows) return
    const next = new Map(decisions)
    next.set(reviewingRow.row, include)
    setDecisions(next)
    const nextIndex = reviewIndex + 1
    setReviewIndex(nextIndex)
    if (nextIndex >= duplicateQueue.length) runApply(previewRows, next)
  }

  function decideAllRemaining(include: boolean) {
    if (!previewRows) return
    const next = new Map(decisions)
    for (let i = reviewIndex; i < duplicateQueue.length; i++) next.set(duplicateQueue[i].row, include)
    setDecisions(next)
    setReviewIndex(duplicateQueue.length)
    runApply(previewRows, next)
  }

  const problemRows = result?.rows.filter(r => r.status !== 'imported') ?? []

  return (
    <motion.div
      variants={overlayFade}
      initial="hidden"
      animate="show"
      exit="exit"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-lg shadow-2xl max-h-[85dvh] overflow-y-auto">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Import Portfolio</h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              Upload a .csv or .xlsx file to bulk-add transactions.
            </p>
          </div>
          <button onClick={onClose} className="tap-target p-1.5 -m-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        {result ? (
          <div className="space-y-3 mt-4">
            <div className="flex items-center gap-2">
              <div className="flex-1 rounded-lg bg-emerald-500/10 border border-emerald-500/20 px-2 py-2.5 text-center">
                <div className="text-lg font-bold font-mono text-emerald-400">{result.imported_rows}</div>
                <div className="text-[0.5625rem] text-zinc-500 tracking-widest">IMPORTED</div>
              </div>
              <div className="flex-1 rounded-lg bg-zinc-800/60 border border-zinc-700/50 px-2 py-2.5 text-center">
                <div className="text-lg font-bold font-mono text-zinc-400">{result.skipped_rows}</div>
                <div className="text-[0.5625rem] text-zinc-500 tracking-widest">SKIPPED</div>
              </div>
              <div className="flex-1 rounded-lg bg-red-500/10 border border-red-500/20 px-2 py-2.5 text-center">
                <div className="text-lg font-bold font-mono text-red-400">{result.failed_rows}</div>
                <div className="text-[0.5625rem] text-zinc-500 tracking-widest">FAILED</div>
              </div>
            </div>

            {problemRows.length > 0 && (
              <div className="border border-zinc-800 rounded-lg overflow-hidden">
                <div className="max-h-56 overflow-y-auto divide-y divide-zinc-800/60">
                  {problemRows.map(r => (
                    <div key={r.row} className="px-3 py-2 text-xs">
                      <div className="flex items-center gap-2">
                        <span className="text-zinc-500 font-mono whitespace-nowrap">Row {r.row}</span>
                        <span className="text-zinc-300 font-mono truncate">{r.ticker || '—'}</span>
                        <span className={clsx(
                          'ml-auto px-1.5 py-0.5 rounded text-[0.625rem] font-semibold shrink-0',
                          r.status === 'skipped' ? 'bg-zinc-700/40 text-zinc-400' : 'bg-red-500/10 text-red-400',
                        )}>
                          {r.status.toUpperCase()}
                        </span>
                      </div>
                      {r.error && <p className="text-red-400 mt-0.5">{r.error}</p>}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              onClick={onClose}
              className="w-full py-2.5 rounded-lg text-sm font-semibold transition-colors bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
            >
              Done
            </button>
          </div>
        ) : applying ? (
          <div className="flex flex-col items-center justify-center gap-3 py-16">
            <RefreshCw size={20} className="text-indigo-400 animate-spin" />
            <p className="text-xs text-zinc-500">Importing…</p>
          </div>
        ) : blocking.length > 0 ? (
          <div className="space-y-3 mt-4">
            <div className="flex items-start gap-3 bg-amber-500/8 border border-amber-500/25 rounded-xl px-4 py-3">
              <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
              <div className="space-y-1">
                <p className="text-xs font-semibold text-amber-400">
                  Nothing was imported
                </p>
                <p className="text-xs text-zinc-400 leading-relaxed">
                  {blocking.length} row{blocking.length !== 1 ? 's' : ''} name a portfolio
                  that couldn't be matched. Fix the file and upload it again — importing
                  the rest would file those transactions in the wrong place.
                </p>
              </div>
            </div>

            <div className="border border-zinc-800 rounded-lg overflow-hidden">
              <div className="max-h-56 overflow-y-auto divide-y divide-zinc-800/60">
                {blocking.map(e => (
                  <div key={e.row} className="px-3 py-2 text-xs">
                    <span className="text-zinc-500 font-mono whitespace-nowrap">
                      {e.row > 0 ? `Row ${e.row}` : 'File'}
                    </span>
                    <p className="text-amber-300/90 mt-0.5 leading-relaxed">{e.message}</p>
                  </div>
                ))}
              </div>
            </div>

            <button
              onClick={() => { setBlocking([]); setFile(null) }}
              className="w-full py-2.5 rounded-lg text-sm font-semibold transition-colors bg-zinc-800 hover:bg-zinc-700 text-zinc-200"
            >
              Choose another file
            </button>
          </div>
        ) : reviewingRow ? (
          <div className="space-y-4 mt-4">
            <div className="flex items-center justify-between">
              <p className="text-xs text-zinc-500">
                Possible duplicate {reviewIndex + 1} of {duplicateQueue.length}
              </p>
              <span className="text-[0.625rem] text-zinc-600 font-mono">Row {reviewingRow.row}</span>
            </div>

            <div className="bg-amber-500/8 border border-amber-500/25 rounded-xl px-4 py-3 space-y-2.5">
              <div className="flex items-center gap-2">
                <AlertTriangle size={14} className="text-amber-400 shrink-0" />
                <span className="text-xs font-semibold text-amber-400">Possible duplicate transaction</span>
              </div>
              <p className="text-xs text-zinc-400 leading-relaxed">{reviewingRow.duplicate_reason}</p>
              <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs font-mono pt-2 border-t border-amber-500/10">
                <span className="text-zinc-500">Ticker</span>
                <span className="text-zinc-200 text-right">{reviewingRow.ticker}</span>
                <span className="text-zinc-500">Date</span>
                <span className="text-zinc-200 text-right">{reviewingRow.date}</span>
                <span className="text-zinc-500">Action</span>
                <span className={clsx('text-right font-semibold', reviewingRow.action === 'sell' ? 'text-red-400' : 'text-emerald-400')}>
                  {reviewingRow.action.toUpperCase()}
                </span>
                <span className="text-zinc-500">Shares</span>
                <span className="text-zinc-200 text-right">{reviewingRow.shares}</span>
                <span className="text-zinc-500">Price</span>
                <span className="text-zinc-200 text-right">{reviewingRow.price}</span>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <button
                onClick={() => decideOne(false)}
                className="py-2 rounded-lg text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 transition-colors"
              >
                Skip this
              </button>
              <button
                onClick={() => decideOne(true)}
                className="py-2 rounded-lg text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors"
              >
                Add this
              </button>
              <button
                onClick={() => decideAllRemaining(false)}
                className="py-2 rounded-lg text-xs font-medium text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60 border border-zinc-800 transition-colors"
              >
                Skip all duplicates
              </button>
              <button
                onClick={() => decideAllRemaining(true)}
                className="py-2 rounded-lg text-xs font-medium text-indigo-400 hover:text-indigo-300 hover:bg-indigo-500/10 border border-indigo-500/20 transition-colors"
              >
                Add all duplicates
              </button>
            </div>
          </div>
        ) : (
          <div className="space-y-4 mt-4">
            <div className="bg-zinc-800/60 border border-zinc-700/50 rounded-lg px-3 py-2.5 text-xs leading-relaxed">
              <p className="font-semibold text-zinc-300 mb-1">Expected columns</p>
              <p className="font-mono text-[0.6875rem] text-zinc-500">market | stock | date | number | buy/sell | price</p>
              <ul className="mt-2 space-y-0.5 text-zinc-500">
                <li><span className="text-zinc-400 font-mono">market</span> — "US" or "IND" (India defaults to NSE)</li>
                <li><span className="text-zinc-400 font-mono">stock</span> — ticker symbol</li>
                <li><span className="text-zinc-400 font-mono">date</span> — transaction date</li>
                <li><span className="text-zinc-400 font-mono">number</span> — share count</li>
                <li><span className="text-zinc-400 font-mono">buy/sell</span> — transaction type</li>
                <li><span className="text-zinc-400 font-mono">price</span> — price per share</li>
                <li>
                  <span className="text-zinc-400 font-mono">portfolio</span> — optional; the
                  portfolio's name, which must already exist in that market. Leave the
                  column out to send everything to your default portfolios.
                </li>
              </ul>
              <p className="mt-2 text-zinc-600">
                A header row is optional — without one, columns must be in exactly the first
                six positions above, and the portfolio column can't be used.
              </p>
              <p className="mt-1.5 text-zinc-600">
                Uploading the same rows again is safe — exact duplicates (same ticker, date, action,
                shares and price) are flagged so you can confirm before they're added again.
              </p>
            </div>

            <label className={clsx(
              'flex flex-col items-center justify-center gap-2 border-2 border-dashed rounded-xl px-4 py-8 cursor-pointer transition-colors',
              file ? 'border-indigo-500/50 bg-indigo-500/5' : 'border-zinc-700 hover:border-zinc-600 hover:bg-zinc-800/40',
            )}>
              <input
                type="file"
                accept=".csv,.xlsx"
                className="hidden"
                onChange={e => setFile(e.target.files?.[0] ?? null)}
              />
              <FileUp size={20} className={file ? 'text-indigo-400' : 'text-zinc-500'} />
              <span className="text-xs text-zinc-400 text-center">
                {file ? file.name : 'Click to choose a .csv or .xlsx file'}
              </span>
            </label>

            {error && (
              <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <button
              onClick={handlePreview}
              disabled={!file || loading}
              className="w-full py-2.5 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              {loading && <RefreshCw size={13} className="animate-spin" />}
              {loading ? 'Reading file…' : 'Import'}
            </button>
          </div>
        )}
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
          'inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[0.625rem] font-semibold',
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
          className="p-2 sm:p-0.5 text-zinc-700 hover:text-red-400 transition-colors"
        >
          <Trash2 size={11} />
        </button>
      </td>
    </tr>
  )
}

function DividendRow({
  entry, money, onEdit, onDeleteRequest,
}: {
  entry: DividendEntry
  money: MoneyFmt
  onEdit: () => void
  onDeleteRequest: () => void
}) {
  return (
    <tr className="border-b border-zinc-800/40 hover:bg-zinc-800/20 transition-colors">
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-500 whitespace-nowrap">{entry.date}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">{money(entry.amount_per_share)}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">{entry.shares_held}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-emerald-400">{money(entry.total_amount)}</td>
      <td className="px-5 py-2.5">
        <span className={clsx(
          'inline-flex items-center px-1.5 py-0.5 rounded text-[0.625rem] font-semibold',
          entry.source === 'auto' ? 'bg-indigo-500/10 text-indigo-400' : 'bg-zinc-700/30 text-zinc-400',
        )}>
          {entry.source === 'auto' ? 'AUTO' : 'MANUAL'}
        </span>
      </td>
      <td className="px-4 py-2.5">
        <div className="flex items-center gap-2 sm:gap-1">
          <button
            onClick={onEdit}
            title="Edit dividend"
            className="p-2 sm:p-0.5 text-zinc-700 hover:text-indigo-400 transition-colors"
          >
            <Pencil size={11} />
          </button>
          <button
            onClick={onDeleteRequest}
            title="Delete dividend"
            className="p-2 sm:p-0.5 text-zinc-700 hover:text-red-400 transition-colors"
          >
            <Trash2 size={11} />
          </button>
        </div>
      </td>
    </tr>
  )
}

function DividendsSection({
  holding, money, syncing, onSync, onAdd, onEdit, onDeleteRequest,
}: {
  holding: StockHolding
  money: MoneyFmt
  syncing: boolean
  onSync: () => void
  onAdd: () => void
  onEdit: (entry: DividendEntry) => void
  onDeleteRequest: (entry: DividendEntry) => void
}) {
  return (
    <div className="border-t border-zinc-800/40">
      <div className="flex flex-wrap items-center gap-2 px-4 sm:px-5 py-3">
        <span className="flex items-center gap-1.5 text-[0.625rem] font-semibold tracking-widest text-zinc-500">
          <Coins size={11} className="text-zinc-600" /> DIVIDENDS <InfoTip k="dividends" />
        </span>
        <span className="text-xs font-mono text-emerald-400">{money(holding.total_dividends)}</span>
        <button
          onClick={onSync}
          disabled={syncing}
          title="Fetch new dividend payments from Yahoo Finance"
          className="ml-auto flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-zinc-400 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700 rounded-lg transition-colors disabled:opacity-40"
        >
          <RefreshCw size={11} className={syncing ? 'animate-spin' : ''} />
          Sync
        </button>
        <button
          onClick={onAdd}
          className="flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium text-zinc-400 bg-zinc-800/60 hover:bg-zinc-800 border border-zinc-700 rounded-lg transition-colors"
        >
          <Plus size={11} />
          Add
        </button>
      </div>

      {holding.dividends.length === 0 ? (
        <p className="px-5 pb-4 text-xs text-zinc-600 italic">
          No dividends recorded. Try "Sync" to fetch payment history, or add one by hand.
        </p>
      ) : (
        <div className="overflow-x-auto pb-1">
          <table className="w-full">
            <thead>
              <tr className="border-b border-zinc-800/40">
                {['Ex-Date', 'Per Share', 'Shares Held', 'Total', 'Source', ''].map(col => (
                  <th
                    key={col}
                    className="px-5 py-2 text-left text-[0.625rem] tracking-widest text-zinc-600 font-semibold whitespace-nowrap"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {[...holding.dividends].reverse().map(entry => (
                <DividendRow
                  key={entry.id}
                  entry={entry}
                  money={money}
                  onEdit={() => onEdit(entry)}
                  onDeleteRequest={() => onDeleteRequest(entry)}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function HoldingRow({
  holding, money, expanded, onToggle, onBuy, onSell, onDelete, onViewTicker, onDeleteTxn,
  syncingDividends, onSyncDividends, onAddDividend, onEditDividend, onDeleteDividendRequest,
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
  syncingDividends: boolean
  onSyncDividends: () => void
  onAddDividend: () => void
  onEditDividend: (entry: DividendEntry) => void
  onDeleteDividendRequest: (entry: DividendEntry) => void
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
      {/* Main summary row — click anywhere to expand.
          Seven numeric columns plus a name need ~900px to stay legible, so
          below `lg` the row becomes a stacked card: an identity line, then a
          labelled grid of the same figures. The two wrappers are `contents`
          at `lg`, which dissolves them so their children become the real grid
          items; `order` then restores the table's left-to-right sequence. */}
      <div
        onClick={onToggle}
        className={clsx(
          'flex flex-col gap-3 px-4 py-3.5 hover:bg-zinc-800/40 cursor-pointer transition-colors group',
          'lg:grid lg:grid-cols-[minmax(8.75rem,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_2rem_2rem] lg:gap-3 lg:px-5 lg:items-center',
        )}
      >
        {/* Identity line: badge + name, with the row actions kept beside it */}
        <div className="flex items-center gap-3 lg:contents">
          {/* Position: ticker badge + company name (ticker) */}
          <div className="flex items-center gap-2.5 min-w-0 flex-1 lg:flex-none lg:order-1">
            <span className={clsx(
              'px-2 py-1 rounded-md text-[0.6875rem] font-bold font-mono shrink-0 whitespace-nowrap',
              !hasPrice ? 'bg-zinc-700/30 text-zinc-400' : pl! >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400',
            )}>
              {displayTicker(holding.ticker)}
            </span>
            <div
              className="min-w-0"
              title={holding.company_name ? `${holding.company_name} (${displayTicker(holding.ticker)})` : displayTicker(holding.ticker)}
            >
              <div className="text-sm font-medium text-zinc-100 truncate">
                {holding.company_name
                  ? <>{holding.company_name} <span className="text-zinc-500 font-normal text-xs">({displayTicker(holding.ticker)})</span></>
                  : displayTicker(holding.ticker)}
              </div>
              {holding.sold_shares > 0 && (
                <div className="text-[0.625rem] text-zinc-600 leading-none mt-0.5">
                  {holding.sold_shares} sold
                </div>
              )}
            </div>
          </div>

          {/* Tracker link */}
          <div className="flex items-center justify-center shrink-0 lg:order-8">
            <button
              onClick={e => { e.stopPropagation(); onViewTicker() }}
              title={`View ${displayTicker(holding.ticker)} on the tracker`}
              aria-label={`View ${displayTicker(holding.ticker)} on the tracker`}
              className="tap-target p-2 lg:p-1 text-zinc-600 hover:text-indigo-400 hover:bg-indigo-500/10 rounded transition-colors"
            >
              <BarChart2 size={13} />
            </button>
          </div>

          {/* Chevron */}
          <div className="flex items-center justify-center shrink-0 lg:order-9">
            {expanded
              ? <ChevronUp  size={13} className="text-zinc-500" />
              : <ChevronDown size={13} className="text-zinc-600 group-hover:text-zinc-400 transition-colors" />}
          </div>
        </div>

        {/* The figures. Labelled only below `lg`, where the table's own column
            header row isn't rendered. */}
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-x-4 gap-y-2.5 pl-1 lg:contents">
          {/* Shares */}
          <div className="min-w-0 lg:order-2">
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">SHARES</span>
            <span className="block text-sm font-mono text-zinc-300 lg:text-right">{holding.shares}</span>
          </div>

          {/* Avg cost */}
          <div className="min-w-0 lg:order-3">
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">AVG COST</span>
            <span className="block text-sm font-mono text-zinc-400 lg:text-right">{money(holding.average_cost)}</span>
          </div>

          {/* Current */}
          <div
            className="min-w-0 lg:order-4"
            title={hasPrice ? undefined : 'Price unavailable — last fetch failed'}
          >
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">CURRENT</span>
            <span className="block text-sm font-mono text-zinc-300 lg:text-right">
              {hasPrice ? money(holding.current_price) : <span className="text-zinc-600 italic">unavailable</span>}
            </span>
          </div>

          {/* Market value */}
          <div className="min-w-0 lg:order-5">
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">VALUE</span>
            <span className="block text-sm font-mono text-zinc-300 lg:text-right">{money(holding.stock_value)}</span>
          </div>

          {/* Unrealized P&L */}
          <div className="min-w-0 lg:order-6 lg:text-right">
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">UNREALIZED P&amp;L</span>
            {hasPrice ? (
              <>
                <div className={clsx('text-sm font-mono font-medium leading-none', gainText(pl!))}>
                  {money(pl, { sign: true })}
                </div>
                <div className={clsx('text-[0.625rem] font-mono mt-0.5', gainText(pl!))}>
                  {fmtPct(plPct!)}
                </div>
              </>
            ) : (
              <div className="text-sm font-mono text-zinc-600">—</div>
            )}
          </div>

          {/* Realized gains */}
          <div className="min-w-0 lg:order-7">
            <span className="lg:hidden block text-[0.5625rem] font-semibold tracking-widest text-zinc-600 mb-0.5">REALIZED</span>
            <span className={clsx(
              'block text-sm font-mono lg:text-right',
              holding.total_earned > 0 ? 'text-emerald-400' : 'text-zinc-500',
            )}>
              {money(holding.total_earned)}
            </span>
          </div>
        </div>
      </div>

      {/* Expanded panel */}
      <AnimatePresence>
      {expanded && (
        <motion.div variants={collapse} initial="hidden" animate="show" exit="exit" style={{ overflow: 'hidden' }} className="border-t border-zinc-800/60 bg-zinc-950/60">
          {/* Actions bar */}
          <div className="flex flex-wrap items-center gap-2 px-4 sm:px-5 py-3 border-b border-zinc-800/40">
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
                        className="px-5 py-2 text-left text-[0.625rem] tracking-widest text-zinc-600 font-semibold whitespace-nowrap"
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

          {/* Dividends */}
          <DividendsSection
            holding={holding}
            money={money}
            syncing={syncingDividends}
            onSync={onSyncDividends}
            onAdd={onAddDividend}
            onEdit={onEditDividend}
            onDeleteRequest={onDeleteDividendRequest}
          />
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
  const [importOpen, setImportOpen]   = useState(false)
  const [deleteTarget, setDeleteTarget] = useState<string | null>(null)
  const [deleteLoading, setDeleteLoading] = useState(false)
  const [txnDeleteTarget, setTxnDeleteTarget] = useState<{ ticker: string; txnId: number; isLast: boolean } | null>(null)
  const [txnDeleteLoading, setTxnDeleteLoading] = useState(false)
  const [txnDeleteError, setTxnDeleteError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated]       = useState<Date | null>(null)
  const [downloading, setDownloading]       = useState(false)
  const [dividendModal, setDividendModal]   = useState<{ mode: 'add' | 'edit'; ticker: string; entry?: DividendEntry } | null>(null)
  const [syncingTicker, setSyncingTicker]   = useState<string | null>(null)
  const [dividendDeleteTarget, setDividendDeleteTarget] = useState<{ ticker: string; id: number } | null>(null)
  const [dividendDeleteLoading, setDividendDeleteLoading] = useState(false)
  const [dividendDeleteError, setDividendDeleteError] = useState<string | null>(null)

  // Which portfolio tab is open, remembered per market so switching US <-> India
  // and back returns you where you were. Persisted ids are validated against the
  // fetched list below — a portfolio can be deleted, or belong to another account.
  const [activeUs, setActiveUs] = usePersistedState<number | null>('active-portfolio-US', null)
  const [activeIn, setActiveIn] = usePersistedState<number | null>('active-portfolio-IN', null)
  const [nameModal, setNameModal] = useState<{ mode: 'create' | 'rename'; portfolio?: PortfolioStats } | null>(null)
  const [portfolioDeleteTarget, setPortfolioDeleteTarget] = useState<PortfolioStats | null>(null)
  const isGuest = isGuestModeActive()

  const load = useCallback(async (opts?: { silent?: boolean }) => {
    const silent = opts?.silent ?? false
    // The background poll (PORTFOLIO_REFRESH_MS) fetches quietly — no skeleton,
    // no error banner — so a scheduled refresh never blanks a page the user is
    // actively looking at. Values update in place once the new data lands (see
    // StatCard's flash-on-change). Only the initial load and a tab switch,
    // which have nothing on screen yet, show the loading state.
    if (!silent) setLoading(true)
    if (!silent) setError(null)
    try {
      const result = await fetchPortfolio(tab)
      setPortfolio(result)
      onData?.(result)
      setLastUpdated(new Date())
    } catch (e) {
      if (!silent) setError(e instanceof Error ? e.message : 'Failed to load portfolio')
    } finally {
      if (!silent) setLoading(false)
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
    const id = setInterval(() => load({ silent: true }), PORTFOLIO_REFRESH_MS)
    return () => clearInterval(id)
  }, [load])

  async function submitBuyBulk(ticker: string, lots: BuyLot[], exchange?: Exchange) {
    await logBuyBulk(ticker, lots, exchange, activeId)
    await load()
    onTickerAdded?.()
  }

  async function submitSellBulk(ticker: string, lots: SellLot[]) {
    await logSellBulk(ticker, lots, activeId)
    await load()
  }

  function openTxnDelete(ticker: string, txnId: number, isLast: boolean) {
    setTxnDeleteTarget({ ticker, txnId, isLast })
    setTxnDeleteError(null)
  }

  async function handleSyncDividends(ticker: string) {
    setSyncingTicker(ticker)
    try {
      await syncDividends(ticker, activeId)
      await load()
    } catch {
      // Best-effort — the "Sync" button just stays available to retry.
    } finally {
      setSyncingTicker(null)
    }
  }

  async function submitDividend(date: string, amountPerShare: number, sharesHeld?: number) {
    if (!dividendModal) return
    if (dividendModal.mode === 'edit' && dividendModal.entry) {
      await updateDividend(dividendModal.ticker, dividendModal.entry.id, { date, amountPerShare, sharesHeld }, activeId)
    } else {
      await addDividend(dividendModal.ticker, date, amountPerShare, sharesHeld, activeId)
    }
    await load()
  }

  function openDividendDelete(ticker: string, id: number) {
    setDividendDeleteTarget({ ticker, id })
    setDividendDeleteError(null)
  }

  async function handleConfirmDeleteDividend() {
    if (!dividendDeleteTarget) return
    setDividendDeleteLoading(true)
    setDividendDeleteError(null)
    try {
      await deleteDividend(dividendDeleteTarget.ticker, dividendDeleteTarget.id, activeId)
      setDividendDeleteTarget(null)
      await load()
    } catch (e) {
      setDividendDeleteError(e instanceof Error ? e.message : 'Failed to delete dividend.')
    } finally {
      setDividendDeleteLoading(false)
    }
  }

  async function handleConfirmDeleteTxn() {
    if (!txnDeleteTarget) return
    setTxnDeleteLoading(true)
    setTxnDeleteError(null)
    try {
      const removedTicker = txnDeleteTarget.ticker
      const wasLast = txnDeleteTarget.isLast
      await deleteTransaction(removedTicker, txnDeleteTarget.txnId, activeId)
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
      await deletePortfolioHolding(removedTicker, activeId)
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

  const portfolios = portfolio?.portfolios ?? []
  const storedActive = tab === 'IN' ? activeIn : activeUs
  const setStoredActive = tab === 'IN' ? setActiveIn : setActiveUs
  // Fall back to the first tab whenever the remembered id isn't in this
  // market's list — covers a deleted portfolio, a different account, and the
  // very first visit.
  const activePortfolio = portfolios.find(p => p.id === storedActive) ?? portfolios[0] ?? null
  const activeId = activePortfolio?.id ?? null

  // One fetch covers the whole market; the tabs are a client-side filter over
  // it, so switching tabs is instant and never refetches.
  const allHoldings = portfolio?.holdings ?? []
  const scoped = activeId == null ? allHoldings : allHoldings.filter(h => h.portfolio_id === activeId)

  // Always alphabetical by ticker, regardless of the order the API returns —
  // makes a given position easy to find without depending on backend order.
  const holdings  = [...scoped].sort((a, b) => a.ticker.localeCompare(b.ticker))
  const netPl     = activePortfolio?.net_profit_loss ?? 0
  const totalRet  = activePortfolio?.total_return ?? 0
  const showCombined = portfolios.length > 1

  async function handleCreatePortfolio(name: string) {
    const created = await createPortfolio(tab, name)
    setStoredActive(created.id)
    await load()
  }

  async function handleRenamePortfolio(name: string) {
    if (!nameModal?.portfolio) return
    await renamePortfolio(nameModal.portfolio.id, name)
    await load()
  }

  async function handleDeletePortfolio() {
    if (!portfolioDeleteTarget) return
    await deletePortfolio(portfolioDeleteTarget.id)
    // Let the fallback above pick the next tab rather than guessing here.
    // The watchlist is per-user and untouched by this, so the dashboard's
    // ticker list needs no refresh.
    setStoredActive(null)
    setExpanded(null)
    await load()
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 sm:p-6 min-w-0">
      <div className="max-w-6xl mx-auto flex flex-col gap-5 sm:gap-6">

        {/* ── Page header ──────────────────────────────────────────────── */}
        <div className="flex flex-col xl:flex-row xl:items-center xl:justify-between gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-5">
            <div>
              <h1 className="font-display text-lg font-bold tracking-tight text-zinc-100">My Portfolios</h1>
              <p className="text-xs text-zinc-500 mt-0.5">
                Track positions, log transactions, monitor performance
              </p>
            </div>
            {/* Market switch: separate portfolios for US and Indian stocks.
                Full width on phones so both halves stay comfortably tappable. */}
            <div className="flex rounded-lg overflow-hidden border border-zinc-800 shrink-0">
              {([
                { value: 'US' as Market, label: 'US · NYSE/NASDAQ', short: 'US' },
                { value: 'IN' as Market, label: 'India · NSE/BSE', short: 'India' },
              ]).map(({ value, label, short }) => (
                <button
                  key={value}
                  onClick={() => switchTab(value)}
                  className={clsx(
                    'relative flex-1 sm:flex-none px-3.5 py-2.5 sm:py-2 text-xs font-medium transition-colors whitespace-nowrap',
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
                  <span className="hidden sm:inline">{label}</span>
                  <span className="sm:hidden">{short}</span>
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:gap-3">
            <div className="flex flex-col items-center gap-0.5">
              <button
                onClick={() => load()}
                disabled={loading}
                title="Refresh portfolio"
                aria-label="Refresh portfolio"
                className="tap-target p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 rounded-lg transition-colors disabled:opacity-40"
              >
                <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
              </button>
              {lastUpdated && (
                <span className="text-[0.625rem] text-zinc-600 whitespace-nowrap">
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
              onClick={() => setImportOpen(true)}
              title="Bulk-import transactions from a .csv or .xlsx file"
              className="flex items-center gap-1.5 px-3 py-2 text-sm font-medium text-indigo-400 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 rounded-lg transition-colors"
            >
              <Upload size={14} />
              Import
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
              onClick={() => load()}
              className="text-xs text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Try again
            </button>
          </div>
        ) : portfolio && (
          <>
            {/* ── Combined totals across the market's portfolios ──────── */}
            {/* Only meaningful with more than one — otherwise it would just
                repeat the single portfolio's own stats row below it. */}
            {showCombined && (
              <CombinedStatsBar portfolio={portfolio} money={money} count={portfolios.length} />
            )}

            {/* ── Portfolio tabs ─────────────────────────────────────── */}
            <PortfolioTabs
              portfolios={portfolios}
              activeId={activeId}
              onSelect={setStoredActive}
              onCreate={() => setNameModal({ mode: 'create' })}
              onRename={p => setNameModal({ mode: 'rename', portfolio: p })}
              onDelete={setPortfolioDeleteTarget}
              disabledReason={isGuest ? 'Sign in to create more portfolios' : undefined}
            />

            {/* ── Summary stats for the open portfolio ───────────────── */}
            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
              <StatCard
                label="PORTFOLIO VALUE"
                tip="portfolio_value"
                value={money(activePortfolio?.portfolio_value ?? 0)}
                accent
              />
              <StatCard
                label="COST BASIS"
                tip="total_invested"
                value={money(activePortfolio?.total_invested ?? 0)}
              />
              <StatCard
                label="UNREALIZED RETURN"
                tip="total_return"
                value={money(totalRet, { sign: true })}
                valueColor={gainText(totalRet)}
                sub={fmtPct(activePortfolio?.return_percentage ?? 0)}
                subColor={gainText(totalRet)}
              />
              <StatCard
                label="REALIZED GAINS"
                tip="realized_gains"
                value={money(activePortfolio?.realized_gains ?? 0)}
                valueColor={(activePortfolio?.realized_gains ?? 0) > 0 ? gainText(1) : undefined}
              />
              <StatCard
                label="DIVIDENDS"
                tip="dividends"
                value={money(activePortfolio?.total_dividends ?? 0)}
                valueColor={(activePortfolio?.total_dividends ?? 0) > 0 ? gainText(1) : undefined}
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
                {/* Column headers — hidden once the rows stop being a table;
                    each stacked card carries its own labels instead. */}
                <div className="hidden lg:grid grid-cols-[minmax(8.75rem,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_2rem_2rem] gap-3 px-5 py-2.5 border-b border-zinc-800 text-[0.625rem] font-semibold tracking-widest text-zinc-500">
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
                        syncingDividends={syncingTicker === h.ticker}
                        onSyncDividends={() => handleSyncDividends(h.ticker)}
                        onAddDividend={() => setDividendModal({ mode: 'add', ticker: h.ticker })}
                        onEditDividend={entry => setDividendModal({ mode: 'edit', ticker: h.ticker, entry })}
                        onDeleteDividendRequest={entry => openDividendDelete(h.ticker, entry.id)}
                      />
                    ))}
                  </AnimatePresence>
                </div>

                {/* Table footer */}
                <div className="flex flex-wrap items-center justify-between gap-2 px-4 sm:px-5 py-2.5 border-t border-zinc-800 bg-zinc-950/40">
                  <span className="text-[0.625rem] text-zinc-600">
                    {holdings.length} position{holdings.length !== 1 ? 's' : ''} · {activePortfolio?.total_shares ?? 0} shares held
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
        {nameModal && (
          <PortfolioNameModal
            key="portfolio-name"
            mode={nameModal.mode}
            market={tab}
            initialName={nameModal.portfolio?.name ?? ''}
            onClose={() => setNameModal(null)}
            onSubmit={nameModal.mode === 'create' ? handleCreatePortfolio : handleRenamePortfolio}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {portfolioDeleteTarget && (
          <DeletePortfolioModal
            key="portfolio-delete"
            portfolio={portfolioDeleteTarget}
            holdings={allHoldings.filter(h => h.portfolio_id === portfolioDeleteTarget.id)}
            money={money}
            onClose={() => setPortfolioDeleteTarget(null)}
            onConfirm={handleDeletePortfolio}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {addOpen && (
          <TxModal
            key="add"
            mode="buy"
            ticker=""
            tickerEditable
            initialExchange={tab === 'IN' ? 'IN' : 'US'}
            onClose={() => setAddOpen(false)}
            onSubmitBuy={submitBuyBulk}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {importOpen && (
          <ImportModal
            key="import"
            onClose={() => setImportOpen(false)}
            onImported={load}
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
            onSubmitBuy={submitBuyBulk}
            onSubmitSell={submitSellBulk}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {dividendModal && (
          <DividendModal
            key="dividend"
            mode={dividendModal.mode}
            ticker={dividendModal.ticker}
            currency={holdings.find(h => h.ticker === dividendModal.ticker)?.currency ?? nativeCcy}
            entry={dividendModal.entry}
            onClose={() => setDividendModal(null)}
            onSubmit={submitDividend}
          />
        )}
      </AnimatePresence>

      <AnimatePresence>
        {dividendDeleteTarget && (
          <motion.div
            key="dividend-delete"
            variants={overlayFade}
            initial="hidden"
            animate="show"
            exit="exit"
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={e => { if (e.target === e.currentTarget && !dividendDeleteLoading) setDividendDeleteTarget(null) }}
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-xs shadow-2xl">
              <h2 className="text-sm font-semibold text-zinc-100 mb-1">Delete dividend entry?</h2>
              <p className="text-xs text-zinc-400 leading-relaxed mb-4">
                This dividend payment will be permanently removed from {dividendDeleteTarget.ticker}'s history.
              </p>

              {dividendDeleteError && (
                <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 mb-4">
                  <X size={13} className="text-red-400 shrink-0 mt-0.5" />
                  <p className="text-xs text-red-400 leading-relaxed">{dividendDeleteError}</p>
                </div>
              )}

              <div className="flex justify-end gap-2">
                <button
                  onClick={() => { setDividendDeleteTarget(null); setDividendDeleteError(null) }}
                  disabled={dividendDeleteLoading}
                  className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
                >
                  Cancel
                </button>
                <button
                  onClick={handleConfirmDeleteDividend}
                  disabled={dividendDeleteLoading}
                  className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors disabled:opacity-40"
                >
                  {dividendDeleteLoading ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={11} />}
                  Delete
                </button>
              </div>
            </motion.div>
          </motion.div>
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={e => { if (e.target === e.currentTarget && !txnDeleteLoading) setTxnDeleteTarget(null) }}
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-sm shadow-2xl">
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
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
            onClick={e => { if (e.target === e.currentTarget) setDeleteTarget(null) }}
          >
            <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-xs shadow-2xl">
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
