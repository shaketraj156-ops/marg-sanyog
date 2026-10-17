// Shapes and movement for the background railway. Pure functions, so they can be tested without WebGL.

export type Vec3 = [number, number, number]

/** A closed loop on the ground: an ellipse with a gentle wobble, as points for a smooth curve. */
export function loopPoints(centerX: number, centerZ: number, radiusX: number, radiusZ: number, wobble = 0, count = 14): Vec3[] {
  return Array.from({ length: count }, (_, i) => {
    const angle = (i / count) * Math.PI * 2
    const bend = 1 + wobble * Math.sin(angle * 3 + centerX)
    return [centerX + Math.cos(angle) * radiusX * bend, 0.2, centerZ + Math.sin(angle) * radiusZ * bend]
  })
}

/** Keeps a position along a closed loop between 0 (inclusive) and 1 (exclusive). */
export function wrap01(value: number): number {
  return ((value % 1) + 1) % 1
}

/** Where along the loop car number `index` of a train is, when the front car is at `front`.
 * `gap` is the share of the loop between neighbouring cars. */
export function carPosition(front: number, index: number, gap: number): number {
  return wrap01(front - index * gap)
}

/** The angle that turns a car's length (its x axis) to follow a direction on the ground. */
export function headingOf(tangentX: number, tangentZ: number): number {
  return Math.atan2(-tangentZ, tangentX)
}

/** A gentle sway of the camera, with a small push from the mouse (both -1 to 1). */
export function cameraSway(seconds: number, mouseX: number, mouseY: number): { position: Vec3; target: Vec3 } {
  return {
    position: [Math.sin(seconds * 0.05) * 6 + mouseX * 4, 36 + Math.cos(seconds * 0.04) * 2 - mouseY * 2, 48],
    target: [0, 0, 0],
  }
}
