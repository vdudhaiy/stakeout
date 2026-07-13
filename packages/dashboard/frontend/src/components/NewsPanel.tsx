import { useEffect, useState } from 'react'
import { ExternalLink, Newspaper, RefreshCw } from 'lucide-react'
import { motion } from 'framer-motion'
import clsx from 'clsx'
import { fetchMarketNews, fetchStockNews } from '../api'
import type { NewsArticle } from '../types'

type Mode =
  | { kind: 'market'; region?: 'all' | 'us' | 'in' }
  | { kind: 'stock'; ticker: string }

interface Props {
  mode: Mode
  limit?: number
  /** compact = tighter rows, no images (dashboard side panel) */
  compact?: boolean
  className?: string
}

const LAYER_LABEL: Record<string, string> = {
  company: 'Company',
  industry: 'Industry',
  market: 'Market',
}

const REGION_LABEL: Record<string, string> = { us: 'US', in: 'India', global: 'Global' }

function timeAgo(iso?: string | null): string | null {
  if (!iso) return null
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return null
  const mins = Math.max(0, Math.round((Date.now() - then) / 60_000))
  if (mins < 60) return `${mins}m ago`
  const hours = Math.round(mins / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function NewsPanel({ mode, limit = 10, compact = false, className }: Props) {
  const [articles, setArticles] = useState<NewsArticle[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  const key = mode.kind === 'market' ? `market:${mode.region ?? 'all'}` : `stock:${mode.ticker}`

  useEffect(() => {
    let cancelled = false
    setArticles(null)
    setError(null)
    setLoading(true)
    const load = mode.kind === 'market'
      ? fetchMarketNews(mode.region ?? 'all', limit)
      : fetchStockNews(mode.ticker, limit)
    load
      .then(res => { if (!cancelled) setArticles(res.articles) })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Failed to load news') })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, limit])

  return (
    <div className={clsx('bg-zinc-900 border border-zinc-800 rounded-xl', compact ? 'p-4' : 'p-5', className)}>
      <div className="flex items-center gap-2 mb-3">
        <Newspaper size={13} className="text-indigo-400 shrink-0" />
        <p className="text-[10px] text-zinc-500 tracking-widest font-medium">
          {mode.kind === 'market' ? 'MARKET HEADLINES' : `NEWS · ${mode.ticker}`}
        </p>
        {loading && <RefreshCw size={11} className="animate-spin text-zinc-600 ml-auto" />}
      </div>

      {error ? (
        <p className="text-xs text-zinc-500 py-3">
          Headlines are unavailable right now — the free news sources may be rate-limiting. They retry automatically.
        </p>
      ) : articles === null ? (
        <div className="space-y-2.5 py-1">
          {Array.from({ length: compact ? 4 : 5 }).map((_, i) => (
            <div key={i} className="h-8 rounded-md bg-zinc-800/60 animate-pulse" />
          ))}
        </div>
      ) : articles.length === 0 ? (
        <p className="text-xs text-zinc-500 py-3">No recent headlines found.</p>
      ) : (
        <ul className={clsx('divide-y divide-zinc-800/70', compact ? '-my-1' : '')}>
          {articles.map((a, i) => {
            const tag = a.layer ? LAYER_LABEL[a.layer] : a.region ? REGION_LABEL[a.region] : null
            const ago = timeAgo(a.published_at)
            return (
              <motion.li
                key={a.url}
                initial={{ opacity: 0, y: 6 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: Math.min(i * 0.04, 0.4), duration: 0.3 }}
              >
                <a
                  href={a.url}
                  target="_blank"
                  rel="noreferrer"
                  className="group flex items-start gap-2 py-2.5 hover:bg-zinc-800/40 -mx-2 px-2 rounded-md transition-colors"
                >
                  <div className="min-w-0 flex-1">
                    <p className={clsx('text-zinc-200 group-hover:text-zinc-100 leading-snug', compact ? 'text-xs' : 'text-[13px]')}>
                      {a.title}
                    </p>
                    <p className="flex items-center gap-1.5 mt-1 text-[10px] text-zinc-600 font-mono">
                      {tag && (
                        <span className="px-1.5 py-px rounded border border-zinc-700 text-zinc-500">{tag}</span>
                      )}
                      <span className="truncate">{a.source}</span>
                      {ago && <span className="shrink-0">· {ago}</span>}
                    </p>
                  </div>
                  <ExternalLink size={11} className="shrink-0 mt-1 text-zinc-700 group-hover:text-indigo-400 transition-colors" />
                </a>
              </motion.li>
            )
          })}
        </ul>
      )}
    </div>
  )
}
