import { Link, NavLink, Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '../auth/AuthContext'
import { roleLabel } from '../lib/permissions'
import { Loading } from './ui'

export function SyntheticBanner() {
  return (
    <div className="banner" role="note">
      All data is synthetic (simulation). Nothing here controls trains, signals or power.
    </div>
  )
}

/** Redirects to the login page when there is no session. */
export function RequireAuth() {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <Loading label="Checking your session" />
  if (!user) return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />
  return <Layout />
}

function Layout() {
  const { user, logout } = useAuth()
  if (!user) return null
  return (
    <div className="app">
      <SyntheticBanner />
      <header className="topbar">
        <Link className="brand" to="/" title="Back to the homepage">
          <span className="brand-mark" aria-hidden="true">
            //
          </span>
          Block Planner
        </Link>
        <nav className="nav" aria-label="Main">
          <NavLink to="/dashboard">Dashboard</NavLink>
          <NavLink to="/requests">Requests</NavLink>
          <NavLink to="/plans">Plans</NavLink>
          <NavLink to="/calendar">Calendar</NavLink>
        </nav>
        <div className="user">
          <div className="user-text">
            <strong>{user.name}</strong>
            <span>
              {roleLabel(user.role)}
              {user.department ? ` · ${user.department.code}` : ''}
            </span>
          </div>
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
