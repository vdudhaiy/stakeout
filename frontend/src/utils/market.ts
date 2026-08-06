import type { Market } from '../types'
import type { Currency } from './currency'

/** Classify a ticker by its Yahoo Finance suffix: .NS / .BO → India, else US. */
export function marketOf(ticker: string): Market {
  const t = ticker.toUpperCase()
  return t.endsWith('.NS') || t.endsWith('.BO') ? 'IN' : 'US'
}

/** Strip the .NS/.BO Yahoo Finance suffix for display — call sites that need
 * the full ticker for API calls or lookups should keep using the raw value. */
export function displayTicker(ticker: string): string {
  return ticker.replace(/\.(NS|BO)$/i, '')
}

/** Exchange the user picks in the "add ticker" UI. NSE and BSE aren't a
 * separate choice — India is one option that resolves to NSE by default and
 * falls back to BSE server-side if NSE doesn't have the ticker. */
export type Exchange = 'US' | 'IN'

export const EXCHANGES: Array<{ value: Exchange; label: string; market: Market }> = [
  { value: 'US', label: 'US · NYSE/NASDAQ', market: 'US' },
  { value: 'IN', label: 'India · NSE/BSE',  market: 'IN' },
]

const EXCHANGE_SUFFIX: Record<Exchange, string> = { US: '', IN: '.NS' }

/** Append the Yahoo Finance suffix for `exchange` to a bare ticker
 * (idempotent). For "IN" this only ever produces the NSE suffix — it has no
 * way to know whether the ticker actually exists on NSE, let alone BSE.
 * Callers that need the NSE-then-BSE fallback for a brand-new Indian ticker
 * should resolve that themselves (see guestApi.resolveGuestTicker) and use
 * this only where the exchange is already unambiguous. */
export function applyExchange(ticker: string, exchange: Exchange): string {
  const t = ticker.trim().toUpperCase()
  if (t.endsWith('.NS') || t.endsWith('.BO')) return t
  const suffix = EXCHANGE_SUFFIX[exchange]
  return suffix ? `${t}${suffix}` : t
}

/** Native currency traded on `exchange`. */
export function currencyOfExchange(exchange: Exchange): Currency {
  return EXCHANGES.find(e => e.value === exchange)?.market === 'IN' ? 'INR' : 'USD'
}
