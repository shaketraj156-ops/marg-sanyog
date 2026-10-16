// Shapes of the backend responses (see http://127.0.0.1:8000/openapi.json).

export type Role = 'admin' | 'planner' | 'dept_user' | 'viewer'

export interface Department {
  id: number
  code: string
  name: string
}

export interface User {
  id: number
  email: string
  name: string
  role: Role
  department: Department | null
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  token_type: string
  expires_in: number
}

export interface Section {
  id: number
  code: string
  name: string
  division: string
  line_count: number
}

export type RequestStatus =
  | 'draft'
  | 'submitted'
  | 'scheduled'
  | 'published'
  | 'completed'
  | 'cancelled'
  | 'rejected'

export const REQUEST_STATUSES: RequestStatus[] = [
  'draft',
  'submitted',
  'scheduled',
  'published',
  'completed',
  'cancelled',
  'rejected',
]

export type WorkType = 'track' | 'ohe' | 'signal' | 'bridge' | 'other'
export const WORK_TYPES: WorkType[] = ['track', 'ohe', 'signal', 'bridge', 'other']

export type Relation = 'finish_before_start' | 'not_same_block' | 'same_block_allowed'
export const RELATIONS: Relation[] = ['finish_before_start', 'not_same_block', 'same_block_allowed']

export interface Dependency {
  depends_on: number
  relation: Relation
  min_gap_minutes: number
}

export interface RequestWarning {
  code: string
  detail: string
  request_ids: number[]
}

export interface BlockRequest {
  id: number
  status: RequestStatus
  department: string
  section_code: string
  work_type: WorkType
  description: string | null
  duration_minutes: number
  earliest_date: string
  deadline_date: string
  priority: number
  needs_power_block: boolean
  preferred_start: string | null
  requested_by: number
  version: number
  dependencies: Dependency[]
  created_at: string
  updated_at: string
  warnings: RequestWarning[]
}

export interface RequestList {
  items: BlockRequest[]
  next_cursor: number | null
}

export interface RequestInput {
  section_code: string
  work_type: WorkType
  duration_minutes: number
  earliest_date: string
  deadline_date: string
  priority: number
  needs_power_block: boolean
  description?: string | null
  preferred_start?: string | null
  department_code?: string
}

export type PlanStatus =
  | 'queued'
  | 'running'
  | 'succeeded'
  | 'infeasible'
  | 'failed'
  | 'cancelled'
  | 'approved'
  | 'published'
  | 'superseded'

export interface PlanMetrics {
  closures: number
  block_hours: number
  trains_affected: number
  traffic_cost: number
  weighted_postponement_days: number
  deferred: number
}

export interface PlanResultMetrics {
  baseline: PlanMetrics
  integrated: PlanMetrics
  solver: { wall_time_s: number; gap: number | null; note?: string | null }
}

export interface Plan {
  id: number
  parent_id: number | null
  status: PlanStatus
  solver_status: string | null
  horizon_start: string
  horizon_end: string
  slot_minutes: number
  weights: Record<string, number>
  time_limit_s: number
  seed: number
  input_hash: string | null
  objective_value: number | null
  best_bound: number | null
  gap: number | null
  metrics: PlanResultMetrics | null
  deferred_request_ids: number[]
  error: string | null
  created_by: number
  created_at: string
  finished_at: string | null
  approved_at: string | null
  published_at: string | null
}

export interface PlanList {
  items: Plan[]
  next_cursor: number | null
}

export interface PlanWeights {
  block: number
  traffic: number
  delay: number
  defer: number
}

export interface PlanInput {
  horizon_start: string
  horizon_end: string
  time_limit_s: number
  weights: PlanWeights
  slot_minutes?: number
  seed?: number
}

export interface PlanAccepted {
  id: number
  status: PlanStatus
  links: { self: string }
}

export interface ScheduleMember {
  request: string
  request_id: number
  dept: string
  start: string
  end: string
}

export interface ScheduleBlock {
  id: number | null
  section_code: string
  start: string
  end: string
  trains_affected: number
  members: ScheduleMember[]
}

export interface DeferredItem {
  request_id: number
  request: string
  reason: string
}

export interface Schedule {
  plan_id: number
  blocks: ScheduleBlock[]
  deferred: DeferredItem[]
}

export interface Baseline extends Schedule {
  metrics: PlanMetrics | null
}

export interface Conflict {
  type: string
  detail: string
  request_ids: number[]
  resolution: string
  resolution_detail: string
  section_code?: string
  departments?: string[]
  relation?: string
  reason?: string
}

export interface ConflictList {
  plan_id: number
  conflicts: Conflict[]
}

export interface Explanation {
  id: number
  code: string
  text: string
  numbers: Record<string, unknown>
  block_id: number | null
  request_id: number | null
}

export interface ExplanationList {
  plan_id: number
  items: Explanation[]
}

export interface Placement {
  start: string
  end: string
}

export interface WhatIfResult {
  feasible: boolean
  solver_status: string
  reason?: string
  target?: { request_id: number; from: Placement | null; to: Placement | null }
  metrics?: {
    current: PlanMetrics
    whatif: PlanMetrics
    difference: PlanMetrics
  }
  moved_requests?: { request_id: number; request: string; from: Placement | null; to: Placement | null }[]
}

export interface Move {
  request_id: number
  start: string
}

export interface CalendarMember {
  request_id: number
  request: string
  dept: string
  start: string
  end: string
}

export interface CalendarBlock {
  id: number
  plan_id: number
  section_code: string
  start: string
  end: string
  trains_affected: number
  status: string
  members: CalendarMember[]
}

export interface FieldError {
  field: string
  message: string
}
