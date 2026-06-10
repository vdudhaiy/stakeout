/**
 * Returns the number of milliseconds by which ET (America/New_York) lags UTC
 * at the current moment, accounting for DST.
 *
 * e.g. during EDT (UTC-4): returns 4 * 3_600_000
 * e.g. during EST (UTC-5): returns 5 * 3_600_000
 *
 * Usage: utcMs = (ET_instant_parsed_as_UTC).getTime() + getEtOffsetMs()
 */
function getEtOffsetMs(): number {
  const now = new Date()
  const p: Record<string, number> = {}
  for (const { type, value } of new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    year: 'numeric', month: 'numeric', day: 'numeric',
    hour: 'numeric', minute: 'numeric', second: 'numeric',
    hour12: false,
  }).formatToParts(now)) {
    if (type !== 'literal') p[type] = parseInt(value, 10)
  }
  return (
    now.getTime() -
    Date.UTC(p.year, p.month - 1, p.day, p.hour === 24 ? 0 : p.hour, p.minute, p.second)
  )
}

/**
 * Parse a backend ET datetime string ("YYYY-MM-DDTHH:MM") into a real UTC Date.
 * The backend produces these strings via pandas strftime on an ET-tz-aware index.
 */
export function parseEtDateStr(etDateStr: string): Date {
  return new Date(new Date(etDateStr + ':00Z').getTime() + getEtOffsetMs())
}

/** Format a Date as "HH:MM" in the user's local timezone (zero-padded 24 h). */
function fmtHHMM(date: Date): string {
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).format(date)
}

/** Format a Date as "HH:MM TZ" in the user's local timezone. */
export function fmtHHMMWithTz(date: Date): string {
  const time = fmtHHMM(date)
  const tz =
    new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' })
      .formatToParts(date)
      .find(p => p.type === 'timeZoneName')?.value ?? ''
  return tz ? `${time} ${tz}` : time
}

/**
 * Convert a fixed ET "HH:MM" time (e.g. "09:30") to the user's local "HH:MM",
 * using today's date for DST accuracy.
 */
export function etToLocalHHMM(etHHMM: string): string {
  const today = new Date().toISOString().slice(0, 10)
  return fmtHHMM(new Date(new Date(`${today}T${etHHMM}:00Z`).getTime() + getEtOffsetMs()))
}

/** Returns the user's local timezone abbreviation (e.g. "SGT", "GMT+5:30"). */
export function localTzAbbr(): string {
  return (
    new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' })
      .formatToParts(new Date())
      .find(p => p.type === 'timeZoneName')?.value ?? ''
  )
}
