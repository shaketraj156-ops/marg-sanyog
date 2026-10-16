import { ApiError } from '../api/client'

/** Human wording for an API failure, including the 403 (role not allowed) case. */
export function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return 'Your role is not allowed to do that.'
    if (error.status === 0) return error.detail
    return error.detail || error.title
  }
  return error instanceof Error ? error.message : String(error)
}
