import { useEffect, useState } from 'react'
import clsx from 'clsx'
import { fetchCurrentStock } from '../api'
import { formatMoney } from '../utils/currency'
import { TICKER_TAPE_REFRESH_MS } from '../utils/env'
import type { WatchlistMap } from '../types'

interface Quote {
  ticker: string
  market: 'US' | 'IN'
  price: number | null
}

interface Props {
  tickers: WatchlistMap | null
}

/**
 * The Stakeout signature: a slim ticker tape under the navbar streaming the
 * watchlist's latest prices. Pauses on hover; disabled entirely when the
 * user prefers reduced motion (see index.css).
 */
export function TickerTape({ tickers }: Props) {
  const [quotes, setQuotes] = useState<Quote[]>([])

  useEffect(() => {
    if (!tickers) return
    const symbols = Object.keys(tickers).slice(0, 12) // keep it light
    if (symbols.length === 0) { setQuotes([]); return }
    let cancelled = false

    async function load() {
      const results = await Promise.all(
        symbols.map(async t => {
          try {
            const res = await fetchCurrentStock(t)
            return { ticker: t, market: tickers![t].market, price: res.data[0]?.close ?? null }
          } catch {
            return { ticker: t, market: tickers![t].market, price: null }
          }
        }),
      )
      if (!cancelled) setQuotes(results.filter(q => q.price != null))
    }

    load()
    const id = setInterval(load, TICKER_TAPE_REFRESH_MS)
    return () => { cancelled = true; clearInterval(id) }
  }, [tickers])

  if (quotes.length === 0) return null

  const items = [...quotes, ...quotes] // duplicated for a seamless loop

  return (
    <div className="ticker-tape shrink-0 border-b border-zinc-800 bg-zinc-900/60" aria-hidden="true">
      <div className="ticker-tape-track py-1.5">
        {items.map((q, i) => (
          <span key={`${q.ticker}-${i}`} className="flex items-center gap-2 px-5 text-[11px] font-mono">
            <span className={clsx('w-1 h-1 rounded-full', q.market === 'IN' ? 'bg-amber-400' : 'bg-indigo-400')} />
            <span className="text-zinc-400">{q.ticker}</span>
            <span className="text-zinc-200">
              {formatMoney(q.price, q.market === 'IN' ? 'INR' : 'USD')}
            </span>
          </span>
        ))}
      </div>
    </div>
  )
}
