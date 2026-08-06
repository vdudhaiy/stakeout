import { useState } from 'react'
import { RefreshCw, X } from 'lucide-react'
import { motion } from 'motion/react'

import type { Market } from '../../types'
import { overlayFade, scaleIn } from '../../lib/motion'

const MAX_NAME_LENGTH = 40   // matches portfolio_admin_service.MAX_NAME_LENGTH

/** Creates a portfolio or renames one — the two differ only in wording. */
export function PortfolioNameModal({
  mode, market, initialName = '', onClose, onSubmit,
}: {
  mode: 'create' | 'rename'
  market: Market
  initialName?: string
  onClose: () => void
  onSubmit: (name: string) => Promise<void>
}) {
  const [name, setName] = useState(initialName)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const marketLabel = market === 'IN' ? 'India' : 'US'
  const trimmed = name.trim()
  const unchanged = mode === 'rename' && trimmed === initialName.trim()
  const canSubmit = trimmed.length > 0 && trimmed.length <= MAX_NAME_LENGTH && !unchanged && !saving

  async function handleSubmit() {
    if (!canSubmit) return
    setSaving(true)
    setError(null)
    try {
      await onSubmit(trimmed)
      onClose()
    } catch (e) {
      // Duplicate names come back as a 409 with a usable message — show it
      // rather than a generic failure, since it's the common case.
      setError(e instanceof Error ? e.message : 'Failed to save portfolio')
      setSaving(false)
    }
  }

  return (
    <motion.div
      variants={overlayFade}
      initial="hidden"
      animate="show"
      exit="exit"
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm p-4"
      onClick={e => { if (e.target === e.currentTarget && !saving) onClose() }}
    >
      <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-5 sm:p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-start justify-between mb-1">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">
              {mode === 'create' ? 'New portfolio' : 'Rename portfolio'}
            </h2>
            <p className="text-xs text-zinc-500 mt-0.5">
              {mode === 'create'
                ? `A separate set of positions in your ${marketLabel} market, with its own cost basis.`
                : 'Only the name changes — positions and history stay put.'}
            </p>
          </div>
          <button
            onClick={onClose}
            disabled={saving}
            className="tap-target p-1.5 -m-1 text-zinc-600 hover:text-zinc-300 transition-colors disabled:opacity-40"
          >
            <X size={15} />
          </button>
        </div>

        <label className="block mt-4">
          <span className="text-[0.625rem] font-semibold tracking-widest text-zinc-500">NAME</span>
          <input
            autoFocus
            value={name}
            maxLength={MAX_NAME_LENGTH}
            onChange={e => setName(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter') handleSubmit() }}
            placeholder="e.g. Zerodha, Long term, 401k"
            className="mt-1 w-full bg-zinc-950 border border-zinc-700 rounded-lg px-3 py-2 text-sm text-zinc-100 placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors"
          />
        </label>
        <p className="text-[0.625rem] text-zinc-600 mt-1">
          {trimmed.length}/{MAX_NAME_LENGTH} · must be unique within your {marketLabel} portfolios
        </p>

        {error && (
          <div className="flex items-start gap-2 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2.5 mt-3">
            <X size={13} className="text-red-400 shrink-0 mt-0.5" />
            <p className="text-xs text-red-400 leading-relaxed">{error}</p>
          </div>
        )}

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={onClose}
            disabled={saving}
            className="px-3 py-1.5 text-xs rounded-lg text-zinc-300 hover:bg-zinc-800 transition-colors disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving && <RefreshCw size={11} className="animate-spin" />}
            {mode === 'create' ? 'Create' : 'Save'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  )
}
