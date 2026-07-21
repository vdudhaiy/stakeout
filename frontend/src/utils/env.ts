/** Reads a VITE_* env var as a positive millisecond duration, falling back
 * to `fallbackMs` if it's unset, non-numeric, or <= 0.
 */
export function envMs(key: string, fallbackMs: number): number {
  const raw = (import.meta.env as Record<string, string | undefined>)[key]
  const parsed = raw ? Number(raw) : NaN
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallbackMs
}

/** Formats a millisecond duration for display, e.g. "30 s", "5 min", "1 hr". */
export function formatInterval(ms: number): string {
  if (ms % (60 * 60_000) === 0) {
    const hrs = ms / (60 * 60_000)
    return `${hrs} hr${hrs !== 1 ? 's' : ''}`
  }
  if (ms % 60_000 === 0) {
    return `${ms / 60_000} min`
  }
  return `${Math.round(ms / 1000)} s`
}

// Polling cadences — single source of truth, overridable per deployment via
// .env (see .env.example). Both the pollers and any UI copy referencing
// "every N" should import these rather than hardcoding the value.
export const HEALTH_REFRESH_MS = envMs('VITE_HEALTH_REFRESH_MS', 30_000)
export const MARKET_STATUS_REFRESH_MS = envMs('VITE_MARKET_STATUS_REFRESH_MS', 5 * 60_000)
export const PRICE_REFRESH_MS = envMs('VITE_PRICE_REFRESH_MS', 2 * 60_000)
export const PORTFOLIO_REFRESH_MS = envMs('VITE_PORTFOLIO_REFRESH_MS', 2 * 60_000)
export const TICKER_TAPE_REFRESH_MS = envMs('VITE_TICKER_TAPE_REFRESH_MS', 5 * 60_000)
