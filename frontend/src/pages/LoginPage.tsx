import { useState } from 'react'
import type { FormEvent } from 'react'
import { Link, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { useAuth } from '../auth/AuthContext'
import { Field } from '../components/ui'
import { describeError } from '../lib/errors'
import { clearIntroFlag, markIntroPending } from '../lib/intro'

const DEMO_USERS = [
  ['planner@blockplanner.test', 'Planner: runs, approves and publishes plans'],
  ['admin@blockplanner.test', 'Administrator'],
  ['engg@blockplanner.test', 'Engineering department user'],
  ['trd@blockplanner.test', 'Traction Distribution department user'],
  ['snt@blockplanner.test', 'Signal and Telecom department user'],
  ['viewer@blockplanner.test', 'Viewer: read-only'],
]

export function LoginPage() {
  const { user, login } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()
  const from = (location.state as { from?: string } | null)?.from ?? '/dashboard'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<unknown>(null)
  const [busy, setBusy] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [capsLock, setCapsLock] = useState(false)

  if (user) return <Navigate to={from} replace />

  const submit = async (event: FormEvent) => {
    event.preventDefault()
    setBusy(true)
    setError(null)
    markIntroPending() // set before signing in: the page changes as soon as the session exists
    try {
      await login(email.trim(), password)
      navigate(from, { replace: true })
    } catch (e) {
      clearIntroFlag()
      setError(e)
      setBusy(false)
    }
  }

  const message =
    error instanceof ApiError && error.title === 'invalid_credentials'
      ? 'That email and password do not match.'
      : error
        ? describeError(error)
        : ''

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="brand brand-large">
          <span className="brand-mark" aria-hidden="true">
            //
          </span>
          MARG SANYOG
        </div>
        <p className="muted">AI-powered automatic block planning for railway maintenance (simulation).</p>
        <h1 className="login-title">Welcome back</h1>
        <p className="muted login-lead">Sign in to plan, review and publish railway blocks.</p>
        <form onSubmit={submit} noValidate>
          <Field label="Email">
            <input
              type="email"
              autoComplete="username"
              placeholder="you@blockplanner.test"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              aria-invalid={error ? true : undefined}
              required
              autoFocus
            />
          </Field>
          <div className="password-row">
            <Field label="Password">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyUp={(e) => setCapsLock(e.getModifierState('CapsLock'))}
                onBlur={() => setCapsLock(false)}
                aria-invalid={error ? true : undefined}
                required
              />
            </Field>
            <button
              type="button"
              className="link password-toggle"
              aria-pressed={showPassword}
              onClick={() => setShowPassword((v) => !v)}
            >
              {showPassword ? 'Hide' : 'Show'}
            </button>
          </div>
          {capsLock && (
            <div className="alert alert-warn" role="status">
              Caps Lock is on.
            </div>
          )}
          {message && (
            <div className="alert alert-error" role="alert">
              {message}
            </div>
          )}
          <button type="submit" className="btn btn-primary btn-block" disabled={busy || !email || !password}>
            {busy ? 'Signing in...' : 'Sign in'}
          </button>
        </form>
        <p className="login-back">
          <Link to="/">← Back to the homepage</Link>
        </p>
        <details className="demo-users">
          <summary>Demo users (created by the seed script)</summary>
          <ul>
            {DEMO_USERS.map(([address, label]) => (
              <li key={address}>
                <button type="button" className="link" onClick={() => setEmail(address)}>
                  {address}
                </button>
                <span className="muted"> {label}</span>
              </li>
            ))}
          </ul>
          <p className="muted">Everyone uses the password you chose for SEED_PASSWORD.</p>
        </details>
      </div>
    </div>
  )
}
