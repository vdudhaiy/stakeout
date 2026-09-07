/**
 * Where the data on screen actually came from, as reported by the backend.
 *
 * Every timestamp here is the server's, read off the response headers that
 * `freshness.py` attaches. The browser deliberately does not date anything
 * itself: a client clock records when the response *arrived*, which for
 * anything served from one of the app's cache layers is a different and much
 * more flattering number than when the data was pulled. It also cannot tell a
 * fresh answer from a week-old fallback, because both arrive as a normal 200.
 *
 * The store is keyed by request path and read by pathname, so a panel can ask
 * about `/stocks/AAPL` without knowing which query string the fetch used.
 */

import { useSyncExternalStore } from 'react'

export type DataSource = 'live' | 'cached' | 'archive' | 'stale'

export interface DataFreshness {
  source: DataSource
  /** When the backend pulled this from upstream. Null when unknowable. */
  fetchedAt: Date | null
  /** Newest data point in the payload (ISO date), for series like the chart. */
  dataThrough: string | null
  /** Server-computed age at response time, in seconds. */
  ageSeconds: number | null
  /** Client receipt time — used only to order entries, never displayed. */
  receivedAt: number
}

const store = new Map<string, DataFreshness>()
const listeners = new Set<() => void>()

// useSyncExternalStore compares snapshots by identity, so a mutable Map would
// never look changed. Bumping a counter on every write is the cheap way to
// give it something stable to diff.
let version = 0

function emit() {
  version += 1
  listeners.forEach(fn => fn())
}

/** Record what the backend said about a response. Called for every request. */
export function recordFreshness(path: string, res: Response): void {
  const source = res.headers.get('X-Data-Source') as DataSource | null
  // Absent on responses with nothing upstream behind them (/health, errors,
  // guest-mode short-circuits). Nothing to claim, so nothing is stored.
  if (!source) return

  const fetchedAtRaw = res.headers.get('X-Data-Fetched-At')
  const age = res.headers.get('X-Data-Age-Seconds')
  const parsed = fetchedAtRaw ? new Date(fetchedAtRaw) : null

  store.set(path, {
    source,
    fetchedAt: parsed && !Number.isNaN(parsed.getTime()) ? parsed : null,
    dataThrough: res.headers.get('X-Data-Through'),
    ageSeconds: age !== null ? Number(age) : null,
    receivedAt: Date.now(),
  })
  emit()
}

function pathnameOf(path: string): string {
  const q = path.indexOf('?')
  return q === -1 ? path : path.slice(0, q)
}

/**
 * Freshness for `key`, matching on the path and ignoring the query string.
 *
 * Two-step on purpose. An exact pathname match wins, so `/portfolio/` reports
 * the portfolio fetch rather than whichever `/portfolio/{ticker}/dividends`
 * call happened to land most recently. Only when nothing matches exactly does
 * it fall back to the newest entry under the prefix, which is what lets a
 * caller name a resource whose real path it doesn't assemble itself.
 */
export function readFreshness(key: string): DataFreshness | null {
  let exact: DataFreshness | null = null
  let prefixed: DataFreshness | null = null

  for (const [path, entry] of store) {
    const pathname = pathnameOf(path)
    if (pathname === key) {
      if (!exact || entry.receivedAt > exact.receivedAt) exact = entry
    } else if (pathname.startsWith(key)) {
      if (!prefixed || entry.receivedAt > prefixed.receivedAt) prefixed = entry
    }
  }
  return exact ?? prefixed
}

function subscribe(fn: () => void): () => void {
  listeners.add(fn)
  return () => { listeners.delete(fn) }
}

/** Live-updating freshness for the response matching `key`. */
export function useDataFreshness(key: string | null | undefined): DataFreshness | null {
  const snapshot = useSyncExternalStore(
    subscribe,
    () => (key ? `${version}:${key}` : ''),
    () => '',
  )
  // The subscription value is only a change token; the read happens here so
  // the returned object is always the current one.
  void snapshot
  return key ? readFreshness(key) : null
}

/** Test/sign-out hook: forget everything recorded so far. */
export function clearFreshness(): void {
  store.clear()
  emit()
}

// ── Presentation ────────────────────────────────────────────────────────────

/** "just now", "6m ago", "3h ago", "2d ago". */
export function formatAge(from: Date, now: number = Date.now()): string {
  const seconds = Math.max(0, Math.round((now - from.getTime()) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.round(hours / 24)}d ago`
}

/** Exact server time, for the tooltip. Local timezone, seconds included. */
export function formatExact(at: Date): string {
  return at.toLocaleString(undefined, {
    year: 'numeric', month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

export const SOURCE_LABEL: Record<DataSource, string> = {
  live: 'Live',
  cached: 'Cached',
  archive: 'Archived',
  stale: 'Stale',
}

export const SOURCE_BLURB: Record<DataSource, string> = {
  live: 'Fetched from the data provider while loading this view.',
  cached: 'Served from the server cache. It was pulled from the provider at the time shown.',
  archive: 'Read from the stored price history rather than fetched live.',
  stale: 'A previous copy — the live fetch failed (usually a provider rate limit), so the last good data is shown instead.',
}
