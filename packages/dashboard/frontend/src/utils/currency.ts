/**
 * Currency conversion + formatting.
 *
 * All monetary values from the API are in the asset's NATIVE currency
 * (USD for US stocks, INR for Indian stocks). The display currency is a
 * user preference; conversion uses the daily USD/INR reference rate from
 * the /fx endpoint. INR amounts use Indian digit grouping (1,00,000).
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

/** Convert `value` from `from` currency to `to` using the USD→INR rate. */
export function convert(value: number, from: Currency, to: Currency, usdInr: number | null): number {
  if (from === to) return value
  if (usdInr == null || usdInr <= 0) return value // rate unavailable — show native
  return from === 'USD' ? value * usdInr : value / usdInr
}

/** Convert then format. Falls back to the native currency if no rate yet. */
export function formatMoney(
  value: number | null | undefined,
  native: Currency,
  display: Currency,
  usdInr: number | null,
  opts: { compact?: boolean; sign?: boolean } = {},
): string {
  if (value == null || Number.isNaN(value)) return '—'
  const canConvert = native === display || (usdInr != null && usdInr > 0)
  const ccy = canConvert ? display : native
  const converted = convert(value, native, ccy, usdInr)
  const text = formatter(ccy, opts.compact).format(Math.abs(converted))
  const sign = opts.sign ? (converted >= 0 ? '+' : '−') : converted < 0 ? '−' : ''
  return `${sign}${text}`
}
