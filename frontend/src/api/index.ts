import { createApiClient } from './client'
import { createTokenStore } from './tokens'
import type {
  Baseline,
  BlockRequest,
  CalendarBlock,
  ConflictList,
  Dependency,
  ExplanationList,
  Move,
  Plan,
  PlanAccepted,
  PlanInput,
  PlanList,
  RequestInput,
  RequestList,
  Schedule,
  Section,
  TokenPair,
  User,
  WhatIfResult,
  Department,
} from './types'

const BASE_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000'

export const tokens = createTokenStore(window.sessionStorage)

let unauthorizedHandler: (() => void) | null = null
/** The auth provider registers itself here so a dead session sends the user to the login page. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  unauthorizedHandler = handler
}

export const client = createApiClient({
  baseUrl: BASE_URL,
  tokens,
  onUnauthorized: () => unauthorizedHandler?.(),
})

const V1 = '/api/v1'

export const api = {
  // auth
  async login(email: string, password: string): Promise<TokenPair> {
    const pair = await client.post<TokenPair>(`${V1}/auth/login`, { email, password }, { auth: false })
    tokens.set(pair.access_token, pair.refresh_token)
    return pair
  },
  me: () => client.get<User>(`${V1}/me`),

  // reference data
  sections: () => client.get<Section[]>(`${V1}/sections`),
  departments: () => client.get<Department[]>(`${V1}/departments`),

  // requests
  requests: (query: {
    status?: string
    section?: string
    department?: string
    limit?: number
    cursor?: number | null
  }) => client.get<RequestList>(`${V1}/requests`, query),
  request: (id: number) => client.get<BlockRequest>(`${V1}/requests/${id}`),
  createRequest: (body: RequestInput) => client.post<BlockRequest>(`${V1}/requests`, body),
  updateRequest: (id: number, body: Partial<RequestInput> & { version: number }) =>
    client.patch<BlockRequest>(`${V1}/requests/${id}`, body),
  submitRequest: (id: number, version?: number) =>
    client.post<BlockRequest>(`${V1}/requests/${id}/submit`, version === undefined ? undefined : { version }),
  cancelRequest: (id: number, version?: number) =>
    client.post<BlockRequest>(`${V1}/requests/${id}/cancel`, version === undefined ? undefined : { version }),
  rejectRequest: (id: number, reason: string, version?: number) =>
    client.post<BlockRequest>(`${V1}/requests/${id}/reject`, { reason, version }),
  setDependencies: (id: number, dependencies: Dependency[], version?: number) =>
    client.put<BlockRequest>(`${V1}/requests/${id}/dependencies`, {
      version,
      dependencies: dependencies.map((d) => ({
        depends_on: d.depends_on,
        relation: d.relation,
        min_gap_minutes: d.min_gap_minutes,
      })),
    }),

  // plans
  createPlan: (body: PlanInput) => client.post<PlanAccepted>(`${V1}/plans`, body),
  plans: (query: { status?: string; limit?: number; cursor?: number | null } = {}) =>
    client.get<PlanList>(`${V1}/plans`, query),
  plan: (id: number) => client.get<Plan>(`${V1}/plans/${id}`),
  schedule: (id: number) => client.get<Schedule>(`${V1}/plans/${id}/schedule`),
  baseline: (id: number) => client.get<Baseline>(`${V1}/plans/${id}/baseline`),
  conflicts: (id: number) => client.get<ConflictList>(`${V1}/plans/${id}/conflicts`),
  explanations: (id: number, code?: string) =>
    client.get<ExplanationList>(`${V1}/plans/${id}/explanations`, { code }),
  whatIf: (id: number, move: Move & { time_limit_s?: number }) =>
    client.post<WhatIfResult>(`${V1}/plans/${id}/whatif`, move),
  override: (id: number, moves: Move[], timeLimit?: number) =>
    client.post<Plan>(`${V1}/plans/${id}/overrides`, { moves, time_limit_s: timeLimit }),
  approve: (id: number) => client.post<Plan>(`${V1}/plans/${id}/approve`),
  publish: (id: number) => client.post<Plan>(`${V1}/plans/${id}/publish`),

  // calendar and traffic
  blocks: (query: { section?: string; date_from?: string; date_to?: string } = {}) =>
    client.get<{ blocks: CalendarBlock[] }>(`${V1}/blocks`, query),
  syntheticTraffic: () => client.post<{ inserted: number }>(`${V1}/traffic/synthetic`, {}),
  rebuildTraffic: (date_from: string, date_to: string) =>
    client.post<{ days: number; sections: number; rows: number }>(`${V1}/traffic/rebuild`, {
      date_from,
      date_to,
    }),
}
