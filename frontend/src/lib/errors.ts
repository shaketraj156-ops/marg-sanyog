import { ApiError } from '../api/client'

/** Human wording for an API failure, including the 403 (role not allowed) case. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Your role is not allowed to do that.'
    if (error.status === 0) return error.detail
    if (error.status === 429) return describeWait(error.detail)
    return error.detail || error.title
  }
  return error instanceof Error ? error.message : String(error)
}

/** "... Try again in 900 seconds." -> "... Try again in 15 minutes." (the server counts in seconds). */
export function describeWait(detail: string): string {
  return detail.replace(/in (\d+) seconds?/, (_, digits: string) => {
    const seconds = Number(digits)
    if (seconds < 120) return `in ${seconds} second${seconds === 1 ? '' : 's'}`
    return `in ${Math.ceil(seconds / 60)} minutes`
  })
}
