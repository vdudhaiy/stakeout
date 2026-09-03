const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

function utc(dateStr: string): Date {
  return new Date(dateStr + 'T00:00:00Z')
}

// Returns the first trading day of every `step` months, never including the
// very first data point (which may be mid-month and would look like a stray tick).
function firstTradingDayEveryNMonths(dates: string[], step: number): string[] {
  const result: string[] = []
  let lastShownKey = -1
  for (let i = 1; i < dates.length; i++) {
    const curr = utc(dates[i])
    const prev = utc(dates[i - 1])
    const newMonth =
      curr.getUTCMonth() !== prev.getUTCMonth() ||
      curr.getUTCFullYear() !== prev.getUTCFullYear()
    if (!newMonth) continue
    const key = curr.getUTCFullYear() * 12 + curr.getUTCMonth()
    const gap = lastShownKey < 0 ? step : key - lastShownKey
    if (gap >= step) {
      result.push(dates[i])
      lastShownKey = key
    }
  }
  return result
}

/**
 * Compute which date strings from `dates` should appear as X-axis ticks,
 * based on the currently selected day range.
 */
export function computeXTicks(dates: string[], days: number): string[] {
  if (dates.length === 0) return []

  let ticks: string[]

  if (days <= 14) {
    ticks = [...dates]
  } else if (days <= 30) {
    ticks = dates.filter((_, i) => i % 2 === 0)
  } else if (days <= 90) {
    ticks = dates.filter((_, i) => i % 5 === 0)
  } else if (days <= 180) {
    ticks = dates.filter((_, i) => i % 10 === 0)
  } else if (days <= 365) {
    ticks = firstTradingDayEveryNMonths(dates, 1)
  } else if (days <= 730) {
    ticks = firstTradingDayEveryNMonths(dates, 2)
  } else {
    ticks = firstTradingDayEveryNMonths(dates, 3)
  }

  // For index-based ranges, ensure the last data point is always labelled
  if (days <= 180) {
    const last = dates[dates.length - 1]
    if (ticks[ticks.length - 1] !== last) ticks = [...ticks, last]
  }

  return ticks
}

/** Format a date string for display on the X axis. */
export function xTickFormatter(dateStr: string, days: number): string {
  if (days > 365) {
    const d = utc(dateStr)
    return `${MONTHS[d.getUTCMonth()]} '${String(d.getUTCFullYear()).slice(2)}`
  }
  return dateStr.slice(5) // MM-DD
}

// Hour marks to show on intraday charts: market open + every whole hour until close
const INTRADAY_HOUR_MARKS = new Set(['09:30', '10:00', '11:00', '12:00', '13:00', '14:00', '15:00', '16:00'])

/** Return the subset of intraday date strings that fall on hourly tick marks. */
export function computeIntradayTicks(dates: string[]): string[] {
  return dates.filter(d => INTRADAY_HOUR_MARKS.has(d.slice(11, 16)))
}

/** Format an intraday datetime string ("YYYY-MM-DDTHH:MM") as "H:MM". */
export function intradayTickFormatter(dateStr: string): string {
  const h = parseInt(dateStr.slice(11, 13), 10)
  const m = dateStr.slice(14, 16)
  return `${h}:${m}`
}


/**
 * Decimal places for an axis label, chosen from how much ground the axis
 * actually covers. A fixed 0 turns a range of a couple of percent into
 * "0%, 0%, 1%" — three labels, two of them identical and none of them true.
 */
export function axisDecimals(span: number): number {
  if (span >= 20) return 0
  if (span >= 2) return 1
  return 2
}

/**
 * Thin `ticks` down to at most `max`, keeping the first and last.
 *
 * computeXTicks picks a sensible density for a wide chart, but the same
 * count collides into an unreadable smear at phone width. Rather than
 * measuring the container (which recharts doesn't expose to the `ticks`
 * prop), the performance charts just ask for a count that reads cleanly at
 * every width — a couple of extra months between labels costs nothing on a
 * chart that already has a tooltip.
 */
export function thinTicks(ticks: string[], max: number): string[] {
  if (ticks.length <= max || max < 2) return ticks
  const step = Math.ceil(ticks.length / max)
  const kept = ticks.filter((_, i) => i % step === 0)
  const lastIndex = ticks.length - 1
  const keptLastIndex = (kept.length - 1) * step
  if (keptLastIndex !== lastIndex) {
    // Append the true final tick, but never let the closing gap be tighter
    // than the regular spacing — a last label crowded against its neighbour
    // is what makes the axis unreadable at phone width. When it would be,
    // it replaces that neighbour instead of joining it.
    if (lastIndex - keptLastIndex < step) kept.pop()
    kept.push(ticks[lastIndex])
  }
  return kept
}
