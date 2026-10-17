import { describe, expect, it } from 'vitest'
import { cameraSway, carPosition, headingOf, loopPoints, wrap01 } from './backgroundPath'

describe('the background tracks', () => {
  it('makes a closed ring of points around the centre', () => {
    const points = loopPoints(10, -5, 20, 8)
    expect(points).toHaveLength(14)
    for (const [x, , z] of points) {
      const inside = ((x - 10) / 20) ** 2 + ((z + 5) / 8) ** 2
      expect(inside).toBeCloseTo(1)
    }
  })

  it('keeps every point on the ground', () => {
    for (const [, y] of loopPoints(0, 0, 30, 15, 0.1)) expect(y).toBeGreaterThan(0)
  })

  it('wobbles within a small share of the radius', () => {
    for (const [x, , z] of loopPoints(0, 0, 30, 15, 0.08)) {
      const ratio = Math.hypot(x / 30, z / 15)
      expect(ratio).toBeGreaterThan(0.9)
      expect(ratio).toBeLessThan(1.1)
    }
  })
})

describe('trains on a loop', () => {
  it('wraps a position back into 0 to 1', () => {
    expect(wrap01(0.25)).toBeCloseTo(0.25)
    expect(wrap01(1.25)).toBeCloseTo(0.25)
    expect(wrap01(-0.25)).toBeCloseTo(0.75)
    expect(wrap01(1)).toBe(0)
  })

  it('puts each car behind the one in front, including across the start of the loop', () => {
    expect(carPosition(0.5, 0, 0.03)).toBeCloseTo(0.5)
    expect(carPosition(0.5, 2, 0.03)).toBeCloseTo(0.44)
    expect(carPosition(0.01, 1, 0.03)).toBeCloseTo(0.98)
  })

  it('turns a car to follow the direction of the track', () => {
    // a car's length lies along x; turning it by this angle about the vertical axis must point
    // it along (x, z) = (cos h, -sin h)
    for (const [x, z] of [[1, 0], [0, -1], [-1, 0], [0, 1], [0.6, 0.8]]) {
      const heading = headingOf(x, z)
      expect(Math.cos(heading)).toBeCloseTo(x)
      expect(-Math.sin(heading)).toBeCloseTo(z)
    }
  })
})

describe('the background camera', () => {
  it('stays high above and in front of the tracks, whatever the mouse does', () => {
    for (const mouse of [-1, 0, 1]) {
      for (let s = 0; s < 600; s += 20) {
        const { position } = cameraSway(s, mouse, mouse)
        expect(position[1]).toBeGreaterThan(30)
        expect(position[2]).toBe(48)
      }
    }
  })

  it('moves only a little', () => {
    const a = cameraSway(0, 0, 0).position
    const b = cameraSway(0.1, 0, 0).position
    expect(Math.hypot(a[0] - b[0], a[1] - b[1])).toBeLessThan(0.1)
  })
})
