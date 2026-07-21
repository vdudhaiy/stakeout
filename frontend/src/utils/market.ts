import type { Market } from '../types'
import type { Currency } from './currency'

/** Classify a ticker by its Yahoo Finance suffix: .NS / .BO → India, else US. */
export function marketOf(ticker: string): Market {
  const t = ticker.toUpperCase()
  return t.endsWith('.NS') || t.endsWith('.BO') ? 'IN' : 'US'
}

/** Exchange the user picks in the "add ticker" UI — drives which suffix gets appended. */
export type Exchange = 'US' | 'NSE' | 'BSE'

export const EXCHANGES: Array<{ value: Exchange; label: string; market: Market }> = [
  { value: 'US',  label: 'US · NYSE/NASDAQ', market: 'US' },
  { value: 'NSE', label: 'India · NSE',      market: 'IN' },
  { value: 'BSE', label: 'India · BSE',      market: 'IN' },
]

const EXCHANGE_SUFFIX: Record<Exchange, string> = { US: '', NSE: '.NS', BSE: '.BO' }

/** Append the Yahoo Finance suffix for `exchange` to a bare ticker (idempotent). */
export function applyExchange(ticker: string, exchange: Exchange): string {
  const t = ticker.trim().toUpperCase()
  const suffix = EXCHANGE_SUFFIX[exchange]
  if (!suffix || t.endsWith(suffix) || t.endsWith('.NS') || t.endsWith('.BO')) return t
  return `${t}${suffix}`
}

/** Native currency traded on `exchange`. */
export function currencyOfExchange(exchange: Exchange): Currency {
  return EXCHANGES.find(e => e.value === exchange)?.market === 'IN' ? 'INR' : 'USD'
}
