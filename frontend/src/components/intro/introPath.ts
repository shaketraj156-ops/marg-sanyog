// The camera path and the train's speed in the welcome scene. Pure functions: the scene only
// applies these numbers, so the movement can be tested without WebGL.

export const INTRO_SECONDS = 4.8

export type Vec3 = [number, number, number]

export function clamp(value: number, low = 0, high = 1): number {
  return Math.min(high, Math.max(low, value))
}

export function lerp(from: number, to: number, amount: number): number {
  return from + (to - from) * amount
}

/** 0 to 1 with a gentle start and finish. */
export function easeInOut(value: number): number {
  const x = clamp(value)
  return x * x * (3 - 2 * x)
}

/** 0 before `from`, 1 after `to`, smooth in between. */
export function smoothstep(from: number, to: number, value: number): number {
  return easeInOut((value - from) / (to - from))
}

/** The train is about 39 units long and centred on x = 0, so its nose is near x = 19.5. The camera
 * starts low in front of the nose, in the headlight, and swings round and back until it sees the
 * whole train from the side. */
export function cameraAt(progress: number): { position: Vec3; target: Vec3 } {
  const e = easeInOut(progress)
  const pivotX = lerp(19, 0, e) // the point the camera circles: the nose first, then the middle
  const angle = lerp(0.12, 1.35, e) // radians from the front of the train toward the viewer's side
  const radius = lerp(14, 44, e)
  const height = lerp(2, 7.5, e)
  return {
    position: [pivotX + Math.cos(angle) * radius, height, Math.sin(angle) * radius],
    target: [lerp(19, 0, e), lerp(2.4, 2.6, e), 0],
  }
}

/** How far the track has slid past the train after `seconds`: the train speeds up as it goes. */
export function offsetAt(seconds: number): number {
  return 7 * seconds + 2.4 * seconds * seconds
}

/** How far a wheel of the given radius has turned, in radians, after the track slid `offset`. */
export function wheelAngle(offset: number, radius: number): number {
  return offset / radius
}

/** Windows and lights come on as the scene settles into dusk. */
export function glowAt(progress: number): number {
  return smoothstep(0.1, 0.75, progress)
}
