/**
 * Returns the number of milliseconds by which `timeZone` lags UTC at the
 * current moment, accounting for DST where applicable.
 *
 * e.g. America/New_York during EDT (UTC-4): returns 4 * 3_600_000
 * e.g. America/New_York during EST (UTC-5): returns 5 * 3_600_000
 * e.g. Asia/Kolkata (UTC+5:30, no DST): returns -5.5 * 3_600_000
 *
 * Usage: utcMs = (zoned_instant_parsed_as_UTC).getTime() + getTzOffsetMs(timeZone)
 */
function getTzOffsetMs(timeZone: string): number {
  const now = new Date()
  const p: Record<string, number> = {}
  for (const { type, value } of new Intl.DateTimeFormat('en-US', {
    timeZone,
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
  return new Date(new Date(etDateStr + ':00Z').getTime() + getTzOffsetMs('America/New_York'))
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
 * Convert a fixed "HH:MM" time in `timeZone` to the user's local "HH:MM",
 * using today's date for DST accuracy.
 */
function zonedToLocalHHMM(hhmm: string, timeZone: string): string {
  const today = new Date().toISOString().slice(0, 10)
  return fmtHHMM(new Date(new Date(`${today}T${hhmm}:00Z`).getTime() + getTzOffsetMs(timeZone)))
}

/** Convert a fixed ET "HH:MM" time (e.g. "09:30") to the user's local "HH:MM". */
export function etToLocalHHMM(etHHMM: string): string {
  return zonedToLocalHHMM(etHHMM, 'America/New_York')
}

/** Convert a fixed IST "HH:MM" time (e.g. "09:15") to the user's local "HH:MM". */
export function istToLocalHHMM(istHHMM: string): string {
  return zonedToLocalHHMM(istHHMM, 'Asia/Kolkata')
}

/** Returns the user's local timezone abbreviation (e.g. "SGT", "GMT+5:30"). */
export function localTzAbbr(): string {
  return (
    new Intl.DateTimeFormat('en-US', { timeZoneName: 'short' })
      .formatToParts(new Date())
      .find(p => p.type === 'timeZoneName')?.value ?? ''
  )
}

/** Format an ET calendar date string ("YYYY-MM-DD") as "Mon D, YYYY" in ET. */
export function formatEtDate(etDateStr: string): string {
  const d = parseEtDateStr(`${etDateStr}T12:00`)
  return new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    month: 'short', day: 'numeric', year: 'numeric',
  }).format(d)
}

/** Format an ET calendar date string ("YYYY-MM-DD") as "Mon D, YYYY" in the user's local timezone. */
export function formatLocalDate(etDateStr: string): string {
  const d = parseEtDateStr(`${etDateStr}T12:00`)
  return new Intl.DateTimeFormat('en-US', {
    month: 'short', day: 'numeric', year: 'numeric',
  }).format(d)
}
