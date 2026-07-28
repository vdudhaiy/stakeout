import { useEffect, useRef, useState } from 'react'
import clsx from 'clsx'
import { RefreshCw } from 'lucide-react'
import { motion, AnimatePresence } from 'motion/react'
import type { TickerSuggestion } from '../types'
import type { Exchange } from '../utils/market'
import { searchTickers } from '../api'
import { popIn } from '../lib/motion'

const DEBOUNCE_MS = 300

interface Props {
  value: string
  onChange: (ticker: string) => void
  exchange: Exchange
  disabled?: boolean
  placeholder?: string
  inputRef?: React.RefObject<HTMLInputElement>
}

/** Ticker/company-name autocomplete for the "add ticker" flows.
 *
 * Scoped to `exchange` server-side, so switching between US/NSE/BSE in the
 * exchange picker re-searches automatically. Suggestions are bare tickers —
 * no .NS/.BO suffix — since applying that suffix is the exchange picker's
 * job, not this component's; selecting one just fills the plain symbol. */
export function TickerAutocomplete({ value, onChange, exchange, disabled, placeholder, inputRef }: Props) {
  const [suggestions, setSuggestions] = useState<TickerSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [loading, setLoading] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const containerRef = useRef<HTMLDivElement>(null)
  const requestIdRef = useRef(0)

  useEffect(() => {
    const query = value.trim()
    if (query.length === 0) {
      setSuggestions([])
      setOpen(false)
      return
    }
    const id = ++requestIdRef.current
    setLoading(true)
    const timer = setTimeout(async () => {
      const results = await searchTickers(query, exchange)
      if (id !== requestIdRef.current) return  // a newer keystroke/exchange change superseded this
      setSuggestions(results)
      setHighlighted(0)
      setOpen(results.length > 0)
      setLoading(false)
    }, DEBOUNCE_MS)
    return () => clearTimeout(timer)
  }, [value, exchange])

  useEffect(() => {
    function onClickOutside(e: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClickOutside)
    return () => document.removeEventListener('mousedown', onClickOutside)
  }, [])

  function select(s: TickerSuggestion) {
    onChange(s.symbol)
    setOpen(false)
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlighted(h => (h + 1) % suggestions.length)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlighted(h => (h - 1 + suggestions.length) % suggestions.length)
    } else if (e.key === 'Enter') {
      e.preventDefault()
      select(suggestions[highlighted])
    } else if (e.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div ref={containerRef} className="relative">
      <div className="relative">
        <input
          ref={inputRef}
          type="text"
          value={value}
          onChange={e => onChange(e.target.value.toUpperCase())}
          onFocus={() => { if (suggestions.length > 0) setOpen(true) }}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder={placeholder}
          autoComplete="off"
          className="w-full bg-zinc-800 border border-zinc-700 rounded-lg px-3 py-2 text-sm font-mono uppercase text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
        />
        {loading && (
          <RefreshCw size={12} className="absolute right-3 top-1/2 -translate-y-1/2 text-zinc-600 animate-spin" />
        )}
      </div>

      <AnimatePresence>
        {open && suggestions.length > 0 && (
          <motion.div
            variants={popIn}
            initial="hidden"
            animate="show"
            exit="exit"
            className="absolute z-20 top-full mt-1.5 w-full bg-zinc-800 border border-zinc-700 rounded-lg shadow-xl overflow-hidden max-h-56 overflow-y-auto"
          >
            {suggestions.map((s, i) => (
              <button
                key={s.symbol}
                type="button"
                onMouseDown={e => e.preventDefault()}  // keep the input focused so onChange/select land in order
                onClick={() => select(s)}
                onMouseEnter={() => setHighlighted(i)}
                className={clsx(
                  'w-full text-left px-3 py-2 flex items-center justify-between gap-3 transition-colors',
                  i === highlighted ? 'bg-indigo-500/15' : 'hover:bg-zinc-700/40',
                )}
              >
                <span className="min-w-0 flex flex-col">
                  <span className="font-mono text-sm text-zinc-100">{s.symbol}</span>
                  <span className="text-xs text-zinc-500 truncate">{s.name}</span>
                </span>
                <span className="text-[10px] text-zinc-600 shrink-0 whitespace-nowrap">{s.exchange}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
