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
