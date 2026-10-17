import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { User } from './api/types'

const state = vi.hoisted(() => ({ access: null as string | null }))
const mocks = vi.hoisted(() => ({ me: vi.fn(), plans: vi.fn(), requests: vi.fn() }))

vi.mock('./api', () => ({
  api: { login: vi.fn(), demoStatus: vi.fn().mockResolvedValue({ enabled: false, email: null }), me: mocks.me, plans: mocks.plans, requests: mocks.requests },
  tokens: {
    getAccess: () => state.access,
    clear: () => {
      state.access = null
    },
  },
  setUnauthorizedHandler: vi.fn(),
}))

import App from './App'
import { AuthProvider } from './auth/AuthContext'

const planner: User = { id: 2, email: 'planner@blockplanner.test', name: 'Demo Planner', role: 'planner', department: null }

function open(path: string) {
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  state.access = null
  mocks.me.mockReset()
  mocks.plans.mockResolvedValue({ items: [], next_cursor: null })
  mocks.requests.mockResolvedValue({ items: [], next_cursor: null })
})

describe('routes', () => {
  it('opens the public homepage at the root, without signing in', async () => {
    open('/')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('One closure')
    expect(screen.getAllByRole('link', { name: 'Log in' })[0]).toHaveAttribute('href', '/login')
  })

  it('keeps the dashboard behind the login', async () => {
    open('/dashboard')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })

  it('shows the dashboard to a signed-in user', async () => {
    state.access = 'token'
    mocks.me.mockResolvedValue(planner)
    open('/dashboard')
    expect(await screen.findByRole('heading', { name: 'Dashboard' })).toBeInTheDocument()
  })

  it('lets a signed-in user come back to the homepage and offers the dashboard there', async () => {
    state.access = 'token'
    mocks.me.mockResolvedValue(planner)
    open('/')
    expect((await screen.findAllByRole('link', { name: 'Open dashboard' }))[0]).toHaveAttribute('href', '/dashboard')
  })

  it('sends unknown addresses to the homepage', async () => {
    open('/nowhere')
    expect(await screen.findByRole('heading', { level: 1 })).toHaveTextContent('One closure')
  })

  it('keeps the other pages behind the login too', async () => {
    for (const path of ['/requests', '/plans', '/plans/1', '/calendar']) {
      const { unmount } = open(path)
      expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
      unmount()
    }
  })
})
