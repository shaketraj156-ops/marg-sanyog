import { afterEach, describe, expect, it } from 'vitest'
import { ARRIVE, DEPART, canAnimate, stepForProgress } from './home'

describe('which station card to show', () => {
  it('starts with the introduction', () => {
    expect(stepForProgress(0)).toBe(-1)
    expect(stepForProgress(0.05)).toBe(-1)
  })

  it('shows each station a little before the train reaches it', () => {
    ARRIVE.forEach((arrive, index) => {
      expect(stepForProgress(arrive - 0.05)).toBe(index - 1)
      expect(stepForProgress(arrive - 0.03)).toBe(index)
      expect(stepForProgress(arrive)).toBe(index)
    })
  })

  it('stays on the last station to the end', () => {
    expect(stepForProgress(1)).toBe(ARRIVE.length - 1)
  })

  it('never goes back while the progress only grows', () => {
    let last = -1
    for (let p = 0; p <= 1; p += 0.01) {
      const step = stepForProgress(p)
      expect(step).toBeGreaterThanOrEqual(last)
      last = step
    }
  })

  it('has four stops in order, each with a pause, inside the journey', () => {
    expect(ARRIVE).toHaveLength(4)
    expect(DEPART).toHaveLength(4)
    ARRIVE.forEach((arrive, i) => {
      expect(DEPART[i]).toBeGreaterThan(arrive) // the train stands for a while
      if (i > 0) expect(arrive).toBeGreaterThan(DEPART[i - 1]) // and travels between stops
    })
    expect(ARRIVE[0]).toBeGreaterThan(0)
    expect(DEPART[3]).toBeLessThan(1)
  })
})

describe('whether the train animation runs', () => {
  const original = window.matchMedia
  afterEach(() => {
    window.matchMedia = original
  })

  function media(reduced: boolean, wide: boolean) {
    window.matchMedia = ((query: string) => ({
      matches: query.includes('prefers-reduced-motion') ? reduced : query.includes('min-width') ? wide : false,
    })) as unknown as typeof window.matchMedia
  }

  it('runs on a wide screen when motion is allowed', () => {
    media(false, true)
    expect(canAnimate()).toBe(true)
  })

  it('does not run for people who asked for less motion', () => {
    media(true, true)
    expect(canAnimate()).toBe(false)
  })

  it('does not run on a narrow screen', () => {
    media(false, false)
    expect(canAnimate()).toBe(false)
  })

  it('does not run where the browser cannot tell (it falls back to the plain page)', () => {
    // @ts-expect-error simulating a browser without matchMedia
    window.matchMedia = undefined
    expect(canAnimate()).toBe(false)
  })
})
