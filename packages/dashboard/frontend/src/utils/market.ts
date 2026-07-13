import type { Market } from '../types'

/** Classify a ticker by its Yahoo Finance suffix: .NS / .BO → India, else US. */
export function marketOf(ticker: string): Market {
  const t = ticker.toUpperCase()
  return t.endsWith('.NS') || t.endsWith('.BO') ? 'IN' : 'US'
}
