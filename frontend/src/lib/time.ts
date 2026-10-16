// The planner works in Asia/Kolkata, a fixed +05:30 offset, and the API returns ISO strings with
// that offset. Display code reads the parts straight from the string so the browser's own time
// zone never shifts anything.

export const IST_OFFSET = '+05:30'

const WEEKDAYS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/** "2026-10-19" -> "2026-10-19T00:00:00+05:30" */
export function istMidnight(date: string): string {
  return `${date}T00:00:00${IST_OFFSET}`
}

/** A datetime-local value ("2026-10-19T08:30") -> "2026-10-19T08:30:00+05:30" */
export function istFromLocalInput(value: string): string {
  return `${value.slice(0, 16)}:00${IST_OFFSET}`
}

/** "2026-10-19T08:30:00+05:30" -> "2026-10-19T08:30" for a datetime-local input */
export function localInputFromIso(iso: string | null): string {
  return iso ? iso.slice(0, 16) : ''
}

export function addDays(date: string, days: number): string {
  const [y, m, d] = date.split('-').map(Number)
  const moment = new Date(Date.UTC(y, m - 1, d + days))
  return moment.toISOString().slice(0, 10)
}

export function daysBetween(from: string, to: string): number {
  const toMs = (date: string) => {
    const [y, m, d] = date.split('-').map(Number)
    return Date.UTC(y, m - 1, d)
  }
  return Math.round((toMs(to) - toMs(from)) / 86_400_000)
}

/** "2026-10-19" -> "Mon 19 Oct" */
export function fmtDate(date: string): string {
  const [y, m, d] = date.slice(0, 10).split('-').map(Number)
  const weekday = WEEKDAYS[new Date(Date.UTC(y, m - 1, d)).getUTCDay()]
  return `${weekday} ${d} ${MONTHS[m - 1]}`
}

/** "2026-10-19T08:30:00+05:30" -> "08:30" */
export function fmtTime(iso: string): string {
  return iso.slice(11, 16)
}

/** "2026-10-19T08:30:00+05:30" -> "Mon 19 Oct 08:30" */
export function fmtDateTime(iso: string | null): string {
  return iso ? `${fmtDate(iso)} ${fmtTime(iso)}` : '-'
}

export function fmtDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours === 0) return `${rest} min`
  return rest === 0 ? `${hours} h` : `${hours} h ${rest} min`
}

export function fmtHours(value: number): string {
  return `${Number.isInteger(value) ? value : value.toFixed(1)} h`
}

/** Percentage change from `before` to `after`, rounded; null when there is no baseline. */
export function percentChange(before: number, after: number): number | null {
  if (before === 0) return null
  return Math.round(((after - before) / before) * 100)
}

/** Reduction as a positive number: 70 means 70% lower than the baseline. */
export function percentReduction(before: number, after: number): number | null {
  const change = percentChange(before, after)
  return change === null ? null : -change
}

/** The next Monday after `from` (today when it already is a Monday), as "YYYY-MM-DD". */
export function nextMonday(from: Date = new Date()): string {
  const day = from.getDay() // 0 = Sunday
  const ahead = (8 - day) % 7
  const target = new Date(from.getFullYear(), from.getMonth(), from.getDate() + ahead)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${target.getFullYear()}-${pad(target.getMonth() + 1)}-${pad(target.getDate())}`
}

/** The Monday of the week that contains `date` ("YYYY-MM-DD"). */
export function mondayOf(date: string): string {
  const [y, m, d] = date.split('-').map(Number)
  const weekday = new Date(Date.UTC(y, m - 1, d)).getUTCDay() // 0 = Sunday
  return addDays(date, -((weekday + 6) % 7))
}

/** Number of whole days a plan covers (at least 1). */
export function horizonDays(plan: { horizon_start: string; horizon_end: string }): number {
  return Math.max(1, daysBetween(plan.horizon_start.slice(0, 10), plan.horizon_end.slice(0, 10)))
}

export function plural(count: number, singular: string, pluralForm = `${singular}s`): string {
  return `${count} ${count === 1 ? singular : pluralForm}`
}
