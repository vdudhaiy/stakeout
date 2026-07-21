import { useState, useRef, useEffect } from 'react'
import { X, RefreshCw } from 'lucide-react'
import { ExchangeSelect } from './ExchangeSelect'
import type { Exchange } from '../utils/market'

interface Props {
  initialExchange?: Exchange
  onClose: () => void
  onSubmit: (ticker: string, exchange: Exchange) => Promise<void>
}

/** Modal for adding a ticker to the dashboard watchlist — asks for the bare
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
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={e => { if (e.target === e.currentTarget) onClose() }}
    >
      <div className="bg-zinc-900 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl">
        <div className="flex items-start justify-between mb-4">
          <div>
            <h2 className="text-sm font-semibold text-zinc-100">Add Ticker</h2>
            <p className="text-xs text-zinc-500 mt-0.5">Track a stock on your dashboard.</p>
          </div>
          <button onClick={onClose} className="p-1 text-zinc-600 hover:text-zinc-300 transition-colors">
            <X size={15} />
          </button>
        </div>

        <form onSubmit={handle} className="space-y-4">
          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              TICKER
            </label>
            <input
              ref={inputRef}
              type="text"
              value={ticker}
              onChange={e => { setTicker(e.target.value.toUpperCase()); setError(null) }}
              disabled={loading}
              placeholder="e.g. AAPL or RELIANCE"
              className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono uppercase text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
            />
          </div>

          <div>
            <label className="block text-[10px] font-semibold tracking-widest text-zinc-500 mb-1.5">
              EXCHANGE
            </label>
            <ExchangeSelect value={exchange} onChange={setExchange} />
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
      </div>
    </div>
  )
}
