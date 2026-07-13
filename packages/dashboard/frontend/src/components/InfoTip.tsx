import { useEffect, useRef, useState } from 'react'
import { GLOSSARY, type GlossaryKey } from '../utils/glossary'

interface Props {
  k: GlossaryKey
  /** Popover alignment relative to the trigger */
  align?: 'left' | 'right'
}

/**
 * The (?) helper next to every statistic. Click to open a short explanation
 * of what the stat is, what it means, and how to read it. Content lives in
 * utils/glossary.ts so wording stays consistent app-wide.
 */
export function InfoTip({ k, align = 'left' }: Props) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLSpanElement>(null)
  const entry = GLOSSARY[k]

  useEffect(() => {
    if (!open) return
    function close(e: MouseEvent) {
      if (!ref.current?.contains(e.target as Node)) setOpen(false)
    }
    function esc(e: KeyboardEvent) {
      if (e.key === 'Escape') setOpen(false)
    }
    document.addEventListener('mousedown', close)
    document.addEventListener('keydown', esc)
    return () => {
      document.removeEventListener('mousedown', close)
      document.removeEventListener('keydown', esc)
    }
  }, [open])

  if (!entry) return null

  return (
    <span ref={ref} className="relative inline-flex">
      <button
        type="button"
        aria-label={`What is ${entry.title}?`}
        aria-expanded={open}
        onClick={e => { e.stopPropagation(); setOpen(o => !o) }}
        className="flex items-center justify-center w-3.5 h-3.5 rounded-full border border-zinc-600 text-zinc-500 text-[9px] leading-none font-semibold hover:border-indigo-400 hover:text-indigo-400 focus-visible:outline focus-visible:outline-1 focus-visible:outline-indigo-400 transition-colors select-none"
      >
        ?
      </button>
      {open && (
        <span
          role="tooltip"
          className={`absolute top-5 z-50 w-60 rounded-lg border border-zinc-700 bg-zinc-950 p-3 shadow-2xl text-left normal-case tracking-normal whitespace-normal ${align === 'right' ? 'right-0' : 'left-0'}`}
        >
          <span className="block text-[11px] font-semibold text-zinc-100 mb-1">{entry.title}</span>
          <span className="block text-[11px] leading-relaxed text-zinc-400 font-normal font-sans">{entry.body}</span>
        </span>
      )}
    </span>
  )
}
