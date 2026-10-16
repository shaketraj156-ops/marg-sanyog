import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ApiError } from '../api/client'
import type { User } from '../api/types'

const state = vi.hoisted(() => ({ access: null as string | null }))
const mocks = vi.hoisted(() => ({
  login: vi.fn(),
  me: vi.fn(),
}))

vi.mock('../api', () => ({
  api: { login: mocks.login, me: mocks.me },
  tokens: {
    getAccess: () => state.access,
    clear: () => {
      state.access = null
    },
  },
  setUnauthorizedHandler: vi.fn(),
}))

import { AuthProvider } from '../auth/AuthContext'
import { RequireAuth } from '../components/Layout'
import { LoginPage } from './LoginPage'

const planner: User = {
  id: 2,
  email: 'planner@blockplanner.test',
  name: 'Demo Planner',
  role: 'planner',
  department: null,
}

function app(initial = '/login') {
  return render(
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<p>Dashboard page</p>} />
            <Route path="/requests" element={<p>Requests page</p>} />
          </Route>
        </Routes>
      </AuthProvider>
    </MemoryRouter>,
  )
}

beforeEach(() => {
  state.access = null
  mocks.login.mockReset()
  mocks.me.mockReset()
})

describe('login page', () => {
  it('always shows the synthetic-data banner', () => {
    app()
    expect(screen.getByRole('note')).toHaveTextContent('All data is synthetic (simulation)')
  })

  it('fills the email from a demo user', () => {
    app()
    fireEvent.click(screen.getByText('Demo users (created by the seed script)'))
    fireEvent.click(screen.getByRole('button', { name: 'viewer@blockplanner.test' }))
    expect(screen.getByLabelText('Email')).toHaveValue('viewer@blockplanner.test')
  })

  it('keeps the button disabled until both fields are filled', () => {
    app()
    const button = screen.getByRole('button', { name: 'Sign in' })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.test' } })
    expect(button).toBeDisabled()
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'secret' } })
    expect(button).toBeEnabled()
  })

  it('explains a wrong password in plain words', async () => {
    mocks.login.mockRejectedValue(new ApiError(401, 'invalid_credentials', 'Invalid email or password'))
    app()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'planner@blockplanner.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'wrong' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That email and password do not match.')
  })

  it('says so when the server cannot be reached', async () => {
    mocks.login.mockRejectedValue(new ApiError(0, 'network_error', 'Cannot reach the server. Check that the backend is running and try again.'))
    app()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'a@b.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'x' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('backend is running')
  })

  it('signs in and opens the dashboard', async () => {
    mocks.login.mockResolvedValue({ access_token: 'a', refresh_token: 'r' })
    mocks.me.mockResolvedValue(planner)
    app()
    fireEvent.change(screen.getByLabelText('Email'), { target: { value: 'planner@blockplanner.test' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'right' } })
    fireEvent.click(screen.getByRole('button', { name: 'Sign in' }))
    expect(await screen.findByText('Dashboard page')).toBeInTheDocument()
    expect(mocks.login).toHaveBeenCalledWith('planner@blockplanner.test', 'right')
    expect(screen.getByText('Demo Planner')).toBeInTheDocument()
    expect(screen.getByText('Planner')).toBeInTheDocument()
  })
})

describe('protected pages', () => {
  it('send a signed-out visitor to the login page', async () => {
    app('/requests')
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
    expect(screen.queryByText('Requests page')).toBeNull()
  })

  it('restore a saved session after a reload', async () => {
    state.access = 'saved-token'
    mocks.me.mockResolvedValue(planner)
    app('/requests')
    expect(await screen.findByText('Requests page')).toBeInTheDocument()
  })

  it('drop a saved session the server no longer accepts', async () => {
    state.access = 'dead-token'
    mocks.me.mockRejectedValue(new ApiError(401, 'invalid_token', 'Token is invalid'))
    app('/requests')
    await waitFor(() => expect(screen.getByRole('button', { name: 'Sign in' })).toBeInTheDocument())
    expect(state.access).toBeNull()
  })

  it('log out from the top bar', async () => {
    state.access = 'saved-token'
    mocks.me.mockResolvedValue(planner)
    app('/')
    fireEvent.click(await screen.findByRole('button', { name: 'Log out' }))
    expect(await screen.findByRole('button', { name: 'Sign in' })).toBeInTheDocument()
  })
})
