import { describe, expect, it, vi } from 'vitest'
import { ApiError, buildUrl, createApiClient } from './client'
import { createTokenStore } from './tokens'

function memoryStorage() {
  const data = new Map<string, string>()
  return {
    getItem: (key: string) => data.get(key) ?? null,
    setItem: (key: string, value: string) => void data.set(key, value),
    removeItem: (key: string) => void data.delete(key),
  }
}

function json(body: unknown, status = 200, type = 'application/json'): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'content-type': type } })
}

function problem(status: number, title: string, detail: string, extra: object = {}): Response {
  return json({ type: `/problems/${title}`, title, status, detail, ...extra }, status, 'application/problem+json')
}

function setup(responses: (Response | Error)[], tokens = createTokenStore(memoryStorage())) {
  const queue = [...responses]
  const calls: { url: string; init: RequestInit }[] = []
  const fetchImpl = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(url), init: init ?? {} })
    const next = queue.shift()
    if (!next) throw new Error('unexpected request')
    if (next instanceof Error) throw next
    return next
  }) as unknown as typeof fetch
  const onUnauthorized = vi.fn()
  const client = createApiClient({ baseUrl: 'http://api.test/', tokens, fetchImpl, onUnauthorized })
  return { client, calls, tokens, onUnauthorized, fetchImpl }
}

/** The ApiError a call fails with (the test fails if it succeeds). */
async function failure(call: Promise<unknown>): Promise<ApiError> {
  try {
    await call
  } catch (e) {
    return e as ApiError
  }
  throw new Error('expected the call to fail')
}

const headersOf = (init: RequestInit) => init.headers as Record<string, string>

describe('buildUrl', () => {
  it('joins the base and path and trims the trailing slash', () => {
    expect(buildUrl('http://api.test/', '/api/v1/me')).toBe('http://api.test/api/v1/me')
  })

  it('adds query parameters and skips empty ones', () => {
    const url = buildUrl('http://api.test', '/x', { status: 'draft', section: '', limit: 5, cursor: null, flag: false })
    expect(url).toBe('http://api.test/x?status=draft&limit=5&flag=false')
  })

  it('encodes values', () => {
    expect(buildUrl('http://api.test', '/x', { q: 'a b&c' })).toBe('http://api.test/x?q=a+b%26c')
  })
})

describe('requests', () => {
  it('sends the access token as a bearer header', async () => {
    const { client, calls, tokens } = setup([json({ ok: true })])
    tokens.set('access-1', 'refresh-1')
    await client.get('/api/v1/me')
    expect(headersOf(calls[0].init).Authorization).toBe('Bearer access-1')
    expect(calls[0].init.method).toBe('GET')
  })

  it('sends no Authorization header without a token or when auth is off', async () => {
    const { client, calls, tokens } = setup([json({}), json({})])
    await client.get('/api/v1/sections')
    tokens.set('a', 'r')
    await client.post('/api/v1/auth/login', { email: 'x', password: 'y' }, { auth: false })
    expect(headersOf(calls[0].init).Authorization).toBeUndefined()
    expect(headersOf(calls[1].init).Authorization).toBeUndefined()
  })

  it('sends JSON bodies with a content type', async () => {
    const { client, calls } = setup([json({ id: 1 })])
    await client.post('/api/v1/requests', { priority: 2 })
    expect(headersOf(calls[0].init)['Content-Type']).toBe('application/json')
    expect(calls[0].init.body).toBe('{"priority":2}')
    expect(calls[0].init.method).toBe('POST')
  })

  it('does not send a body or content type for a plain POST', async () => {
    const { client, calls } = setup([json({})])
    await client.post('/api/v1/plans/1/approve')
    expect(calls[0].init.body).toBeUndefined()
    expect(headersOf(calls[0].init)['Content-Type']).toBeUndefined()
  })

  it('supports PUT and PATCH', async () => {
    const { client, calls } = setup([json({}), json({})])
    await client.put('/a', { x: 1 })
    await client.patch('/b', { y: 2 })
    expect(calls.map((c) => c.init.method)).toEqual(['PUT', 'PATCH'])
  })

  it('returns the parsed JSON', async () => {
    const { client } = setup([json({ id: 7, name: 'A' })])
    expect(await client.get('/x')).toEqual({ id: 7, name: 'A' })
  })

  it('returns undefined for 204', async () => {
    const { client } = setup([new Response(null, { status: 204 })])
    expect(await client.post('/x')).toBeUndefined()
  })
})

describe('errors', () => {
  it('turns problem+json into an ApiError with field errors', async () => {
    const { client } = setup([
      problem(422, 'validation', 'Request body is invalid', {
        errors: [
          { field: 'duration_minutes', message: 'Input should be greater than or equal to 15' },
          { field: 'priority', message: 'Input should be less than or equal to 3' },
        ],
      }),
    ])
    const error = await failure(client.post('/api/v1/requests', {}))
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(422)
    expect(error.title).toBe('validation')
    expect(error.detail).toBe('Request body is invalid')
    expect(error.fieldMessage('duration_minutes')).toBe('Input should be greater than or equal to 15')
    expect(error.fieldMessage('priority')).toContain('less than or equal to 3')
    expect(error.fieldMessage('nope')).toBeUndefined()
  })

  it('keeps extra problem fields such as the list of stale requests', async () => {
    const { client } = setup([problem(409, 'stale_plan', 'Run a new plan.', { request_ids: [3, 4] })])
    const error = await failure(client.post('/api/v1/plans/1/approve'))
    expect(error.status).toBe(409)
    expect(error.extra).toEqual({ request_ids: [3, 4] })
  })

  it('reports 403 without logging the user out', async () => {
    const { client, onUnauthorized, tokens } = setup([problem(403, 'forbidden', "role 'viewer' may not do this")])
    tokens.set('a', 'r')
    const error = await failure(client.post('/api/v1/plans', {}))
    expect(error.status).toBe(403)
    expect(error.title).toBe('forbidden')
    expect(onUnauthorized).not.toHaveBeenCalled()
    expect(tokens.getAccess()).toBe('a')
  })

  it('handles a non-JSON error response', async () => {
    const { client } = setup([new Response('Bad gateway', { status: 502, statusText: 'Bad Gateway' })])
    const error = await failure(client.get('/x'))
    expect(error).toBeInstanceOf(ApiError)
    expect(error.status).toBe(502)
    expect(error.title).toBe('http_error')
  })

  it('reports a network failure as status 0 with a readable message', async () => {
    const { client } = setup([new TypeError('Failed to fetch')])
    const error = await failure(client.get('/x'))
    expect(error.status).toBe(0)
    expect(error.title).toBe('network_error')
    expect(error.detail).toMatch(/backend is running/)
  })
})

describe('401 handling', () => {
  it('refreshes the token once and retries the request', async () => {
    const { client, calls, tokens, onUnauthorized } = setup([
      problem(401, 'token_expired', 'Token has expired'),
      json({ access_token: 'new-access', refresh_token: 'new-refresh', token_type: 'bearer', expires_in: 900 }),
      json({ id: 1 }),
    ])
    tokens.set('old-access', 'old-refresh')
    expect(await client.get('/api/v1/me')).toEqual({ id: 1 })
    expect(calls.map((c) => c.url)).toEqual([
      'http://api.test/api/v1/me',
      'http://api.test/api/v1/auth/refresh',
      'http://api.test/api/v1/me',
    ])
    expect(JSON.parse(String(calls[1].init.body))).toEqual({ refresh_token: 'old-refresh' })
    expect(headersOf(calls[2].init).Authorization).toBe('Bearer new-access')
    expect(tokens.getAccess()).toBe('new-access')
    expect(tokens.getRefresh()).toBe('new-refresh')
    expect(onUnauthorized).not.toHaveBeenCalled()
  })

  it('logs out when the refresh fails', async () => {
    const { client, tokens, onUnauthorized } = setup([
      problem(401, 'token_expired', 'Token has expired'),
      problem(401, 'invalid_token', 'Refresh token is revoked or unknown'),
    ])
    tokens.set('old', 'dead')
    const error = await failure(client.get('/api/v1/me'))
    expect(error.status).toBe(401)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(tokens.getAccess()).toBeNull()
    expect(tokens.getRefresh()).toBeNull()
  })

  it('logs out at once when there is no refresh token', async () => {
    const { client, calls, onUnauthorized } = setup([problem(401, 'not_authenticated', 'Sign in first')])
    const error = await failure(client.get('/api/v1/me'))
    expect(error.status).toBe(401)
    expect(calls).toHaveLength(1)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
  })

  it('logs out when the retried request is still refused', async () => {
    const { client, tokens, onUnauthorized } = setup([
      problem(401, 'invalid_token', 'Token is invalid'),
      json({ access_token: 'n', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 }),
      problem(401, 'invalid_token', 'Token is invalid'),
    ])
    tokens.set('a', 'r')
    await client.get('/api/v1/me').catch(() => undefined)
    expect(onUnauthorized).toHaveBeenCalledTimes(1)
    expect(tokens.getAccess()).toBeNull()
  })

  it('shares one refresh between requests that fail together', async () => {
    const { client, calls, tokens } = setup([
      problem(401, 'token_expired', 'x'),
      problem(401, 'token_expired', 'x'),
      json({ access_token: 'n', refresh_token: 'r2', token_type: 'bearer', expires_in: 900 }),
      json({ a: 1 }),
      json({ b: 2 }),
    ])
    tokens.set('old', 'r')
    const [a, b] = await Promise.all([client.get('/a'), client.get('/b')])
    expect([a, b]).toEqual([{ a: 1 }, { b: 2 }])
    expect(calls.filter((c) => c.url.endsWith('/auth/refresh'))).toHaveLength(1)
  })

  it('does not treat a wrong password as a dead session', async () => {
    const { client, onUnauthorized, calls } = setup([problem(401, 'invalid_credentials', 'Invalid email or password')])
    const error = await failure(client.post('/api/v1/auth/login', { email: 'a', password: 'b' }, { auth: false }))
    expect(error.status).toBe(401)
    expect(error.title).toBe('invalid_credentials')
    expect(onUnauthorized).not.toHaveBeenCalled()
    expect(calls).toHaveLength(1) // no refresh attempt
  })
})

describe('token store', () => {
  it('keeps tokens in memory and mirrors them to the given storage', () => {
    const storage = memoryStorage()
    const store = createTokenStore(storage)
    expect(store.getAccess()).toBeNull()
    store.set('a1', 'r1')
    expect(store.getAccess()).toBe('a1')
    expect(storage.getItem('bp.access')).toBe('a1')
    expect(storage.getItem('bp.refresh')).toBe('r1')
  })

  it('restores tokens after a reload', () => {
    const storage = memoryStorage()
    createTokenStore(storage).set('a1', 'r1')
    const reloaded = createTokenStore(storage)
    expect(reloaded.getAccess()).toBe('a1')
    expect(reloaded.getRefresh()).toBe('r1')
  })

  it('clears memory and storage', () => {
    const storage = memoryStorage()
    const store = createTokenStore(storage)
    store.set('a1', 'r1')
    store.clear()
    expect(store.getAccess()).toBeNull()
    expect(storage.getItem('bp.access')).toBeNull()
    expect(createTokenStore(storage).getRefresh()).toBeNull()
  })

  it('never uses localStorage', () => {
    const store = createTokenStore(memoryStorage())
    store.set('a', 'r')
    expect(window.localStorage.getItem('bp.access')).toBeNull()
  })
})
