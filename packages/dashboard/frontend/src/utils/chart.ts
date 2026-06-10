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
