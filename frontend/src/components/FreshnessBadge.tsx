import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'motion/react'
import {
  SOURCE_BLURB, SOURCE_LABEL, formatAge, formatExact, useDataFreshness,
} from '../lib/freshness'
import { popIn } from '../lib/motion'

const POPOVER_WIDTH = 248  // px — matches the w-[248px] popover below
const VIEWPORT_MARGIN = 8

// How often the "6m ago" text re-renders. The underlying timestamp is fixed;
// only its distance from now moves, and a badge that silently ages into a lie
// is worse than no badge at all.
const TICK_MS = 30_000

interface Props {
  /** Request path to report on (query string ignored), e.g. `/stocks/AAPL`. */
  path: string | null | undefined
  /** Optional lead-in, e.g. "Prices". Rendered before the age. */
  label?: string
  align?: 'left' | 'right'
  className?: string
}

const DOT: Record<string, string> = {
  live: 'bg-emerald-400',
  cached: 'bg-indigo-400',
  archive: 'bg-amber-400',
  stale: 'bg-rose-400',
}

const TEXT: Record<string, string> = {
  live: 'text-zinc-500',
  cached: 'text-zinc-500',
  archive: 'text-amber-500',
  stale: 'text-rose-400',
}

/**
 * "as of" marker for a panel, sourced entirely from the backend.
 *
 * The distinction it draws is not cosmetic: a live quote, a six-hour-old
 * cached snapshot, a chart read from the archive, and a week-old copy served
 * because the provider rate-limited us all render as ordinary numbers. Only
 * the server knows which of those is on screen, so only the server dates it
 * (see lib/freshness.ts and backend/src/freshness.py).
 *
 * Renders nothing when there's no provenance to report — a guest-mode view,
 * or an endpoint with nothing upstream behind it — rather than occupying the
 * layout with an empty claim.
 */
export function FreshnessBadge({ path, label, align = 'right', className = '' }: Props) {
  const info = useDataFreshness(path)
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)
  const [, setTick] = useState(0)
  const btnRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const id = setInterval(() => setTick(t => t + 1), TICK_MS)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    if (!open) return
    function close(e: MouseEvent) {
      const target = e.target as Node
      if (btnRef.current?.contains(target) || popoverRef.current?.contains(target)) return
      setOpen(false)
    }
    function esc(e: KeyboardEvent) { if (e.key === 'Escape') setOpen(false) }
    function dismiss() { setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    window.addEventListener('scroll', dismiss, true)
    window.addEventListener('resize', dismiss)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
      window.removeEventListener('scroll', dismiss, true)
      window.removeEventListener('resize', dismiss)
    }
  }, [open])

  if (!info) return null

  const age = info.fetchedAt ? formatAge(info.fetchedAt) : 'time unknown'
  const dot = DOT[info.source] ?? 'bg-zinc-500'
  const tone = TEXT[info.source] ?? 'text-zinc-500'

  function toggle(e: React.MouseEvent) {
    e.stopPropagation()
    setOpen(o => {
      const next = !o
      if (next && btnRef.current) {
        const rect = btnRef.current.getBoundingClientRect()
        const left = Math.max(
          VIEWPORT_MARGIN,
          Math.min(
            align === 'right' ? rect.right - POPOVER_WIDTH : rect.left,
            window.innerWidth - POPOVER_WIDTH - VIEWPORT_MARGIN,
          ),
        )
        setCoords({ top: rect.bottom + 6, left })
      }
      return next
    })
  }

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-label={`Data freshness: ${SOURCE_LABEL[info.source]}, ${age}`}
        className={`tap-target inline-flex items-center gap-1.5 text-[0.625rem] leading-none ${tone} hover:text-zinc-300 focus-visible:outline focus-visible:outline-1 focus-visible:outline-indigo-400 rounded transition-colors ${className}`}
      >
        <motion.span
          className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`}
          // Only the live dot pulses. An animated marker on stale data would
          // read as activity, which is the opposite of what it means.
          animate={info.source === 'live' ? { opacity: [1, 0.35, 1] } : { opacity: 1 }}
          transition={info.source === 'live'
            ? { duration: 2.4, repeat: Infinity, ease: 'easeInOut' }
            : { duration: 0.2 }}
        />
        <span className="whitespace-nowrap">
          {label ? `${label} ` : ''}{age}
        </span>
      </button>

      {coords && createPortal(
        <div ref={popoverRef}>
          <AnimatePresence>
            {open && (
              <motion.div
                role="tooltip"
                variants={popIn}
                initial="hidden"
                animate="show"
                exit="exit"
                style={{
                  position: 'fixed', top: coords.top, left: coords.left,
                  transformOrigin: align === 'right' ? 'top right' : 'top left',
                }}
                className="z-50 w-[248px] rounded-lg border border-zinc-700 bg-zinc-950 p-3 shadow-2xl text-left normal-case tracking-normal whitespace-normal"
              >
                <span className="flex items-center gap-1.5 mb-1.5">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
                  <span className="text-[0.6875rem] font-semibold text-zinc-100">
                    {SOURCE_LABEL[info.source]}
                  </span>
                </span>
                <span className="block text-[0.6875rem] leading-relaxed text-zinc-400 font-normal font-sans mb-2">
                  {SOURCE_BLURB[info.source]}
                </span>
                <dl className="text-[0.6875rem] leading-relaxed font-sans">
                  <div className="flex justify-between gap-3">
                    <dt className="text-zinc-500">Pulled</dt>
                    <dd className="text-zinc-300 text-right">
                      {info.fetchedAt ? formatExact(info.fetchedAt) : 'Not recorded'}
                    </dd>
                  </div>
                  {info.dataThrough && (
                    <div className="flex justify-between gap-3">
                      <dt className="text-zinc-500">Data through</dt>
                      <dd className="text-zinc-300 text-right">{info.dataThrough}</dd>
                    </div>
                  )}
                </dl>
              </motion.div>
            )}
          </AnimatePresence>
        </div>,
        document.body,
      )}
    </>
  )
}
