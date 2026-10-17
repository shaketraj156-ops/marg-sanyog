import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { clearIntroFlag, markIntroPending, shouldPlayIntro } from './intro'

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
  sessionStorage.clear()
  stubWebdriver(false)
})

afterEach(() => {
  window.matchMedia = original
  sessionStorage.clear()
})

describe('the welcome after signing in', () => {
  it('does not play unless a sign-in just happened', () => {
    stubMotion(false)
    expect(shouldPlayIntro()).toBe(false)
  })

  it('plays after a sign-in', () => {
    stubMotion(false)
    markIntroPending()
    expect(shouldPlayIntro()).toBe(true)
  })

  it('stops playing once the flag is cleared (so a reload does not repeat it)', () => {
    stubMotion(false)
    markIntroPending()
    clearIntroFlag()
    expect(shouldPlayIntro()).toBe(false)
  })

  it('is skipped for people who asked for less motion', () => {
    stubMotion(true)
    markIntroPending()
    expect(shouldPlayIntro()).toBe(false)
  })

  it('is skipped for automated browsers, which the overlay would block', () => {
    stubMotion(false)
    stubWebdriver(true)
    markIntroPending()
    expect(shouldPlayIntro()).toBe(false)
  })

  it('is skipped where matchMedia does not exist', () => {
    // @ts-expect-error simulating a browser without matchMedia
    window.matchMedia = undefined
    markIntroPending()
    expect(shouldPlayIntro()).toBe(false)
  })
})
