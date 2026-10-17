import { Suspense, lazy, useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { backgroundSupported, backgroundWanted, saveBackgroundWanted } from '../lib/background'
import { clearIntroFlag, shouldPlayIntro } from '../lib/intro'
import { roleLabel } from '../lib/permissions'
import { Loading } from './ui'

// The 3D welcome (and three.js with it) is only fetched when it is about to play.
const IntroSplash = lazy(() => import('./intro/IntroSplash'))
const BackgroundScene = lazy(() => import('./background/BackgroundScene'))

/** Redirects to the login page when there is no session. */
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Loading label="Checking your session" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Layout />
}

function initials(name: string): string {
  const letters = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0].toUpperCase())
  return letters.join('') || '?'
}

function Layout() {
  const { user, logout } = useAuth()
  const [intro, setIntro] = useState(shouldPlayIntro)
  const [bgWanted, setBgWanted] = useState(backgroundWanted)
  const [bgReady, setBgReady] = useState(false)
  const [bgFailed, setBgFailed] = useState(false)
  const bgAvailable = backgroundSupported() && !bgFailed
  const bgOn = bgAvailable && bgWanted && !intro // wait until the welcome has finished
  useEffect(() => {
    clearIntroFlag() // play once per sign-in, even if the page is reloaded halfway
  }, [])
  if (!user) return null
  return (
    <div className={`app${bgOn && bgReady ? ' bg3d' : ''}`}>
      {bgOn && (
        <Suspense fallback={null}>
          <BackgroundScene onReady={() => setBgReady(true)} onFail={() => setBgFailed(true)} />
        </Suspense>
      )}
      {intro && (
        <Suspense fallback={<div className="intro-overlay" />}>
          <IntroSplash name={user.name} onDone={() => setIntro(false)} />
        </Suspense>
      )}
      <header className="topbar">
        <Link className="brand" to="/" title="Back to the homepage">
          <span className="brand-mark" aria-hidden="true">
            //
          </span>
          MARG SANYOG
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/requests">Requests</NavLink>
          <NavLink to="/plans">Plans</NavLink>
          <NavLink to="/calendar">Calendar</NavLink>
        </nav>
        <div className="user">
          <span className="avatar" aria-hidden="true">
            {initials(user.name)}
          </span>
          <div className="user-text">
            <strong>{user.name}</strong>
            <span>
              {roleLabel(user.role)}
              {user.department ? ` · ${user.department.code}` : ''}
            </span>
          </div>
          {bgAvailable && (
            <button
              type="button"
              className="btn btn-ghost-light bg-toggle"
              aria-pressed={bgWanted}
              title="Turn the 3D background on or off"
              onClick={() => {
                saveBackgroundWanted(!bgWanted)
                setBgWanted(!bgWanted)
              }}
            >
              3D {bgWanted ? 'on' : 'off'}
            </button>
          )}
          <button type="button" className="btn btn-ghost-light" onClick={logout}>
            Log out
          </button>
        </div>
      </header>
      <main className="page">
        <Outlet />
      </main>
    </div>
  )
}
