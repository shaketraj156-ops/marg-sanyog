import { describe, expect, it } from 'vitest'
import type { Role, User } from '../api/types'
import {
  canActOnRequest,
  canCreateRequests,
  canRejectRequests,
  canReviewPlans,
  canRunPlans,
  isReadOnly,
  isReviewer,
  roleLabel,
  stateActions,
} from './permissions'

const dept = (code: string) => ({ id: 1, code, name: code })
function user(role: Role, department: string | null = null): User {
  return { id: 1, email: `${role}@x.test`, name: role, role, department: department ? dept(department) : null }
}

const admin = user('admin')
const planner = user('planner')
const engg = user('dept_user', 'ENGG')
const trd = user('dept_user', 'TRD')
const viewer = user('viewer')
const nobody = null

describe('running and reviewing plans', () => {
  it.each([
    ['admin', admin, true],
    ['planner', planner, true],
    ['department user', engg, false],
    ['viewer', viewer, false],
    ['signed out', nobody, false],
  ])('%s: run=%s', (_name, who, allowed) => {
    expect(canRunPlans(who)).toBe(allowed)
    expect(canReviewPlans(who)).toBe(allowed)
    expect(isReviewer(who)).toBe(allowed)
    expect(canRejectRequests(who)).toBe(allowed)
  })
})

describe('creating requests', () => {
  it.each([
    ['admin', admin, true],
    ['planner', planner, true],
    ['department user', engg, true],
    ['viewer', viewer, false],
    ['signed out', nobody, false],
  ])('%s: create=%s', (_name, who, allowed) => {
    expect(canCreateRequests(who)).toBe(allowed)
  })
})

describe('acting on one request', () => {
  const engineering = { department: 'ENGG' }

  it('lets planners and admins act on any department', () => {
    expect(canActOnRequest(planner, engineering)).toBe(true)
    expect(canActOnRequest(admin, { department: 'SNT' })).toBe(true)
  })

  it('lets a department user act only on their own department', () => {
    expect(canActOnRequest(engg, engineering)).toBe(true)
    expect(canActOnRequest(trd, engineering)).toBe(false)
  })

  it('refuses a department user who has no department', () => {
    expect(canActOnRequest(user('dept_user'), engineering)).toBe(false)
  })

  it('never lets a viewer or a signed-out visitor act', () => {
    expect(canActOnRequest(viewer, engineering)).toBe(false)
    expect(canActOnRequest(nobody, engineering)).toBe(false)
  })
})

describe('read-only', () => {
  it('is true for viewers and signed-out visitors only', () => {
    expect(isReadOnly(viewer)).toBe(true)
    expect(isReadOnly(nobody)).toBe(true)
    for (const who of [admin, planner, engg]) expect(isReadOnly(who)).toBe(false)
  })
})

describe('what a request state allows', () => {
  it('follows the state machine', () => {
    expect(stateActions({ status: 'draft' })).toEqual({ edit: true, submit: true, cancel: true, reject: false })
    expect(stateActions({ status: 'submitted' })).toEqual({ edit: true, submit: false, cancel: true, reject: true })
    expect(stateActions({ status: 'scheduled' })).toEqual({ edit: false, submit: false, cancel: true, reject: false })
  })

  it.each(['published', 'completed', 'cancelled', 'rejected'] as const)('%s allows nothing', (status) => {
    expect(stateActions({ status })).toEqual({ edit: false, submit: false, cancel: false, reject: false })
  })
})

describe('role labels', () => {
  it('has a readable label for every role', () => {
    expect(roleLabel('admin')).toBe('Administrator')
    expect(roleLabel('dept_user')).toBe('Department user')
    expect(roleLabel('viewer')).toContain('read-only')
  })
})
