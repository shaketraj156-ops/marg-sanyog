// Shapes and positions of the homepage scene. Everything is in one coordinate system (the SVG
// viewBox): 1600 wide, 900 high, with the rails near the bottom. The train stays at the centre of
// the screen and the world slides past it, so "driving" is the world moving, not the train.

export const VIEW_W = 1600
export const VIEW_H = 900

export const RAIL_Y = 748 // top of the rails
export const WIRE_Y = 598 // the contact wire the pantograph touches
export const TRAIN_CENTER_X = 800

// ----- the train: three coaches pulled by an electric locomotive, heading right -----
export const COACH_W = 205
export const LOCO_W = 250
export const CAR_GAP = 8
export const COACHES = 3
export const CAR_TOP = 640
export const CAR_BOTTOM = 722
export const WHEEL_Y = 734

export interface Car {
  kind: 'coach' | 'loco'
  x: number
  w: number
}

export const TRAIN_W = COACHES * COACH_W + COACHES * CAR_GAP + LOCO_W
export const TRAIN_X0 = TRAIN_CENTER_X - TRAIN_W / 2

export const CARS: Car[] = [
  ...Array.from({ length: COACHES }, (_, i): Car => ({
    kind: 'coach',
    x: TRAIN_X0 + i * (COACH_W + CAR_GAP),
    w: COACH_W,
  })),
  { kind: 'loco', x: TRAIN_X0 + COACHES * (COACH_W + CAR_GAP), w: LOCO_W },
]
export const TRAIN_FRONT_X = TRAIN_X0 + TRAIN_W

/** Centres of the two wheels of each bogie, for every car. */
export function wheelCentres(): number[] {
  const centres: number[] = []
  for (const car of CARS) {
    const inset = car.kind === 'loco' ? 58 : 36
    const spread = car.kind === 'loco' ? 16 : 13
    for (const bogie of [car.x + inset, car.x + car.w - inset]) {
      centres.push(bogie - spread, bogie + spread)
    }
  }
  return centres
}

// ----- the four stations -----
export const STATIONS = [
  { name: 'REQUEST', number: 1, x: 1000 },
  { name: 'PLAN', number: 2, x: 3000 },
  { name: 'REVIEW', number: 3, x: 5000 },
  { name: 'PUBLISH', number: 4, x: 7000 },
]
export const PLATFORM_W = 1000

/** How far the world has slid when the train stands at station i (its centre at the platform's). */
export const STATION_OFFSETS = STATIONS.map((s) => s.x - TRAIN_CENTER_X)
export const START_OFFSET = -300
export const END_OFFSET = 7000

// ----- how far each background layer moves compared with the world (parallax) -----
export const PARALLAX = { mountains: 0.06, skyline: 0.16, hills: 0.32, clouds: 0.04 }

// ----- small seeded random numbers, so the scenery is the same on every visit -----
export function rng(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = a
    t = Math.imul(t ^ (t >>> 15), t | 1)
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61)
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** The span a layer must cover so no edge ever shows: from just left of the screen to just right
 * of it after the world has moved all the way. */
export function layerSpan(factor: number): { from: number; to: number } {
  const margin = 700 // extra room for very wide windows
  return { from: -margin - Math.max(0, -START_OFFSET * factor), to: VIEW_W + margin + END_OFFSET * factor }
}

// ----- scenery generators -----
export interface Building {
  x: number
  w: number
  h: number
}

export function skyline(seed: number, from: number, to: number): Building[] {
  const random = rng(seed)
  const buildings: Building[] = []
  let x = from
  while (x < to) {
    const w = 38 + random() * 58
    // taller towers appear in clusters, with low buildings between
    const cluster = Math.sin(x / 520) * 0.5 + 0.5
    const h = 50 + random() * 70 + cluster * (random() * 150)
    buildings.push({ x, w, h })
    x += w + random() * 6
  }
  return buildings
}

/** A ridge line as an SVG path, closed along the bottom. */
export function ridge(seed: number, from: number, to: number, base: number, low: number, high: number): string {
  const random = rng(seed)
  const phases = [random() * 6, random() * 6, random() * 6]
  const step = 40
  const points: string[] = []
  for (let x = from; x <= to + step; x += step) {
    const wave =
      Math.sin(x / 310 + phases[0]) * 0.5 + Math.sin(x / 130 + phases[1]) * 0.3 + Math.sin(x / 57 + phases[2]) * 0.2
    const y = base - low - (wave * 0.5 + 0.5) * (high - low)
    points.push(`${x},${y.toFixed(1)}`)
  }
  return `M ${from},${base + 400} L ${points.join(' L ')} L ${to + step},${base + 400} Z`
}

export interface Tree {
  x: number
  y: number
  r: number
  shade: number
}

export function trees(seed: number, from: number, to: number, groundY: number): Tree[] {
  const random = rng(seed)
  const out: Tree[] = []
  for (let x = from; x < to; x += 26 + random() * 90) {
    out.push({ x, y: groundY - random() * 14, r: 12 + random() * 16, shade: random() })
  }
  return out
}

export interface Star {
  x: number
  y: number
  r: number
  delay: number
}

export function stars(seed: number, count: number): Star[] {
  const random = rng(seed)
  return Array.from({ length: count }, () => ({
    x: -500 + random() * (VIEW_W + 1000),
    y: -700 + random() * 1150,
    r: 0.8 + random() * 1.7,
    delay: random() * 4,
  }))
}

export interface Cloud {
  x: number
  y: number
  scale: number
}

export function clouds(seed: number, from: number, to: number): Cloud[] {
  const random = rng(seed)
  const out: Cloud[] = []
  for (let x = from; x < to; x += 330 + random() * 380) {
    out.push({ x, y: 90 + random() * 230, scale: 0.7 + random() * 0.9 })
  }
  return out
}

// ----- overhead line: a mast every 360 units, wire hung between them -----
export const MAST_SPACING = 360

export function mastPositions(from: number, to: number): number[] {
  const first = Math.ceil(from / MAST_SPACING) * MAST_SPACING
  const out: number[] = []
  for (let x = first; x <= to; x += MAST_SPACING) out.push(x)
  return out
}

/** The messenger wire sags between masts; the contact wire below it is straight. */
export function messengerWire(masts: number[]): string {
  if (masts.length < 2) return ''
  const top = WIRE_Y - 26
  let d = `M ${masts[0]},${top}`
  for (let i = 1; i < masts.length; i++) {
    const mid = (masts[i - 1] + masts[i]) / 2
    d += ` Q ${mid},${top + 22} ${masts[i]},${top}`
  }
  return d
}

/** Short hangers joining the messenger wire to the contact wire. */
export function droppers(masts: number[]): { x: number; y1: number; y2: number }[] {
  const out: { x: number; y1: number; y2: number }[] = []
  const top = WIRE_Y - 26
  for (let i = 1; i < masts.length; i++) {
    const a = masts[i - 1]
    const b = masts[i]
    for (const share of [0.25, 0.5, 0.75]) {
      const x = a + (b - a) * share
      const sag = 22 * 4 * share * (1 - share) // the curve's depth at this point
      out.push({ x, y1: top + sag, y2: WIRE_Y })
    }
  }
  return out
}
