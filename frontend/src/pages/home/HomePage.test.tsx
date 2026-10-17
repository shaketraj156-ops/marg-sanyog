import { act, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { User } from '../../api/types'

const auth = vi.hoisted(() => ({ user: null as User | null }))
vi.mock('../../auth/AuthContext', () => ({ useAuth: () => ({ user: auth.user }) }))

// GSAP needs a real browser (layout, scroll). Here it is replaced by a recorder, so the tests can
// check what the page asks it to do and drive the scroll progress by hand.
const gsapMock = vi.hoisted(() => ({
  timelines: [] as {
    config: { scrollTrigger: Record<string, unknown> }
    tweens: { target: unknown; vars: Record<string, unknown>; at: number }[]
    callbacks: Record<string, () => void>
    progressValue: number
  }[],
  reverted: 0,
  registered: [] as unknown[],
}))

vi.mock('gsap', () => ({
  gsap: {
    registerPlugin: (...plugins: unknown[]) => gsapMock.registered.push(...plugins),
    context: (fn: () => void) => {
      fn()
      return { revert: () => (gsapMock.reverted += 1) }
    },
    timeline: (config: { scrollTrigger: Record<string, unknown> }) => {
      const timeline = {
        config,
        tweens: [] as { target: unknown; vars: Record<string, unknown>; at: number }[],
        callbacks: {} as Record<string, () => void>,
        progressValue: 0,
        to(target: unknown, vars: Record<string, unknown>, at: number) {
          timeline.tweens.push({ target, vars, at })
          return timeline
        },
        eventCallback(name: string, fn: () => void) {
          timeline.callbacks[name] = fn
        },
        progress: () => timeline.progressValue,
      }
      gsapMock.timelines.push(timeline)
      return timeline
    },
  },
}))
vi.mock('gsap/ScrollTrigger', () => ({ ScrollTrigger: { name: 'scrollTrigger' } }))

import { HomePage } from './HomePage'

const planner: User = { id: 2, email: 'planner@blockplanner.test', name: 'Demo Planner', role: 'planner', department: null }

function page() {
  return render(
    <MemoryRouter>
      <HomePage />
    </MemoryRouter>,
  )
}

function setMedia(animated: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? !animated : query.includes('min-width') ? animated : false,
  })) as unknown as typeof window.matchMedia
}

const original = window.matchMedia
beforeEach(() => {
  auth.user = null
  gsapMock.timelines.length = 0
  gsapMock.reverted = 0
  gsapMock.registered.length = 0
  window.scrollTo = vi.fn() as unknown as typeof window.scrollTo
})
afterEach(() => {
  window.matchMedia = original
})

describe('the homepage content', () => {
  beforeEach(() => setMedia(false)) // plain page: no animation

  it('says what the project is and that the data is simulated', () => {
    page()
    expect(screen.getByRole('heading', { level: 1 })).toHaveTextContent(/One closure\s*for every department\./)
    expect(screen.getByText('Simulation: all data is synthetic')).toBeInTheDocument()
    expect(document.title).toMatch(/MARG SANYOG/)
  })

  it('offers a login in the navigation, the hero and at the end', () => {
    page()
    const links = screen.getAllByRole('link', { name: 'Log in' })
    expect(links).toHaveLength(3)
    links.forEach((link) => expect(link).toHaveAttribute('href', '/login'))
    expect(screen.queryByRole('link', { name: 'Open dashboard' })).toBeNull()
  })

  it('offers the dashboard instead once signed in', () => {
    auth.user = planner
    page()
    const links = screen.getAllByRole('link', { name: 'Open dashboard' })
    expect(links).toHaveLength(3)
    links.forEach((link) => expect(link).toHaveAttribute('href', '/dashboard'))
    expect(screen.queryByRole('link', { name: 'Log in' })).toBeNull()
  })

  it('lists the four steps when there is no train to show them', () => {
    page()
    const steps = within(screen.getByRole('region', { name: 'How it works' })).getAllByRole('listitem')
    expect(steps.map((s) => within(s).getByRole('heading').textContent)).toEqual(['Request', 'Plan', 'Review', 'Publish'])
    expect(screen.queryByLabelText('Stops')).toBeNull()
    expect(gsapMock.timelines).toHaveLength(0) // no animation was set up
  })

  it('describes the features and the example run, labelled as simulated', () => {
    page()
    expect(screen.getAllByRole('article')).toHaveLength(6)
    expect(screen.getByText('Fewer closures')).toBeInTheDocument()
    const results = screen.getByText('An example run').closest('section')!
    expect(within(results).getByText(/simulated data/)).toBeInTheDocument()
    expect(within(results).getByText('33% lower with joint planning')).toBeInTheDocument() // 15 -> 10
    expect(within(results).getByText('70% lower with joint planning')).toBeInTheDocument() // 56 -> 17
  })

  it('scrolls to the top from Overview', async () => {
    page()
    screen.getByRole('button', { name: 'Overview' }).click()
    expect(window.scrollTo).toHaveBeenCalledWith({ top: 0, behavior: 'smooth' })
  })
})

describe('the scroll-driven train', () => {
  beforeEach(() => setMedia(true))

  it('draws the scene, with the station boards', () => {
    page()
    expect(screen.getByTestId('hero-scene')).toBeInTheDocument()
    const names = [...document.querySelectorAll('.board-name')].map((n) => n.textContent)
    expect(names).toEqual(['REQUEST', 'PLAN', 'REVIEW', 'PUBLISH'])
  })

  it('never crops the track: the scene fits the window instead of filling it', () => {
    page()
    expect(screen.getByTestId('hero-scene').getAttribute('preserveAspectRatio')).toBe('xMidYMax meet')
  })

  it('pins the hero and ties the journey to the scroll', () => {
    page()
    expect(gsapMock.timelines).toHaveLength(1)
    const trigger = gsapMock.timelines[0].config.scrollTrigger
    expect(trigger).toMatchObject({ start: 'top top', pin: true, scrub: expect.any(Number) })
    expect(String(trigger.end)).toMatch(/^\+=\d+$/) // a scroll distance
    expect(gsapMock.registered).toHaveLength(1) // ScrollTrigger
  })

  it('moves the world in segments: arrive, stand, depart, four times, then leave', () => {
    page()
    const { tweens } = gsapMock.timelines[0]
    expect(tweens).toHaveLength(9)
    const offsets = tweens.map((t) => (t.vars as { offset: number }).offset)
    expect(offsets[1]).toBe(offsets[0]) // standing: stays at the station's offset
    expect(offsets[offsets.length - 1]).toBe(7000)
    // segments are laid end to end on the timeline
    tweens.slice(1).forEach((t, i) => {
      const previous = tweens[i]
      expect(t.at).toBeCloseTo(previous.at + (previous.vars as { duration: number }).duration, 6)
    })
  })

  it('changes the station board as the train passes each station', () => {
    page()
    const timeline = gsapMock.timelines[0]
    const board = () => document.querySelector('.station-board') as HTMLElement
    expect(within(board()).getByRole('heading')).toHaveTextContent('Follow one block, start to finish')

    const heading = (progress: number) => {
      timeline.progressValue = progress
      act(() => timeline.callbacks.onUpdate())
      return within(board()).getByRole('heading').textContent
    }
    expect(heading(0.15)).toBe('Request')
    expect(heading(0.45)).toBe('Plan')
    expect(heading(0.7)).toBe('Review')
    expect(heading(0.95)).toBe('Publish')
    expect(board()).toHaveTextContent('Station 4 of 4')
    expect(heading(0.15)).toBe('Request') // and back, when scrolling up
    expect(heading(0)).toBe('Follow one block, start to finish')
  })

  it('marks the stops the train has reached', () => {
    page()
    const timeline = gsapMock.timelines[0]
    timeline.progressValue = 0.7
    act(() => timeline.callbacks.onUpdate())
    const reached = [...screen.getByLabelText('Stops').children].map((li) => li.classList.contains('reached'))
    expect(reached).toEqual([true, true, true, false])
  })

  it('removes the pin and every animation when the page is left', () => {
    const { unmount } = page()
    expect(gsapMock.reverted).toBe(0)
    unmount()
    expect(gsapMock.reverted).toBe(1)
  })

  it('does not repeat the steps below the train', () => {
    page()
    expect(screen.queryByRole('region', { name: 'How it works' })).toBeNull()
  })
})
