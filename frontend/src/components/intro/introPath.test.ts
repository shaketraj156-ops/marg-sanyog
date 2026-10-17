import { describe, expect, it } from 'vitest'
import { INTRO_SECONDS, cameraAt, easeInOut, glowAt, offsetAt, wheelAngle } from './introPath'

const distance = (a: number[], b: number[]) => Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2])

describe('the welcome camera', () => {
  it('starts in front of the train, low and close, and ends beside it, higher and further away', () => {
    const start = cameraAt(0)
    const end = cameraAt(1)
    expect(start.position[0]).toBeGreaterThan(19.5 + 5) // clear of the nose (about x = 19.5), not inside the train
    expect(Math.abs(start.position[2])).toBeLessThan(5)
    expect(end.position[2]).toBeGreaterThan(30) // far enough out to see the whole 39-unit train
    expect(end.position[1]).toBeGreaterThan(start.position[1])
  })

  it('never puts the camera inside the train', () => {
    for (let p = 0; p <= 1; p += 0.01) {
      const [x, y, z] = cameraAt(p).position
      const insideTrain = Math.abs(x) < 19.6 && Math.abs(z) < 2 && y < 5
      expect(insideTrain).toBe(false)
    }
  })

  it('moves smoothly: no jump between neighbouring moments', () => {
    let previous = cameraAt(0).position
    for (let p = 0.01; p <= 1.0001; p += 0.01) {
      const now = cameraAt(p).position
      expect(distance(previous, now)).toBeLessThan(1)
      previous = now
    }
  })

  it('stays put outside the 0 to 1 range', () => {
    expect(cameraAt(-1)).toEqual(cameraAt(0))
    expect(cameraAt(2)).toEqual(cameraAt(1))
  })

  it('never looks below the ground or too high', () => {
    for (let p = 0; p <= 1; p += 0.05) {
      const { position, target } = cameraAt(p)
      expect(position[1]).toBeGreaterThan(1)
      expect(target[1]).toBeGreaterThan(1)
      expect(target[1]).toBeLessThan(4)
    }
  })
})

describe('the welcome movement', () => {
  it('eases in and out', () => {
    expect(easeInOut(0)).toBe(0)
    expect(easeInOut(1)).toBe(1)
    expect(easeInOut(0.5)).toBeCloseTo(0.5)
    expect(easeInOut(0.1)).toBeLessThan(0.1)
  })

  it('speeds the train up and never reverses', () => {
    let previous = offsetAt(0)
    let previousStep = 0
    for (let s = 0.1; s <= INTRO_SECONDS; s += 0.1) {
      const now = offsetAt(s)
      const step = now - previous
      expect(step).toBeGreaterThan(0)
      expect(step).toBeGreaterThanOrEqual(previousStep - 1e-9)
      previous = now
      previousStep = step
    }
  })

  it('keeps each frame under one sleeper step at 60 frames a second, so the track does not seem to flicker', () => {
    const speedAtEnd = offsetAt(INTRO_SECONDS) - offsetAt(INTRO_SECONDS - 1 / 60)
    expect(speedAtEnd).toBeLessThan(0.9)
  })

  it('turns the wheels in step with the track', () => {
    expect(wheelAngle(0, 0.55)).toBe(0)
    expect(wheelAngle(0.55, 0.55)).toBeCloseTo(1)
  })

  it('lights up gradually, from off to fully on', () => {
    expect(glowAt(0)).toBe(0)
    expect(glowAt(1)).toBe(1)
    expect(glowAt(0.4)).toBeGreaterThan(0)
    expect(glowAt(0.4)).toBeLessThan(1)
  })
})
