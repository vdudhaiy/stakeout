import { useEffect, useState } from 'react'
import { Users, ArrowUpRight } from 'lucide-react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { fetchPeers, fetchQuoteBatch } from '../api'
import { displayTicker } from '../utils/market'
import { Sparkline } from './Sparkline'
import type { Quote } from '../types'

interface Props {
  ticker: string
  /** ticker -> display name, for peers that happen to already be tracked */
  knownNames?: Record<string, string>
  /** Switches the tracker to a peer ticker. Omit to render chips as inert. */
  onSelect?: (ticker: string) => void
  className?: string
}

export function PeersPanel({ ticker, knownNames, onSelect, className }: Props) {
  const [peers, setPeers] = useState<string[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [quotes, setQuotes] = useState<Record<string, Quote | null>>({})

  useEffect(() => {
    let cancelled = false
    setPeers(null)
    setError(null)
    setQuotes({})
    fetchPeers(ticker)
      .then(res => { if (!cancelled) setPeers(res.peers) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load peers') })
    return () => { cancelled = true }
  }, [ticker])

  // Batched once the peer list is known, via Finnhub's /quote — not
  // per-peer yfinance calls, which would multiply this panel's cost by
  // however many peers are shown (see PR discussion: this stays cheap
  // because it's one HTTP round trip regardless of peer count).
  useEffect(() => {
    if (!peers || peers.length === 0) return
    let cancelled = false
    fetchQuoteBatch(peers)
      .then(res => { if (!cancelled) setQuotes(res.quotes) })
      .catch(() => { /* sparklines are decorative — chips still work without them */ })
    return () => { cancelled = true }
  }, [peers])

  return (
    <div className={clsx('bg-zinc-900 border border-zinc-800 rounded-xl p-4 sm:p-5', className)}>
      <div className="flex items-center gap-2 mb-3">
        <Users size={13} className="text-indigo-400 shrink-0" />
        <p className="text-[0.625rem] text-zinc-500 tracking-widest font-medium">PEER COMPANIES</p>
      </div>

      {error ? (
        <p className="text-xs text-zinc-500 py-3">
          Peer data is unavailable right now — it retries automatically.
        </p>
      ) : peers === null ? (
        <div className="flex flex-wrap gap-2 py-1">
          {Array.from({ length: 6 }).map((_, i) => (
            <div key={i} className="h-14 w-24 rounded-lg bg-zinc-800/60 animate-pulse" />
          ))}
        </div>
      ) : peers.length === 0 ? (
        <p className="text-xs text-zinc-500 py-3">No peer companies found for this stock.</p>
      ) : (
        <div className="flex flex-wrap gap-2 py-1">
          {peers.map((p, i) => {
            const name = knownNames?.[p]
            const clickable = !!onSelect
            const Tag = clickable ? motion.button : motion.div
            const quote = quotes[p]
            const sparkPoints = quote && quote.prev_close != null && quote.open != null && quote.close != null
              ? [quote.prev_close, quote.open, quote.close]
              : null
            const up = quote?.change != null ? quote.change >= 0 : null

            return (
              <Tag
                key={p}
                type={clickable ? 'button' : undefined}
                onClick={clickable ? () => onSelect!(p) : undefined}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.25 }}
                whileHover={clickable ? { y: -2 } : undefined}
                whileTap={clickable ? { scale: 0.97 } : undefined}
                className={clsx(
                  'group flex flex-col gap-1.5 min-w-[5.5rem] rounded-lg border px-3 py-2 text-left transition-colors',
                  clickable
                    ? 'border-zinc-700 hover:border-indigo-500/60 hover:bg-indigo-500/5 cursor-pointer'
                    : 'border-zinc-800',
                )}
                title={name ?? displayTicker(p)}
              >
                <span className="flex items-center gap-1 text-xs font-mono text-zinc-300 group-hover:text-indigo-300 transition-colors">
                  {displayTicker(p)}
                  {clickable && (
                    <ArrowUpRight size={10} className="ml-auto text-zinc-700 group-hover:text-indigo-400 transition-colors" />
                  )}
                </span>
                <span className={clsx(
                  'flex items-center gap-1.5',
                  up === null ? 'text-zinc-700' : up ? 'text-emerald-400' : 'text-red-400',
                )}>
                  {sparkPoints ? (
                    <Sparkline points={sparkPoints} width={32} height={14} />
                  ) : (
                    <span className="h-3.5 w-8 rounded bg-zinc-800/80" />
                  )}
                  {quote?.change_percent != null && (
                    <span className="text-[0.625rem] font-mono">
                      {quote.change_percent >= 0 ? '+' : ''}{quote.change_percent.toFixed(1)}%
                    </span>
                  )}
                </span>
              </Tag>
            )
          })}
        </div>
      )}
    </div>
  )
}
