import type { BlockRequest, Role, User } from '../api/types'

// What each role may do. The backend enforces the same rules (and answers 403); the UI uses these
// functions to hide or disable what a role cannot do. Keep them in step with section 14 of the spec.

const REVIEWERS: Role[] = ['planner', 'admin']
const REQUEST_WRITERS: Role[] = ['dept_user', 'planner', 'admin']

export function isReviewer(user: User | null): boolean {
  return !!user && REVIEWERS.includes(user.role)
}

/** Run plans, load traffic. */
export function canRunPlans(user: User | null): boolean {
  return isReviewer(user)
}

/** What-if, override, approve, publish. */
export function canReviewPlans(user: User | null): boolean {
  return isReviewer(user)
}

export function canCreateRequests(user: User | null): boolean {
  return !!user && REQUEST_WRITERS.includes(user.role)
}

/** Edit, submit, cancel and change the dependencies of one request. */
export function canActOnRequest(user: User | null, request: Pick<BlockRequest, 'department'>): boolean {
  if (!user) return false
  if (isReviewer(user)) return true
  if (user.role === 'dept_user') return user.department?.code === request.department
  return false
}

export function canRejectRequests(user: User | null): boolean {
  return isReviewer(user)
}

export function isReadOnly(user: User | null): boolean {
  return !user || user.role === 'viewer'
}

const STATE_ACTIONS: Record<string, { edit: boolean; submit: boolean; cancel: boolean; reject: boolean }> = {
  draft: { edit: true, submit: true, cancel: true, reject: false },
  submitted: { edit: true, submit: false, cancel: true, reject: true },
  scheduled: { edit: false, submit: false, cancel: true, reject: false },
}

/** Which actions the request's state allows (the role is checked separately). */
export function stateActions(request: Pick<BlockRequest, 'status'>) {
  return STATE_ACTIONS[request.status] ?? { edit: false, submit: false, cancel: false, reject: false }
}

export function roleLabel(role: Role): string {
  return {
    admin: 'Administrator',
    planner: 'Planner',
    dept_user: 'Department user',
    viewer: 'Viewer (read-only)',
  }[role]
}
