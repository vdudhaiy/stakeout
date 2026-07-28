import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { AnimatePresence, motion } from 'motion/react'
import { GLOSSARY, type GlossaryKey } from '../utils/glossary'
import { popIn } from '../lib/motion'

const POPOVER_WIDTH = 240  // px — matches w-60
const VIEWPORT_MARGIN = 8

interface Props {
  k: GlossaryKey
  /** Popover alignment relative to the trigger */
  align?: 'left' | 'right'
}

/**
 * The (?) helper next to every statistic. Click to open a short explanation
 * of what the stat is, what it means, and how to read it. Content lives in
 * utils/glossary.ts so wording stays consistent app-wide.
 *
 * The popover is rendered in a portal (document.body), positioned from the
 * trigger's viewport rect, rather than as a normal DOM child — some triggers
 * live inside an `overflow: hidden` expand/collapse panel (e.g. the
 * portfolio holding row), and an in-place absolutely-positioned popover gets
 * silently clipped by that ancestor. Portaling escapes it entirely.
 */
export function InfoTip({ k, align = 'left' }: Props) {
  const [open, setOpen] = useState(false)
  const [coords, setCoords] = useState<{ top: number; left: number } | null>(null)
  const btnRef = useRef<HTMLButtonElement>(null)
  const popoverRef = useRef<HTMLDivElement>(null)
  const entry = GLOSSARY[k]

  useEffect(() => {
    if (!open) return
    function close(e: MouseEvent) {
      const target = e.target as Node
      if (btnRef.current?.contains(target) || popoverRef.current?.contains(target)) return
      setOpen(false)
    }
    function esc(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    // The popover is positioned from a one-time rect snapshot, not tracked
    // continuously — closing on scroll/resize avoids it drifting away from
    // its trigger rather than trying to keep it glued in place.
    function dismissOnLayoutChange() { setOpen(false) }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    window.addEventListener('scroll', dismissOnLayoutChange, true)
    window.addEventListener('resize', dismissOnLayoutChange)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
      window.removeEventListener('scroll', dismissOnLayoutChange, true)
      window.removeEventListener('resize', dismissOnLayoutChange)
    }
  }, [open])

  if (!entry) return null

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
        aria-label={`What is ${entry.title}?`}
        aria-expanded={open}
        onClick={toggle}
        className="inline-flex items-center justify-center w-3.5 h-3.5 rounded-full border border-zinc-600 text-zinc-500 text-[9px] leading-none font-semibold hover:border-indigo-400 hover:text-indigo-400 focus-visible:outline focus-visible:outline-1 focus-visible:outline-indigo-400 transition-colors select-none"
      >
        ?
      </button>
      {coords && createPortal(
        // The outside-click ref sits on this plain wrapper, not on the
        // motion.div AnimatePresence animates — handing motion.div a second,
        // externally-owned ref alongside AnimatePresence's own exit-tracking
        // ref trips a dev-mode React warning.
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
                className="z-50 w-60 rounded-lg border border-zinc-700 bg-zinc-950 p-3 shadow-2xl text-left normal-case tracking-normal whitespace-normal"
              >
                <span className="block text-[11px] font-semibold text-zinc-100 mb-1">{entry.title}</span>
                <span className="block text-[11px] leading-relaxed text-zinc-400 font-normal font-sans">{entry.body}</span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>,
        document.body,
      )}
    </>
  )
}
