/**
 * Minimal, unauthenticated fetch helpers for guest mode.
 *
 * Guests never touch the DB-backed /watchlist or /portfolio endpoints (those
 * require a real Supabase session). But the on-disk price archive behind
 * /stocks/* is shared, public reference data — anyone can fetch a ticker
 * into it or read its current price, guest or not. These two calls are the
 * only backend interaction guestPortfolio/guestWatchlist need, kept separate
 * from api/index.ts to avoid a circular import (that module imports the
 * guest engines to route into them).
 */
import { applyExchange, type Exchange } from '../utils/market'

const API_BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '')

/** Ensures `ticker` is cached in the shared archive and returns a display name.
 * Throws if the ticker doesn't exist on Yahoo Finance. */
export async function resolveTickerName(ticker: string): Promise<string> {
  const addRes = await fetch(`${API_BASE}/stocks/${encodeURIComponent(ticker)}`, { method: 'POST' })
  if (!addRes.ok) {
    const err = await addRes.json().catch(() => ({ detail: 'Request failed' }))
    throw new Error(err.detail ?? `Ticker '${ticker}' could not be found.`)
  }
  const detailsRes = await fetch(`${API_BASE}/stocks/${encodeURIComponent(ticker)}/details`)
  if (detailsRes.ok) {
    const details = await detailsRes.json()
    const info = details?.info as Record<string, unknown> | undefined
    const name = (info?.displayName as string) || (info?.shortName as string)
    if (name) return name
  }
  return ticker
}

/** Current price for `ticker`, or null if unavailable — never a fabricated 0
 * (mirrors the backend's own Optional[Decimal] price handling; see
 * portfolio_service._current_price). */
export async function fetchGuestPrice(ticker: string): Promise<number | null> {
  try {
    const res = await fetch(`${API_BASE}/stocks/${encodeURIComponent(ticker)}/current`)
    if (!res.ok) return null
    const data = await res.json()
    return data?.data?.[0]?.close ?? null
  } catch {
    return null
  }
}

/** Resolves a bare ticker + exchange choice to the canonical suffixed
 * ticker to use in guest mode, mirroring portfolio_service._resolve_ticker
 * (and watchlist.py's own copy of the same logic) since guest mode has no
 * server-side session to do this for it.
 *
 * "US" and an already-suffixed ticker pass through applyExchange unchanged.
 * A bare Indian ticker is ambiguous — the user no longer picks NSE vs BSE —
 * so this reuses whichever suffix `hasExisting` already recognizes (so
 * "buy more"/re-adding doesn't fork into a second holding/watchlist entry),
 * otherwise probes NSE then BSE via resolveTickerName and keeps whichever
 * one actually exists. Throws if the ticker exists on neither exchange. */
export async function resolveGuestTicker(
  ticker: string, exchange: Exchange | undefined, hasExisting: (t: string) => boolean,
): Promise<string> {
  const t = ticker.trim().toUpperCase()
  if (exchange !== 'IN' || t.endsWith('.NS') || t.endsWith('.BO')) {
    return applyExchange(t, exchange ?? 'US')
  }

  for (const suffix of ['.NS', '.BO'] as const) {
    if (hasExisting(`${t}${suffix}`)) return `${t}${suffix}`
  }

  let lastError: unknown
  for (const suffix of ['.NS', '.BO'] as const) {
    try {
      await resolveTickerName(`${t}${suffix}`)
      return `${t}${suffix}`
    } catch (e) {
      lastError = e
    }
  }
  throw lastError instanceof Error
    ? new Error(`Ticker '${t}' could not be found on NSE or BSE. Please check the symbol and try again.`)
    : lastError
}
