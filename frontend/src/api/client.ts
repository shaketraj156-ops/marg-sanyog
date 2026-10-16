import type { TokenStore } from './tokens'
import type { FieldError, TokenPair } from './types'

/** An error response from the API (problem+json), a network failure (status 0), or similar. */
export class ApiError extends Error {
  status: number
  title: string
  detail: string
  errors: FieldError[]
  extra: Record<string, unknown>

  constructor(
    status: number,
    title: string,
    detail: string,
    errors: FieldError[] = [],
    extra: Record<string, unknown> = {},
  ) {
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.title = title
    this.detail = detail
    this.errors = errors
    this.extra = extra
  }

  /** Server-side message for one form field, if there is one. */
  fieldMessage(field: string): string | undefined {
    return this.errors.find((e) => e.field === field)?.message
  }
}

export type Query = Record<string, string | number | boolean | null | undefined>

export interface RequestOptions {
  query?: Query
  body?: unknown
  headers?: Record<string, string>
  /** Send the access token and handle 401 by refreshing. False for login. */
  auth?: boolean
}

export interface ClientOptions {
  baseUrl: string
  tokens: TokenStore
  fetchImpl?: typeof fetch
  /** Called when the session cannot continue (no valid token and no way to refresh). */
  onUnauthorized?: () => void
}

export interface ApiClient {
  request<T>(method: string, path: string, options?: RequestOptions): Promise<T>
  get<T>(path: string, query?: Query): Promise<T>
  post<T>(path: string, body?: unknown, options?: Omit<RequestOptions, 'body'>): Promise<T>
  put<T>(path: string, body?: unknown): Promise<T>
  patch<T>(path: string, body?: unknown): Promise<T>
}

export function buildUrl(baseUrl: string, path: string, query?: Query): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value === undefined || value === null || value === '') continue
    params.set(key, String(value))
  }
  const text = params.toString()
  return `${baseUrl.replace(/\/+$/, '')}${path}${text ? `?${text}` : ''}`
}

async function toApiError(response: Response): Promise<ApiError> {
  const type = response.headers.get('content-type') ?? ''
  if (type.includes('json')) {
    try {
      const body = await response.json()
      const { title, detail, errors, status: _status, type: _type, ...extra } = body ?? {}
      return new ApiError(
        response.status,
        typeof title === 'string' ? title : 'error',
        typeof detail === 'string' ? detail : response.statusText,
        Array.isArray(errors) ? errors : [],
        extra,
      )
    } catch {
      // fall through to the generic error
    }
  }
  return new ApiError(response.status, 'http_error', response.statusText || `HTTP ${response.status}`)
}

export function createApiClient(options: ClientOptions): ApiClient {
  const { baseUrl, tokens, onUnauthorized } = options
  const doFetch = options.fetchImpl ?? ((...args: Parameters<typeof fetch>) => fetch(...args))
  let refreshing: Promise<boolean> | null = null

  async function send(method: string, path: string, opts: RequestOptions, token: string | null) {
    const headers: Record<string, string> = { Accept: 'application/json', ...opts.headers }
    if (opts.body !== undefined) headers['Content-Type'] = 'application/json'
    if (token && opts.auth !== false) headers.Authorization = `Bearer ${token}`
    try {
      return await doFetch(buildUrl(baseUrl, path, opts.query), {
        method,
        headers,
        body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      })
    } catch {
      throw new ApiError(
        0,
        'network_error',
        'Cannot reach the server. Check that the backend is running and try again.',
      )
    }
  }

  /** One refresh at a time, shared by every request that hit a 401 together. */
  function refreshTokens(): Promise<boolean> {
    if (!refreshing) {
      refreshing = (async () => {
        const refresh = tokens.getRefresh()
        if (!refresh) return false
        try {
          const response = await send(
            'POST',
            '/api/v1/auth/refresh',
            { auth: false, body: { refresh_token: refresh } },
            null,
          )
          if (!response.ok) return false
          const pair = (await response.json()) as TokenPair
          tokens.set(pair.access_token, pair.refresh_token)
          return true
        } catch {
          return false
        } finally {
          refreshing = null
        }
      })()
    }
    return refreshing
  }

  async function request<T>(method: string, path: string, opts: RequestOptions = {}): Promise<T> {
    let response = await send(method, path, opts, tokens.getAccess())
    if (response.status === 401 && opts.auth !== false) {
      if (await refreshTokens()) {
        response = await send(method, path, opts, tokens.getAccess())
      }
      if (response.status === 401) {
        tokens.clear()
        onUnauthorized?.()
      }
    }
    if (!response.ok) throw await toApiError(response)
    if (response.status === 204) return undefined as T
    return (await response.json()) as T
  }

  return {
    request,
    get: (path, query) => request('GET', path, { query }),
    post: (path, body, opts) => request('POST', path, { ...opts, body }),
    put: (path, body) => request('PUT', path, { body }),
    patch: (path, body) => request('PATCH', path, { body }),
  }
}
