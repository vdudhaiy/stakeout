import { useState } from 'react'
import { AlertTriangle, RefreshCw, Trash2, X } from 'lucide-react'
import { motion } from 'motion/react'
import clsx from 'clsx'

import type { PortfolioStats, StockHolding } from '../../types'
import { overlayFade, scaleIn } from '../../lib/motion'

type MoneyFmt = (v: number | null | undefined, opts?: { sign?: boolean; compact?: boolean }) => string

/**
 * Three confirmations before a portfolio is deleted.
 *
 * They're three different questions, not the same one asked three times —
 * each is meant to catch a different kind of mistake:
 *   1. scale     — exactly what is about to be destroyed, counted
 *   2. finality  — that Undo cannot bring it back
 *   3. intent    — retype the name, so the wrong tab can't be deleted by reflex
 *
 * Deleting is genuinely destructive (holdings, transactions and dividend
 * history all go), which is why the flow is this heavy.
 */
export function DeletePortfolioModal({
  portfolio, holdings, money, onClose, onConfirm,
}: {
  portfolio: PortfolioStats
  /** Holdings belonging to this portfolio — used only for the counts in step 1. */
  holdings: StockHolding[]
  money: MoneyFmt
  onClose: () => void
  onConfirm: () => Promise<void>
}) {
  const [step, setStep] = useState<1 | 2 | 3>(1)
  const [typed, setTyped] = useState('')
  const [deleting, setDeleting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const positions = holdings.length
  const transactions = holdings.reduce((n, h) => n + h.trade_history.length, 0)
  const dividends = holdings.reduce((n, h) => n + h.dividends.length, 0)
  const nameMatches = typed.trim() === portfolio.name

  async function handleDelete() {
    setDeleting(true)
    setError(null)
    try {
      await onConfirm()
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to delete portfolio')
      setDeleting(false)
    }
  }

  return (
    <motion.div
      variants={overlayFade}
      initial="hidden"
      animate="show"
      exit="exit"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget && !deleting) onClose() }}
    >
      <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-start justify-between mb-3">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              Delete "{portfolio.name}"
            </h2>
            <p className="text-[0.625rem] text-zinc-600 mt-0.5 tracking-widest font-semibold">
              STEP {step} OF 3
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={deleting}
            className="tap-target p-1.5 -m-1 text-zinc-600 hover:text-zinc-300 transition-colors disabled:opacity-40"
          >
            <X size={15} />
          </button>
        </div>

        {/* Step markers — makes it obvious this is a sequence, not a loop. */}
        <div className="flex gap-1 mb-4">
          {[1, 2, 3].map(n => (
            <span
              key={n}
              className={clsx('h-0.5 flex-1 rounded-full transition-colors',
                n <= step ? 'bg-red-500' : 'bg-zinc-800')}
            />
          ))}
        </div>

        {step === 1 && (
          <>
            <p className="text-xs text-zinc-400 leading-relaxed mb-3">
              Deleting this portfolio permanently removes everything in it:
            </p>
            <div className="rounded-xl border border-zinc-800 bg-zinc-950/50 divide-y divide-zinc-800/70 mb-4">
              {[
                ['Positions', String(positions)],
                ['Transactions', String(transactions)],
                ['Dividend entries', String(dividends)],
                ['Current value', money(portfolio.portfolio_value)],
              ].map(([label, value]) => (
                <div key={label} className="flex items-center justify-between px-3 py-2">
                  <span className="text-xs text-zinc-500">{label}</span>
                  <span className="text-xs font-mono font-semibold text-zinc-200">{value}</span>
                </div>
              ))}
            </div>
            <p className="text-[0.625rem] text-zinc-600 leading-relaxed mb-4">
              Your other portfolios in this market are not affected, and price
              history stays in the tracker.
            </p>
          </>
        )}

        {step === 2 && (
          <div className="flex items-start gap-3 bg-amber-500/8 border border-amber-500/25 rounded-xl px-4 py-3 mb-4">
            <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="text-xs font-semibold text-amber-400">This cannot be undone</p>
              <p className="text-xs text-zinc-400 leading-relaxed">
                Undo won't bring it back — the deletion is not added to your
                undo history. If you might want this data later, export the
                market first and keep the file.
              </p>
            </div>
          </div>
        )}

        {step === 3 && (
          <>
            <p className="text-xs text-zinc-400 leading-relaxed mb-3">
              Type <span className="font-mono font-semibold text-zinc-200">{portfolio.name}</span> to confirm.
            </p>
            <input
              autoFocus
              value={typed}
              onChange={e => setTyped(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter' && nameMatches) handleDelete() }}
              placeholder={portfolio.name}
              className="w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono text-zinc-100 placeholder:text-zinc-700 focus:outline-none focus:border-red-500 transition-colors mb-4"
            />
          </>
        )}

        {error && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 mb-4">
            <X size={13} className="text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs text-red-400 leading-relaxed">{error}</p>
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={step === 1 ? onClose : () => setStep(s => (s - 1) as 1 | 2)}
            disabled={deleting}
            className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
          >
            {step === 1 ? 'Cancel' : 'Back'}
          </button>
          {step < 3 ? (
            <button
              onClick={() => setStep(s => (s + 1) as 2 | 3)}
              className="px-3 py-1.5 text-xs rounded-lg bg-zinc-800 hover:bg-zinc-700 text-zinc-100 font-medium transition-colors"
            >
              Continue
            </button>
          ) : (
            <button
              onClick={handleDelete}
              disabled={!nameMatches || deleting}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-red-600 hover:bg-red-500 text-white font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {deleting ? <RefreshCw size={11} className="animate-spin" /> : <Trash2 size={11} />}
              Delete portfolio
            </button>
          )}
        </div>
      </motion.div>
    </motion.div>
  )
}
