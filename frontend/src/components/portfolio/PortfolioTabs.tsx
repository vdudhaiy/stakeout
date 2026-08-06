import { Pencil, Plus, Trash2 } from 'lucide-react'
import { motion } from 'motion/react'
import clsx from 'clsx'

import type { PortfolioStats } from '../../types'
import { layoutSpring } from '../../lib/motion'

/**
 * Switches between the portfolios of the current market, in creation order.
 *
 * Hidden entirely when there's only one — a lone tab is noise, and it keeps
 * the page identical to what single-portfolio users (and guests, who can't
 * have more) have always seen. The "New portfolio" button stays visible so
 * the feature is still discoverable from one portfolio.
 *
 * Mirrors the market switcher's sliding-pill idiom, with its own layoutId so
 * the two pills never animate into each other.
 */
export function PortfolioTabs({
  portfolios, activeId, onSelect, onCreate, onRename, onDelete, disabledReason,
}: {
  portfolios: PortfolioStats[]
  activeId: number | null
  onSelect: (id: number) => void
  onCreate: () => void
  onRename: (p: PortfolioStats) => void
  onDelete: (p: PortfolioStats) => void
  /** When set, creating is unavailable (guest mode) and this explains why. */
  disabledReason?: string
}) {
  const active = portfolios.find(p => p.id === activeId)
  const canDelete = portfolios.length > 1

  return (
    <div className="flex flex-wrap items-center gap-2">
      {portfolios.length > 1 && (
        <div className="flex flex-wrap rounded-lg overflow-hidden border border-zinc-800">
          {portfolios.map(p => (
            <button
              key={p.id}
              onClick={() => onSelect(p.id)}
              title={p.name}
              className={clsx(
                'relative px-3.5 py-2 text-xs font-medium transition-colors whitespace-nowrap max-w-[12rem] truncate',
                p.id === activeId ? 'text-white' : 'text-zinc-400 hover:bg-zinc-900 hover:text-zinc-200',
              )}
            >
              {p.id === activeId && (
                <motion.span
                  layoutId="portfolio-tab-pill"
                  transition={layoutSpring}
                  className="absolute inset-0 bg-zinc-700 -z-10"
                />
              )}
              {p.name}
            </button>
          ))}
        </div>
      )}

      <button
        onClick={onCreate}
        disabled={!!disabledReason}
        title={disabledReason ?? 'Create a new portfolio in this market'}
        className="tap-target flex items-center gap-1 px-2.5 py-2 text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-900 border border-zinc-800 rounded-lg transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        <Plus size={13} />
        New portfolio
      </button>

      {active && (
        <>
          <button
            onClick={() => onRename(active)}
            title={`Rename "${active.name}"`}
            aria-label={`Rename ${active.name}`}
            className="tap-target p-2 text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 rounded-lg transition-colors"
          >
            <Pencil size={13} />
          </button>
          <button
            onClick={() => onDelete(active)}
            disabled={!canDelete}
            title={canDelete
              ? `Delete "${active.name}"`
              : 'This is your only portfolio in this market — create another one first'}
            aria-label={`Delete ${active.name}`}
            className="tap-target p-2 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:text-zinc-500 disabled:hover:bg-transparent"
          >
            <Trash2 size={13} />
          </button>
        </>
      )}
    </div>
  )
}
