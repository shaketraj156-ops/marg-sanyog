// What the scene looks like at one moment of the scroll. Pure functions: the component only
// applies these numbers to the drawing, so the maths can be tested without a browser.
import { ARRIVE, DEPART } from '../../../lib/home'
import {
  CARS,
  END_OFFSET,
  PARALLAX,
  START_OFFSET,
  STATIONS,
  STATION_OFFSETS,
  TRAIN_FRONT_X,
} from './geometry'

export function clamp(value: number, low = 0, high = 1): number {
  return Math.min(high, Math.max(low, value))
}

/** 0 before `from`, 1 after `to`, a smooth S-curve in between. */
export function smoothstep(from: number, to: number, value: number): number {
  const x = clamp((value - from) / (to - from))
  return x * x * (3 - 2 * x)
}

// ----- the journey: when the train arrives at each station, and when it leaves -----
// Between a departure and the next arrival the train travels; while it stands, the world does not
// move. The times themselves live in lib/home.ts.

export interface Segment {
  from: number // time
  to: number
  fromOffset: number
  toOffset: number
  ease: string
}

/** The train's movement as a list of segments (dwell stops are segments that do not move). */
export function journey(): Segment[] {
  const segments: Segment[] = []
  let time = 0
  let offset = START_OFFSET
  STATION_OFFSETS.forEach((stationOffset, i) => {
    // brake into the station
    segments.push({
      from: time,
      to: ARRIVE[i],
      fromOffset: offset,
      toOffset: stationOffset,
      ease: i === 0 ? 'power2.out' : 'power2.inOut',
    })
    // stand at the platform
    segments.push({ from: ARRIVE[i], to: DEPART[i], fromOffset: stationOffset, toOffset: stationOffset, ease: 'none' })
    time = DEPART[i]
    offset = stationOffset
  })
  // pull away from the last station
  segments.push({ from: time, to: 1, fromOffset: offset, toOffset: END_OFFSET, ease: 'power2.in' })
  return segments
}

/** The tint over the whole scene and the lights, for a time of day mapped onto the scroll. */
export interface Frame {
  dayOpacity: number
  sunsetOpacity: number
  nightTint: number
  warmTint: number
  starsOpacity: number
  lightsOpacity: number
  cloudsOpacity: number
  sun: { x: number; y: number; opacity: number }
  moon: { x: number; y: number; opacity: number }
  translate: { mountains: number; skyline: number; hills: number; clouds: number; world: number }
}

export function frameState(t: number, offset: number): Frame {
  const sunProgress = clamp(t / 0.56)
  const moonProgress = smoothstep(0.5, 0.92, t)
  return {
    // bright morning -> golden sunset -> night, by fading layers of sky on top of each other
    dayOpacity: 1 - smoothstep(0.14, 0.42, t),
    sunsetOpacity: 1 - smoothstep(0.52, 0.8, t),
    nightTint: 0.5 * smoothstep(0.46, 0.88, t),
    warmTint: 0.26 * Math.exp(-(((t - 0.44) / 0.15) ** 2)),
    starsOpacity: smoothstep(0.52, 0.82, t),
    lightsOpacity: smoothstep(0.46, 0.8, t),
    cloudsOpacity: 0.95 * (1 - smoothstep(0.34, 0.62, t)),
    sun: {
      x: 430 + 560 * sunProgress,
      y: 140 + 640 * sunProgress ** 1.7,
      opacity: 1 - smoothstep(0.5, 0.6, t),
    },
    moon: { x: 1180 - 120 * moonProgress, y: 700 - 560 * moonProgress, opacity: smoothstep(0.5, 0.66, t) },
    translate: {
      mountains: -offset * PARALLAX.mountains,
      skyline: -offset * PARALLAX.skyline,
      hills: -offset * PARALLAX.hills,
      clouds: -offset * PARALLAX.clouds,
      world: -offset,
    },
  }
}

/** Are the doors open? Only while the train stands at a platform, a moment after it stops. */
export function doorsOpen(t: number): boolean {
  return ARRIVE.some((arrive, i) => t >= arrive + 0.012 && t <= DEPART[i] - 0.012)
}

/** A signal shows red until the train that stands at its platform starts to pull away. */
export function signalGreen(stationIndex: number, offset: number): boolean {
  return offset > STATION_OFFSETS[stationIndex] + 8
}

/** World x of the signal beyond each platform. */
export function signalX(stationIndex: number): number {
  return STATIONS[stationIndex].x + 620
}

/** Has the front of the train passed this world position? */
export function trainHasPassed(worldX: number, offset: number): boolean {
  return worldX - offset < TRAIN_FRONT_X
}

/** How far the wheels have turned, in degrees, after the world has slid `offset` units. */
export function wheelAngle(offset: number, radius = 14): number {
  return ((offset / radius) * 180) / Math.PI
}

/** A faint bounce while the train is moving: 0 when it stands. */
export function bob(offset: number, speed: number): number {
  const moving = clamp(Math.abs(speed) / 5)
  return Math.sin(offset * 0.06) * 0.9 * moving
}

export const TRAIN_WIDTH = CARS.reduce((sum, car) => sum + car.w, 0)
