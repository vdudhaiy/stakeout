/**
 * Currency formatting.
 *
 * Every monetary value from the API is in the asset's NATIVE currency
 * (USD for US stocks, INR for Indian stocks) and is always displayed in
 * that same currency — there is no display-currency conversion. INR
 * amounts use Indian digit grouping (1,00,000).
 */

export type Currency = 'USD' | 'INR'

export const CURRENCY_SYMBOL: Record<Currency, string> = { USD: '$', INR: '₹' }

const fmtCache = new Map<string, Intl.NumberFormat>()

function formatter(currency: Currency, compact = false): Intl.NumberFormat {
  const key = `${currency}:${compact}`
  let f = fmtCache.get(key)
  if (!f) {
    f = new Intl.NumberFormat(currency === 'INR' ? 'en-IN' : 'en-US', {
      style: 'currency',
      currency,
      notation: compact ? 'compact' : 'standard',
      minimumFractionDigits: compact ? 0 : 2,
      maximumFractionDigits: 2,
    })
    fmtCache.set(key, f)
  }
  return f
}

/** Format `value` in its native currency. */
export function formatMoney(
  value: number | null | undefined,
  native: Currency,
  opts: { compact?: boolean; sign?: boolean } = {},
): string {
  if (value == null || Number.isNaN(value)) return '—'
  const text = formatter(native, opts.compact).format(Math.abs(value))
  const sign = opts.sign ? (value >= 0 ? '+' : '−') : value < 0 ? '−' : ''
  return `${sign}${text}`
}
