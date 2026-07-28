import { useState, useRef, useEffect } from 'react'
import { X, RefreshCw } from 'lucide-react'
import { motion } from 'motion/react'
import { ExchangeSelect } from './ExchangeSelect'
import { TickerAutocomplete } from './TickerAutocomplete'
import type { Exchange } from '../utils/market'
import { overlayFade, scaleIn } from '../lib/motion'

interface Props {
  initialExchange?: Exchange
  onClose: () => void
  onSubmit: (ticker: string, exchange: Exchange) => Promise<void>
}

/** Modal for adding a ticker to the tracker watchlist — asks for the bare
 * ticker plus its exchange, so the .NS/.BO suffix is never typed by hand. */
export function AddTickerModal({ initialExchange, onClose, onSubmit }: Props) {
  const [ticker, setTicker] = useState('')
  const [exchange, setExchange] = useState<Exchange>(initialExchange ?? 'US')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => { inputRef.current?.focus() }, [])

  async function handle(e: React.FormEvent) {
    e.preventDefault()
    if (!ticker.trim()) return
    setLoading(true)
    setError(null)
    try {
      await onSubmit(ticker.trim(), exchange)
      onClose()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to add ticker')
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
      <motion.div variants={scaleIn} className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Add Ticker</h2>
            <p className="text-xs text-zinc-500 mt-0.5">Track a stock on your tracker.</p>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handle} className="space-y-4">
          {/* Exchange first: it scopes the ticker search below, and keeping it
              above means the suggestion dropdown never has to cover it. */}
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              EXCHANGE
            </label>
            <ExchangeSelect value={exchange} onChange={setExchange} />
          </div>

          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              TICKER
            </label>
            <TickerAutocomplete
              inputRef={inputRef}
              value={ticker}
              onChange={t => { setTicker(t); setError(null) }}
              exchange={exchange}
              disabled={loading}
              placeholder="e.g. AAPL or RELIANCE"
            />
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <button
            type="submit"
            disabled={loading || !ticker.trim()}
            className="w-full py-2.5 rounded-lg text-sm font-semibold transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed bg-indigo-600 hover:bg-indigo-500 text-white"
          >
            {loading && <RefreshCw size={13} className="animate-spin" />}
            Add Ticker
          </button>
        </form>
      </motion.div>
    </motion.div>
  )
}
