import { useCallback, useEffect, useRef, useState } from 'react'
import { ChevronLeft, ChevronRight, ExternalLink, Newspaper, RefreshCw } from 'lucide-react'
import { motion } from 'motion/react'
import clsx from 'clsx'
import { fetchMarketNews, fetchStockNews } from '../api'
import type { NewsArticle } from '../types'

type Mode =
  | { kind: 'market'; region?: 'all' | 'us' | 'in' }
  | { kind: 'stock'; ticker: string }

interface Props {
  mode: Mode
  limit?: number
  /** compact = tighter rows, no images (side panel usage) */
  compact?: boolean
  className?: string
}

const LAYER_LABEL: Record<string, string> = {
  company: 'Company',
  industry: 'Industry',
  sector: 'Sector',
  market: 'Market',
}

// Layer chips get subtle distinct tints so the mix of company / industry /
// sector / market coverage is scannable at a glance in the carousel.
const LAYER_STYLE: Record<string, string> = {
  company: 'border-indigo-500/40 text-indigo-300',
  industry: 'border-amber-500/40 text-amber-300',
  sector: 'border-emerald-500/40 text-emerald-300',
  market: 'border-zinc-700 text-zinc-500',
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

// ── Stock mode: horizontally scrollable card carousel ─────────────────────────

function NewsCarousel({ articles }: { articles: NewsArticle[] }) {
  const scrollerRef = useRef<HTMLDivElement>(null)
  const [canLeft, setCanLeft] = useState(false)
  const [canRight, setCanRight] = useState(false)

  const updateArrows = useCallback(() => {
    const el = scrollerRef.current
    if (!el) return
    setCanLeft(el.scrollLeft > 4)
    setCanRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 4)
  }, [])

  useEffect(() => {
    updateArrows()
    const el = scrollerRef.current
    if (!el) return
    // Track resizes too — arrow state depends on container width
    const ro = new ResizeObserver(updateArrows)
    ro.observe(el)
    return () => ro.disconnect()
  }, [updateArrows, articles.length])

  const scrollBy = (dir: 1 | -1) => {
    const el = scrollerRef.current
    if (!el) return
    el.scrollBy({ left: dir * el.clientWidth * 0.8, behavior: 'smooth' })
  }

  return (
    <div className="relative">
      {/* ‹ / › controls */}
      {canLeft && (
        <button
          onClick={() => scrollBy(-1)}
          aria-label="Scroll news left"
          className="absolute left-0 top-1/2 -translate-y-1/2 z-10 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-950/90 border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 shadow-xl transition-colors"
        >
          <ChevronLeft size={16} />
        </button>
      )}
      {canRight && (
        <button
          onClick={() => scrollBy(1)}
          aria-label="Scroll news right"
          className="absolute right-0 top-1/2 -translate-y-1/2 z-10 flex items-center justify-center w-8 h-8 rounded-full bg-zinc-950/90 border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 shadow-xl transition-colors"
        >
          <ChevronRight size={16} />
        </button>
      )}

      {/* edge fades hint that there's more to scroll */}
      {canLeft && <div className="pointer-events-none absolute left-0 inset-y-0 w-8 bg-gradient-to-r from-zinc-900 to-transparent z-[5]" />}
      {canRight && <div className="pointer-events-none absolute right-0 inset-y-0 w-8 bg-gradient-to-l from-zinc-900 to-transparent z-[5]" />}

      <div
        ref={scrollerRef}
        onScroll={updateArrows}
        className="no-scrollbar flex gap-3 overflow-x-auto pb-1 snap-x snap-mandatory"
      >
        {articles.map((a, i) => {
          const tag = a.layer ? LAYER_LABEL[a.layer] : a.region ? REGION_LABEL[a.region] : null
          const tagStyle = a.layer ? LAYER_STYLE[a.layer] : 'border-zinc-700 text-zinc-500'
          const ago = timeAgo(a.published_at)
          return (
            <motion.a
              key={a.url}
              href={a.url}
              target="_blank"
              rel="noreferrer"
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: Math.min(i * 0.03, 0.3), duration: 0.3 }}
              className="group snap-start shrink-0 w-64 flex flex-col justify-between rounded-lg border border-zinc-800 bg-zinc-950/60 hover:border-zinc-600 hover:bg-zinc-800/40 transition-colors p-3.5"
            >
              <p className="text-xs text-zinc-200 group-hover:text-zinc-100 leading-snug line-clamp-4">
                {a.title}
              </p>
              <div className="flex items-center gap-1.5 mt-3 text-[0.625rem] text-zinc-600 font-mono min-w-0">
                {tag && (
                  <span className={clsx('px-1.5 py-px rounded border shrink-0', tagStyle)}>{tag}</span>
                )}
                <span className="truncate">{a.source}</span>
                {ago && <span className="shrink-0">· {ago}</span>}
                <ExternalLink size={10} className="shrink-0 ml-auto text-zinc-700 group-hover:text-indigo-400 transition-colors" />
              </div>
            </motion.a>
          )
        })}
      </div>
    </div>
  )
}

// ── Panel ─────────────────────────────────────────────────────────────────────

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

  const isCarousel = mode.kind === 'stock'

  return (
    <div className={clsx('bg-zinc-900 border border-zinc-800 rounded-xl', compact ? 'p-3 sm:p-4' : 'p-4 sm:p-5', className)}>
      <div className="flex items-center gap-2 mb-3">
        <Newspaper size={13} className="text-indigo-400 shrink-0" />
        <p className="text-[0.625rem] text-zinc-500 tracking-widest font-medium">
          {mode.kind === 'market' ? 'MARKET HEADLINES' : `NEWS · ${mode.ticker}`}
        </p>
        {isCarousel && (
          <p className="hidden sm:block text-[0.625rem] text-zinc-600 font-mono">company · industry · sector · market</p>
        )}
        {loading && <RefreshCw size={11} className="animate-spin text-zinc-600 ml-auto" />}
      </div>

      {error ? (
        <p className="text-xs text-zinc-500 py-3">
          Headlines are unavailable right now — the free news sources may be rate-limiting. They retry automatically.
        </p>
      ) : articles === null ? (
        isCarousel ? (
          <div className="flex gap-3 py-1">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="w-64 h-28 shrink-0 rounded-lg bg-zinc-800/60 animate-pulse" />
            ))}
          </div>
        ) : (
          <div className="space-y-2.5 py-1">
            {Array.from({ length: compact ? 4 : 5 }).map((_, i) => (
              <div key={i} className="h-8 rounded-md bg-zinc-800/60 animate-pulse" />
            ))}
          </div>
        )
      ) : articles.length === 0 ? (
        <p className="text-xs text-zinc-500 py-3">No recent headlines found.</p>
      ) : isCarousel ? (
        <NewsCarousel articles={articles} />
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
                    <p className={clsx('text-zinc-200 group-hover:text-zinc-100 leading-snug', compact ? 'text-xs' : 'text-[0.8125rem]')}>
                      {a.title}
                    </p>
                    <p className="flex items-center gap-1.5 mt-1 text-[0.625rem] text-zinc-600 font-mono">
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
