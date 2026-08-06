import clsx from 'clsx'
import { Layers } from 'lucide-react'

import type { PortfolioResponse } from '../../types'
import type { GlossaryKey } from '../../utils/glossary'
import { InfoTip } from '../InfoTip'

type MoneyFmt = (v: number | null | undefined, opts?: { sign?: boolean; compact?: boolean }) => string

const fmtPct = (n: number) => `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`
const gainText = (n: number) => n >= 0 ? 'text-emerald-400' : 'text-red-400'

/**
 * Totals across every portfolio in the current market.
 *
 * Rendered above the tabs, and only when the market has more than one
 * portfolio — with a single one it would just repeat that portfolio's own
 * stats row directly below it.
 *
 * Deliberately flatter and denser than the per-portfolio StatCard row: this
 * is context for the numbers below, not the primary reading.
 */
export function CombinedStatsBar({
  portfolio, money, count,
}: {
  portfolio: PortfolioResponse
  money: MoneyFmt
  count: number
}) {
  const netPl = portfolio.net_profit_loss
  const totalRet = portfolio.total_return

  const cells: { label: string; value: string; sub?: string; color?: string; tip?: GlossaryKey }[] = [
    { label: 'VALUE', value: money(portfolio.portfolio_value), tip: 'portfolio_value' },
    { label: 'COST BASIS', value: money(portfolio.total_invested), tip: 'total_invested' },
    {
      label: 'UNREALIZED', value: money(totalRet, { sign: true }),
      sub: fmtPct(portfolio.return_percentage), color: gainText(totalRet), tip: 'total_return',
    },
    {
      label: 'REALIZED', value: money(portfolio.realized_gains),
      color: portfolio.realized_gains > 0 ? gainText(1) : undefined, tip: 'realized_gains',
    },
    {
      label: 'DIVIDENDS', value: money(portfolio.total_dividends),
      color: portfolio.total_dividends > 0 ? gainText(1) : undefined, tip: 'dividends',
    },
    { label: 'NET P&L', value: money(netPl, { sign: true }), color: gainText(netPl), tip: 'net_pl' },
  ]

  return (
    <div className="rounded-xl border border-indigo-500/20 bg-indigo-500/[0.04] px-4 py-3">
      <div className="flex items-center gap-1.5 mb-2.5">
        <Layers size={12} className="text-indigo-400" />
        <span className="text-[0.625rem] font-semibold tracking-widest text-indigo-300">
          ALL {count} PORTFOLIOS
        </span>
      </div>
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-x-4 gap-y-3">
        {cells.map(c => (
          <div key={c.label} className="flex flex-col gap-0.5 min-w-0">
            <span className="flex items-center gap-1 text-[0.5625rem] font-semibold tracking-widest text-zinc-500">
              {c.label}{c.tip && <InfoTip k={c.tip} />}
            </span>
            <span className={clsx('text-sm font-bold font-mono leading-none truncate', c.color ?? 'text-zinc-200')}>
              {c.value}
            </span>
            {c.sub && <span className={clsx('text-[0.625rem] font-mono', c.color ?? 'text-zinc-500')}>{c.sub}</span>}
          </div>
        ))}
      </div>
    </div>
  )
}
