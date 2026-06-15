import { useState, useEffect, useCallback } from 'react'
import clsx from 'clsx'
import {
  Plus, TrendingUp, TrendingDown, ChevronDown, ChevronUp,
  Trash2, RefreshCw, X, Briefcase, ArrowDownLeft, ArrowUpRight,
  BarChart2, AlertTriangle,
} from 'lucide-react'
import type { PortfolioResponse, StockHolding, StockPurchaseHistory } from '../types'
import { fetchPortfolio, logBuy, logSell, deletePortfolioHolding, deleteTransaction } from '../api'

// ── Formatting ────────────────────────────────────────────────────────────────

const fmt = (n: number) =>
  n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

const fmtCcy = (n: number) => `$${fmt(Math.abs(n))}`

const fmtK = (n: number) => {
  const abs = Math.abs(n)
  const prefix = n < 0 ? '-' : ''
  if (abs >= 1_000_000) return `${prefix}$${(abs / 1_000_000).toFixed(2)}M`
  if (abs >= 10_000)    return `${prefix}$${(abs / 1_000).toFixed(1)}k`
  return `${prefix}$${fmt(abs)}`
}

const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
const sign   = (n: number) => n >= 0 ? '+' : '−'

const gainText   = (n: number) => n >= 0 ? 'text-emerald-400' : 'text-red-400'
const gainBg     = (n: number) => n >= 0
  ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
  : 'bg-red-500/10 text-red-400 border-red-500/20'
const gainBorder = (n: number) => n >= 0 ? 'border-l-emerald-500/50' : 'border-l-red-500/50'

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  label, value, sub, valueColor, subColor, accent,
}: {
  label: string
  value: string
  sub?: string
  valueColor?: string
  subColor?: string
  accent?: boolean
}) {
  return (
    <div className={clsx(
      'flex flex-col gap-1.5 rounded-xl border px-4 py-3.5 bg-zinc-900',
      accent ? 'border-indigo-500/25' : 'border-zinc-800',
    )}>
      <span className="text-[10px] font-semibold tracking-widest text-zinc-500">{label}</span>
      <span className={clsx('text-lg font-bold font-mono leading-none', valueColor ?? 'text-zinc-100')}>{value}</span>
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

// ── Transaction modal ─────────────────────────────────────────────────────────

interface TxModalProps {
  mode: 'buy' | 'sell'
  ticker: string
  tickerEditable?: boolean
  maxShares?: number
  onClose: () => void
  onSubmit: (ticker: string, shares: number, price: number) => Promise<void>
}

function TxModal({ mode, ticker: initTicker, tickerEditable = false, maxShares, onClose, onSubmit }: TxModalProps) {
  const [ticker, setTicker]   = useState(initTicker.toUpperCase())
  const [shares, setShares]   = useState('')
  const [price, setPrice]     = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError]     = useState<string | null>(null)

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
      await onSubmit(ticker.trim().toUpperCase(), sharesNum, priceNum)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
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
                $
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

          {/* Total preview */}
          {total != null && (
            <div className="bg-zinc-800/80 border border-zinc-700/50 rounded-lg px-3 py-2.5 flex items-center justify-between">
              <span className="text-xs text-zinc-500">
                Total {mode === 'buy' ? 'cost' : 'proceeds'}
              </span>
              <span className="text-sm font-mono font-semibold text-zinc-200">
                ${fmt(total)}
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
      </div>
    </div>
  )
}

// ── Holding row ───────────────────────────────────────────────────────────────

function TxRow({ txn, onDeleteRequest }: { txn: StockPurchaseHistory; onDeleteRequest: () => void }) {
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
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">${fmt(txn.bought_at)}</td>
      <td className="px-5 py-2.5 font-mono text-xs text-zinc-400">
        {txn.sale ? `$${fmt(txn.sold_at)}` : <span className="text-zinc-700">—</span>}
      </td>
      <td className="px-5 py-2.5 font-mono text-xs">
        {rowPl != null ? (
          <span className={gainText(rowPl)}>
            {sign(rowPl)}{fmtCcy(rowPl)}
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
  holding, expanded, onToggle, onBuy, onSell, onDelete, onViewTicker, onDeleteTxn,
}: {
  holding: StockHolding
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

  return (
    <div className={clsx('border-l-2 transition-colors', gainBorder(pl))}>
      {/* Main summary row — click anywhere to expand */}
      <div
        onClick={onToggle}
        className="grid grid-cols-[minmax(140px,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_32px_32px] gap-3 px-5 py-3.5 items-center hover:bg-zinc-800/40 cursor-pointer transition-colors group"
      >
        {/* Position: ticker badge + company name (ticker) */}
        <div className="flex items-center gap-2.5 min-w-0">
          <span className={clsx(
            'px-2 py-1 rounded-md text-[11px] font-bold font-mono shrink-0 whitespace-nowrap',
            pl >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-red-500/10 text-red-400',
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
        <span className="text-sm font-mono text-zinc-400 text-right">${fmt(holding.average_cost)}</span>

        {/* Current */}
        <span className="text-sm font-mono text-zinc-300 text-right">${fmt(holding.current_price)}</span>

        {/* Market value */}
        <span className="text-sm font-mono text-zinc-300 text-right">${fmt(holding.stock_value)}</span>

        {/* Unrealized P&L */}
        <div className="text-right">
          <div className={clsx('text-sm font-mono font-medium leading-none', gainText(pl))}>
            {sign(pl)}{fmtCcy(pl)}
          </div>
          <div className={clsx('text-[10px] font-mono mt-0.5', gainText(pl))}>
            {fmtPct(plPct)}
          </div>
        </div>

        {/* Realized gains */}
        <span className={clsx(
          'text-sm font-mono text-right',
          holding.total_earned > 0 ? 'text-emerald-400' : 'text-zinc-500',
        )}>
          ${fmt(holding.total_earned)}
        </span>

        {/* Dashboard link */}
        <div className="flex items-center justify-center">
          <button
            onClick={e => { e.stopPropagation(); onViewTicker() }}
            title={`View ${holding.ticker} on dashboard`}
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
      {expanded && (
        <div className="border-t border-zinc-800/60 bg-zinc-950/60">
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
                <span className="font-mono text-zinc-400">${fmt(holding.total_invested)}</span>
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
                    {['Date', 'Type', 'Shares', 'Bought @', 'Sold @', 'P&L', ''].map(col => (
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
                      onDeleteRequest={() => onDeleteTxn(txn.id, holding.trade_history.length === 1)}
                    />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function PortfolioPage({
  onViewTicker,
  onTickerRemoved,
}: {
  onViewTicker: (ticker: string) => void
  onTickerRemoved?: (ticker: string) => void
}) {
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

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      setPortfolio(await fetchPortfolio())
      setLastUpdated(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load portfolio')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    const id = setInterval(load, 2 * 60_000)
    return () => clearInterval(id)
  }, [load])

  async function submitBuy(ticker: string, shares: number, price: number) {
    await logBuy(ticker, shares, price)
    await load()
  }

  async function submitSell(ticker: string, shares: number, price: number) {
    await logSell(ticker, shares, price)
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
          <div>
            <h1 className="text-lg font-bold tracking-tight text-zinc-100">My Portfolio</h1>
            <p className="text-xs text-zinc-500 mt-0.5">
              Track positions, log transactions, monitor performance
            </p>
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
                value={fmtK(portfolio.portfolio_value)}
                accent
              />
              <StatCard
                label="COST BASIS"
                value={fmtK(portfolio.total_invested)}
              />
              <StatCard
                label="UNREALIZED RETURN"
                value={`${sign(totalRet)}${fmtK(Math.abs(totalRet))}`}
                valueColor={gainText(totalRet)}
                sub={fmtPct(portfolio.return_percentage)}
                subColor={gainText(totalRet)}
              />
              <StatCard
                label="REALIZED GAINS"
                value={fmtK(portfolio.realized_gains)}
                valueColor={portfolio.realized_gains > 0 ? gainText(1) : undefined}
              />
              <StatCard
                label="NET P&L"
                value={`${sign(netPl)}${fmtK(Math.abs(netPl))}`}
                valueColor={gainText(netPl)}
              />
            </div>

            {/* ── Holdings ───────────────────────────────────────────── */}
            {holdings.length === 0 ? (
              <EmptyState onAdd={() => setAddOpen(true)} />
            ) : (
              <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
                {/* Column headers */}
                <div className="grid grid-cols-[minmax(140px,2fr)_1fr_1fr_1fr_1fr_1.4fr_1fr_32px_32px] gap-3 px-5 py-2.5 border-b border-zinc-800 text-[10px] font-semibold tracking-widest text-zinc-500">
                  <span>POSITION</span>
                  <span className="text-right">SHARES</span>
                  <span className="text-right">AVG COST</span>
                  <span className="text-right">CURRENT</span>
                  <span className="text-right">VALUE</span>
                  <span className="text-right">UNREALIZED P&L</span>
                  <span className="text-right">REALIZED</span>
                  <span />
                  <span />
                </div>

                {/* Rows */}
                <div className="divide-y divide-zinc-800">
                  {holdings.map(h => (
                    <HoldingRow
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
                </div>

                {/* Table footer */}
                <div className="flex items-center justify-between px-5 py-2.5 border-t border-zinc-800 bg-zinc-950/40">
                  <span className="text-[10px] text-zinc-600">
                    {holdings.length} position{holdings.length !== 1 ? 's' : ''} · {portfolio.total_shares} shares held
                  </span>
                  <span className={clsx('text-xs font-mono font-semibold', gainText(netPl))}>
                    Net {sign(netPl)}{fmtK(Math.abs(netPl))}
                  </span>
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Modals ───────────────────────────────────────────────────────── */}

      {addOpen && (
        <TxModal
          mode="buy"
          ticker=""
          tickerEditable
          onClose={() => setAddOpen(false)}
          onSubmit={submitBuy}
        />
      )}

      {modal && (
        <TxModal
          mode={modal.mode}
          ticker={modal.ticker}
          maxShares={modal.mode === 'sell'
            ? (holdings.find(h => h.ticker === modal.ticker)?.shares ?? 0)
            : undefined}
          onClose={() => setModal(null)}
          onSubmit={modal.mode === 'buy' ? submitBuy : submitSell}
        />
      )}

      {txnDeleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget && !txnDeleteLoading) setTxnDeleteTarget(null) }}
        >
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-96 shadow-2xl">
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
          </div>
        </div>
      )}

      {deleteTarget && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
          onClick={e => { if (e.target === e.currentTarget) setDeleteTarget(null) }}
        >
          <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-80 shadow-2xl">
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
          </div>
        </div>
      )}
    </div>
  )
}
