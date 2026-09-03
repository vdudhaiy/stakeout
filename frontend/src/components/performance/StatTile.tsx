import clsx from 'clsx'
import { motion } from 'motion/react'
import { InfoTip } from '../InfoTip'
import type { GlossaryKey } from '../../utils/glossary'

interface Props {
  label: string
  value: string
  /** Sub-line under the value — a comparison, a date, a caveat. */
  detail?: string
  /** Colours the value. Omit for a neutral figure that isn't good or bad. */
  tone?: 'positive' | 'negative' | 'neutral'
  glossary?: GlossaryKey
  /** Staggers the entrance so a row of tiles arrives in sequence. */
  index?: number
  emphasis?: boolean
}

/**
 * One figure on the Performance page.
 *
 * `tone` is passed in rather than derived from the sign of the value: not
 * every negative number is bad news (drawdown and volatility are simply
 * facts), and colouring them red would tell the user something untrue.
 */
export function StatTile({ label, value, detail, tone = 'neutral', glossary, index = 0, emphasis }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ delay: Math.min(index * 0.04, 0.3), duration: 0.28, ease: 'easeOut' }}
      className={clsx(
        'rounded-xl border p-3 sm:p-4 min-w-0',
        emphasis
          ? 'border-indigo-500/30 bg-indigo-500/5'
          : 'border-zinc-800 bg-zinc-900',
      )}
    >
      {/* Label and detail wrap rather than truncate: at two tiles across on a
          phone, "MONEY-WEIGHTED R…" and "same money, same days, …" lose the
          only thing that made them worth reading. */}
      <p className="flex items-start gap-1 text-[0.625rem] tracking-widest text-zinc-500 font-medium">
        <span>{label.toUpperCase()}</span>
        {glossary && <span className="shrink-0"><InfoTip k={glossary} /></span>}
      </p>
      <p className={clsx(
        'mt-1.5 font-mono tabular-nums truncate',
        emphasis ? 'text-xl sm:text-2xl' : 'text-base sm:text-lg',
        tone === 'positive' && 'text-emerald-400',
        tone === 'negative' && 'text-red-400',
        tone === 'neutral' && 'text-zinc-100',
      )}>
        {value}
      </p>
      {detail && <p className="mt-1 text-[0.6875rem] text-zinc-500 leading-snug">{detail}</p>}
    </motion.div>
  )
}
