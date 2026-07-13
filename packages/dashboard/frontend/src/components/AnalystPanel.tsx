import clsx from 'clsx'
import { InfoTip } from './InfoTip'
import type { GlossaryKey } from '../utils/glossary'
import type { RecommendationPeriod, EarningsEstimateRow, RevenueEstimateRow } from '../types'

type MoneyFmt = (v: number | null | undefined, opts?: { sign?: boolean }) => string

// ── Formatters ────────────────────────────────────────────────────────────────

function fmtPrice(n: number | null | undefined) {
  if (n == null) return '—'
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
}

function fmtBig(n: number | null | undefined) {
  if (n == null) return '—'
  const abs = Math.abs(n)
  if (abs >= 1e12) return `$${(n / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `$${(n / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `$${(n / 1e6).toFixed(2)}M`
  return `$${n.toFixed(0)}`
}

function fmtPct(n: number | null | undefined) {
  if (n == null) return '—'
  const pct = n * 100
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(1)}%`
}

function SectionLabel({ children, tip }: { children: React.ReactNode; tip?: GlossaryKey }) {
  return (
    <p className="flex items-center gap-1.5 text-[10px] text-zinc-500 tracking-widest font-medium">
      {children}
      {tip && <InfoTip k={tip} />}
    </p>
  )
}

function Unavailable() {
  return <p className="text-zinc-600 text-sm py-1">Not available</p>
}

// ── Shared estimates table ────────────────────────────────────────────────────

interface EstimatesTableProps {
  rows: Array<{
    period?: string | null
    avg?: number | null
    low?: number | null
    high?: number | null
    growth?: number | null
  }>
  fmtValue: (n: number | null | undefined) => string
  valueLabel: string
}

function EstimatesTable({ rows, fmtValue, valueLabel }: EstimatesTableProps) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs border-collapse">
        <thead>
          <tr>
            {['PERIOD', valueLabel, 'LOW', 'HIGH', 'GROWTH'].map(h => (
              <th
                key={h}
                className={clsx(
                  'pb-2 text-[10px] text-zinc-600 font-medium tracking-wider',
                  h === 'PERIOD' ? 'text-left' : 'text-right',
                )}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-800/50">
          {rows.map((row, i) => (
            <tr key={i}>
              <td className="py-2 font-mono text-zinc-400">{row.period ?? `Row ${i + 1}`}</td>
              <td className="py-2 text-right font-mono text-zinc-200">{fmtValue(row.avg)}</td>
              <td className="py-2 text-right font-mono text-zinc-500">{fmtValue(row.low)}</td>
              <td className="py-2 text-right font-mono text-zinc-500">{fmtValue(row.high)}</td>
              <td
                className={clsx(
                  'py-2 text-right font-mono font-medium',
                  row.growth == null
                    ? 'text-zinc-600'
                    : row.growth >= 0
                      ? 'text-emerald-400'
                      : 'text-red-400',
                )}
              >
                {fmtPct(row.growth)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

// ── Price Targets ─────────────────────────────────────────────────────────────

interface PriceTargetsProps {
  targets: Record<string, number | null> | null | undefined
  currentPrice?: number
  format?: MoneyFmt
}

function PriceTargetsCard({ targets, currentPrice, format }: PriceTargetsProps) {
  const money = format ?? fmtPrice
  const low = targets?.low ?? null
  const high = targets?.high ?? null
  const mean = targets?.mean ?? null
  const median = targets?.median ?? null
  const current = targets?.current ?? currentPrice ?? null

  const hasRange = low != null && high != null && high > low
  const toPct = (v: number) =>
    Math.max(2, Math.min(98, ((v - low!) / (high! - low!)) * 100))

  const upside =
    current != null && mean != null
      ? (((mean - current) / current) * 100).toFixed(1)
      : null

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <SectionLabel tip="price_target">ANALYST PRICE TARGETS</SectionLabel>

      {!hasRange ? (
        <Unavailable />
      ) : (
        <>
          <div className="space-y-3">
            <div className="relative h-1.5 bg-zinc-800 rounded-full">
              {mean != null && (
                <div
                  className="absolute h-full bg-indigo-500/25 rounded-full"
                  style={{ left: 0, width: `${toPct(mean)}%` }}
                />
              )}
              {current != null && (
                <div
                  className="absolute w-px h-3.5 bg-zinc-300 rounded-full -top-1"
                  style={{ left: `${toPct(current)}%` }}
                  title={`Current: ${money(current)}`}
                />
              )}
              {mean != null && (
                <div
                  className="absolute w-2.5 h-2.5 bg-indigo-500 rounded-full border-2 border-zinc-900 top-1/2 -translate-y-1/2 -translate-x-1/2"
                  style={{ left: `${toPct(mean)}%` }}
                  title={`Mean: ${money(mean)}`}
                />
              )}
              {median != null && (
                <div
                  className="absolute w-2 h-2 bg-violet-400 rounded-full border-2 border-zinc-900 top-1/2 -translate-y-1/2 -translate-x-1/2"
                  style={{ left: `${toPct(median)}%` }}
                  title={`Median: ${money(median)}`}
                />
              )}
            </div>
            <div className="flex justify-between text-[10px] font-mono text-zinc-500">
              <span>Low {fmtPrice(low)}</span>
              <span>High {fmtPrice(high)}</span>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            {[
              { label: 'Current', value: money(current) },
              { label: 'Mean Target', value: money(mean) },
              { label: 'Median Target', value: money(median) },
              {
                label: 'Upside (mean)',
                value: upside != null ? `${Number(upside) >= 0 ? '+' : ''}${upside}%` : '—',
                colored: upside != null ? Number(upside) >= 0 : null,
              },
            ].map(({ label, value, colored }) => (
              <div key={label} className="space-y-0.5">
                <p className="text-[10px] text-zinc-600">{label}</p>
                <p
                  className={clsx(
                    'text-sm font-mono font-medium',
                    colored === true
                      ? 'text-emerald-400'
                      : colored === false
                        ? 'text-red-400'
                        : 'text-zinc-200',
                  )}
                >
                  {value}
                </p>
              </div>
            ))}
          </div>

          <div className="flex items-center gap-4 text-[10px] text-zinc-500">
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-px h-3 bg-zinc-300" /> Current
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-indigo-500" /> Mean
            </span>
            <span className="flex items-center gap-1.5">
              <span className="inline-block w-2 h-2 rounded-full bg-violet-400" /> Median
            </span>
          </div>
        </>
      )}
    </div>
  )
}

// ── Recommendations ───────────────────────────────────────────────────────────

interface RecommendationsProps {
  recommendations: RecommendationPeriod[] | null | undefined
}

function RecommendationsCard({ recommendations }: RecommendationsProps) {
  const rows = (recommendations ?? [])
    .map(r => ({
      period: r.period,
      strongBuy: r.strong_buy ?? r.strongBuy ?? 0,
      buy: r.buy ?? 0,
      hold: r.hold ?? 0,
      sell: r.sell ?? 0,
      strongSell: r.strong_sell ?? r.strongSell ?? 0,
    }))
    .map(r => ({ ...r, total: r.strongBuy + r.buy + r.hold + r.sell + r.strongSell }))
    .filter(r => r.total > 0)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <SectionLabel tip="recommendations">ANALYST RECOMMENDATIONS</SectionLabel>

      {rows.length === 0 ? (
        <Unavailable />
      ) : (
        <>
          <div className="space-y-3.5">
            {rows.slice(0, 4).map((r, i) => (
              <div key={i} className="space-y-1.5">
                <div className="flex justify-between items-center text-xs">
                  <span className="font-mono text-zinc-400">{r.period ?? `Period ${i + 1}`}</span>
                  <span className="text-zinc-600 text-[10px]">{r.total} analysts</span>
                </div>
                <div className="flex h-2 rounded-full overflow-hidden gap-px">
                  {r.strongBuy > 0 && <div style={{ flex: r.strongBuy }} className="bg-emerald-500" title={`Strong Buy: ${r.strongBuy}`} />}
                  {r.buy > 0 && <div style={{ flex: r.buy }} className="bg-emerald-400/60" title={`Buy: ${r.buy}`} />}
                  {r.hold > 0 && <div style={{ flex: r.hold }} className="bg-zinc-500" title={`Hold: ${r.hold}`} />}
                  {r.sell > 0 && <div style={{ flex: r.sell }} className="bg-red-400/60" title={`Sell: ${r.sell}`} />}
                  {r.strongSell > 0 && <div style={{ flex: r.strongSell }} className="bg-red-500" title={`Strong Sell: ${r.strongSell}`} />}
                </div>
                <div className="flex justify-between text-[10px] font-mono text-zinc-600">
                  <span className="text-emerald-600">Buy {r.strongBuy + r.buy}</span>
                  <span>Hold {r.hold}</span>
                  <span className="text-red-600">Sell {r.sell + r.strongSell}</span>
                </div>
              </div>
            ))}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 pt-1">
            {[
              { color: 'bg-emerald-500', label: 'Strong Buy' },
              { color: 'bg-emerald-400/60', label: 'Buy' },
              { color: 'bg-zinc-500', label: 'Hold' },
              { color: 'bg-red-400/60', label: 'Sell' },
              { color: 'bg-red-500', label: 'Strong Sell' },
            ].map(({ color, label }) => (
              <span key={label} className="flex items-center gap-1 text-[10px] text-zinc-500">
                <span className={`inline-block w-2 h-2 rounded-sm ${color}`} />
                {label}
              </span>
            ))}
          </div>
        </>
      )}
    </div>
  )
}

// ── Earnings Estimates ────────────────────────────────────────────────────────

interface EarningsEstimatesProps {
  estimates: EarningsEstimateRow[] | null | undefined
}

function EarningsEstimatesCard({ estimates }: EarningsEstimatesProps) {
  const rows = (estimates ?? []).filter(r => r.avg != null)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <SectionLabel tip="eps_estimate">EARNINGS ESTIMATES (EPS)</SectionLabel>

      {rows.length === 0 ? (
        <Unavailable />
      ) : (
        <EstimatesTable
          rows={rows}
          fmtValue={fmtPrice}
          valueLabel="AVG EPS"
        />
      )}
    </div>
  )
}

// ── Revenue Estimates ─────────────────────────────────────────────────────────

interface RevenueEstimatesProps {
  estimates: RevenueEstimateRow[] | null | undefined
}

function RevenueEstimatesCard({ estimates }: RevenueEstimatesProps) {
  const rows = (estimates ?? []).filter(r => r.avg != null)

  return (
    <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-5 space-y-4">
      <SectionLabel tip="revenue_estimate">REVENUE ESTIMATES</SectionLabel>

      {rows.length === 0 ? (
        <Unavailable />
      ) : (
        <EstimatesTable
          rows={rows}
          fmtValue={fmtBig}
          valueLabel="AVG"
        />
      )}
    </div>
  )
}

// ── Composed panel ────────────────────────────────────────────────────────────

interface Props {
  targets: Record<string, number | null> | null | undefined
  recommendations: RecommendationPeriod[] | null | undefined
  earningsEstimates: EarningsEstimateRow[] | null | undefined
  revenueEstimates: RevenueEstimateRow[] | null | undefined
  currentPrice?: number
  format?: MoneyFmt
}

export function AnalystPanel({
  targets,
  recommendations,
  earningsEstimates,
  revenueEstimates,
  currentPrice,
  format,
}: Props) {
  return (
    <div className="shrink-0 grid grid-cols-1 md:grid-cols-2 gap-4">
      <EarningsEstimatesCard estimates={earningsEstimates} />
      <RevenueEstimatesCard estimates={revenueEstimates} />
      <PriceTargetsCard targets={targets} currentPrice={currentPrice} format={format} />
      <RecommendationsCard recommendations={recommendations} />
    </div>
  )
}
