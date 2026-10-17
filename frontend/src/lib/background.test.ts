import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { backgroundSupported, backgroundWanted, saveBackgroundWanted } from './background'

const original = window.matchMedia

function stubMotion(reduced: boolean) {
  window.matchMedia = ((query: string) => ({
    matches: query.includes('prefers-reduced-motion') ? reduced : false,
  })) as unknown as typeof window.matchMedia
}

function stubWebdriver(value: boolean) {
  Object.defineProperty(navigator, 'webdriver', { value, configurable: true })
}

beforeEach(() => {
  localStorage.clear()
  stubWebdriver(false)
})

afterEach(() => {
  window.matchMedia = original
  localStorage.clear()
})

describe('the 3D background setting', () => {
  it('is on until the visitor switches it off, and remembers the choice', () => {
    expect(backgroundWanted()).toBe(true)
    saveBackgroundWanted(false)
    expect(backgroundWanted()).toBe(false)
    saveBackgroundWanted(true)
    expect(backgroundWanted()).toBe(true)
  })

  it('runs in an ordinary browser', () => {
    stubMotion(false)
    expect(backgroundSupported()).toBe(true)
  })

  it('still runs when the browser reports reduced motion', () => {
    stubMotion(true)
    expect(backgroundSupported()).toBe(true)
  })

  it('does not run in automated browsers', () => {
    stubMotion(false)
    stubWebdriver(true)
    expect(backgroundSupported()).toBe(false)
  })

  it('does not run where matchMedia does not exist', () => {
    // @ts-expect-error simulating a browser without matchMedia
    window.matchMedia = undefined
    expect(backgroundSupported()).toBe(false)
  })
})
