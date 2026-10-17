import { describe, expect, it } from 'vitest'
import { ARRIVE, DEPART } from '../../../lib/home'
import { bob, doorsOpen, frameState, journey, signalGreen, smoothstep, wheelAngle } from './frame'
import {
  CARS,
  END_OFFSET,
  PLATFORM_W,
  STATIONS,
  STATION_OFFSETS,
  START_OFFSET,
  TRAIN_CENTER_X,
  TRAIN_FRONT_X,
  TRAIN_X0,
  clouds,
  layerSpan,
  mastPositions,
  ridge,
  skyline,
  wheelCentres,
} from './geometry'

describe('the train', () => {
  it('is centred on the screen and fits inside a platform', () => {
    const width = TRAIN_FRONT_X - TRAIN_X0
    expect(TRAIN_X0 + width / 2).toBeCloseTo(TRAIN_CENTER_X)
    expect(width).toBeLessThan(PLATFORM_W)
  })

  it('has cars that do not overlap and two wheels per bogie', () => {
    CARS.slice(1).forEach((car, i) => expect(car.x).toBeGreaterThan(CARS[i].x + CARS[i].w))
    expect(wheelCentres()).toHaveLength(CARS.length * 4)
  })
})

describe('the journey', () => {
  const segments = journey()

  it('covers the whole scroll with no gaps', () => {
    expect(segments[0].from).toBe(0)
    expect(segments[segments.length - 1].to).toBe(1)
    segments.slice(1).forEach((s, i) => expect(s.from).toBeCloseTo(segments[i].to, 9))
  })

  it('stands still at every platform for the dwell time, and ends at the end of the line', () => {
    STATION_OFFSETS.forEach((offset, i) => {
      const stand = segments.find((s) => s.from === ARRIVE[i] && s.to === DEPART[i])!
      expect(stand.fromOffset).toBe(offset)
      expect(stand.toOffset).toBe(offset)
    })
    expect(segments[0].fromOffset).toBe(START_OFFSET)
    expect(segments[segments.length - 1].toOffset).toBe(END_OFFSET)
  })

  it('never goes backwards', () => {
    segments.forEach((s) => expect(s.toOffset).toBeGreaterThanOrEqual(s.fromOffset))
  })

  it('puts each station in the middle of the screen when the train stops', () => {
    STATIONS.forEach((station, i) => expect(station.x - STATION_OFFSETS[i]).toBe(TRAIN_CENTER_X))
  })
})

describe('the time of day', () => {
  it('is bright at the start, dark at the end', () => {
    const start = frameState(0, START_OFFSET)
    const end = frameState(1, END_OFFSET)
    expect(start.dayOpacity).toBe(1)
    expect(start.nightTint).toBe(0)
    expect(start.lightsOpacity).toBe(0)
    expect(end.dayOpacity).toBe(0)
    expect(end.sunsetOpacity).toBe(0)
    expect(end.starsOpacity).toBe(1)
    expect(end.lightsOpacity).toBe(1)
  })

  it('changes smoothly: every value moves in one direction (the warm tint peaks once)', () => {
    let previous = frameState(0, 0)
    for (let t = 0.01; t <= 1.0001; t += 0.01) {
      const now = frameState(t, 0)
      expect(now.dayOpacity).toBeLessThanOrEqual(previous.dayOpacity + 1e-9)
      expect(now.sunsetOpacity).toBeLessThanOrEqual(previous.sunsetOpacity + 1e-9)
      expect(now.nightTint).toBeGreaterThanOrEqual(previous.nightTint - 1e-9)
      expect(now.starsOpacity).toBeGreaterThanOrEqual(previous.starsOpacity - 1e-9)
      previous = now
    }
  })

  it('keeps the sky clear: the night tint never covers it fully', () => {
    for (let t = 0; t <= 1; t += 0.05) expect(frameState(t, 0).nightTint).toBeLessThanOrEqual(0.5)
  })

  it('moves far layers slower than near ones', () => {
    const { translate } = frameState(0.5, 1000)
    expect(Math.abs(translate.mountains)).toBeLessThan(Math.abs(translate.skyline))
    expect(Math.abs(translate.skyline)).toBeLessThan(Math.abs(translate.hills))
    expect(Math.abs(translate.hills)).toBeLessThan(Math.abs(translate.world))
  })

  it('smoothstep is 0 before, 1 after, and between in the middle', () => {
    expect(smoothstep(0.2, 0.4, 0.1)).toBe(0)
    expect(smoothstep(0.2, 0.4, 0.5)).toBe(1)
    expect(smoothstep(0.2, 0.4, 0.3)).toBeCloseTo(0.5)
  })
})

describe('doors, signals and wheels', () => {
  it('opens the doors only while the train stands', () => {
    ARRIVE.forEach((arrive, i) => {
      expect(doorsOpen(arrive - 0.01)).toBe(false)
      expect(doorsOpen((arrive + DEPART[i]) / 2)).toBe(true)
      expect(doorsOpen(DEPART[i] + 0.01)).toBe(false)
    })
  })

  it('shows red until the train pulls away from the platform', () => {
    expect(signalGreen(0, STATION_OFFSETS[0])).toBe(false)
    expect(signalGreen(0, STATION_OFFSETS[0] + 200)).toBe(true)
    expect(signalGreen(1, STATION_OFFSETS[0] + 200)).toBe(false)
  })

  it('turns the wheels with the distance and bounces only while moving', () => {
    expect(wheelAngle(0)).toBe(0)
    expect(wheelAngle(200)).toBeGreaterThan(wheelAngle(100))
    expect(bob(123, 0)).toBe(0)
    expect(Math.abs(bob(123, 8))).toBeGreaterThan(0)
  })
})

describe('the scenery', () => {
  it('is the same on every visit', () => {
    expect(skyline(5, 0, 2000)).toEqual(skyline(5, 0, 2000))
    expect(ridge(11, 0, 2000, 744, 150, 330)).toBe(ridge(11, 0, 2000, 744, 150, 330))
    expect(clouds(3, 0, 3000)).toEqual(clouds(3, 0, 3000))
  })

  it('covers the screen at both ends of the journey, for every layer', () => {
    for (const factor of [0.04, 0.06, 0.16, 0.32]) {
      const { from, to } = layerSpan(factor)
      const leftEdge = START_OFFSET * factor // layer shifts by -offset*factor
      expect(from + -START_OFFSET * factor).toBeLessThanOrEqual(0) // left edge visible start
      expect(to - END_OFFSET * factor).toBeGreaterThanOrEqual(1600) // right edge at the end
      expect(leftEdge).toBeLessThan(0)
    }
  })

  it('puts masts on a regular grid, including the line under every station', () => {
    const masts = mastPositions(-500, 8000)
    masts.slice(1).forEach((x, i) => expect(x - masts[i]).toBe(360))
    expect(masts[0]).toBeGreaterThanOrEqual(-500)
  })
})
