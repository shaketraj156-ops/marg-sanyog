import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  reload(): void
  /** Replace the data without a request (after an action returned the new value). */
  setData(value: T | null): void
}

function toApiError(error: unknown): ApiError {
  return error instanceof ApiError ? error : new ApiError(0, 'error', String(error))
}

/** Run an async function when `deps` change; ignores answers that arrive out of order. */
export function useAsync<T>(fn: () => Promise<T>, deps: unknown[]): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [tick, setTick] = useState(0)
  const latest = useRef(0)

  useEffect(() => {
    const id = ++latest.current
    setLoading(true)
    fn()
      .then((value) => {
        if (id !== latest.current) return
        setData(value)
        setError(null)
      })
      .catch((e) => {
        if (id === latest.current) setError(toApiError(e))
      })
      .finally(() => {
        if (id === latest.current) setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, tick])

  const reload = useCallback(() => setTick((n) => n + 1), [])
  return { data, error, loading, reload, setData }
}

/** Call `fn` every `intervalMs` while `active` is true (stops when the page unmounts). */
export function usePolling(fn: () => void, intervalMs: number, active: boolean): void {
  const saved = useRef(fn)
  useEffect(() => {
    saved.current = fn
  })
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => saved.current(), intervalMs)
    return () => window.clearInterval(timer)
  }, [intervalMs, active])
}
