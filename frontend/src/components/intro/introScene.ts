// The welcome scene: a three-coach electric train at dusk, seen by a camera that swings from the
// headlight round to the side. Everything is built from simple shapes (no model files). The train
// stands still and the track, masts and wheels move, exactly like the homepage scene.
import {
  ACESFilmicToneMapping,
  AdditiveBlending,
  AmbientLight,
  BoxGeometry,
  BufferGeometry,
  CanvasTexture,
  Color,
  ConeGeometry,
  CylinderGeometry,
  DirectionalLight,
  DoubleSide,
  ExtrudeGeometry,
  Fog,
  Group,
  HemisphereLight,
  InstancedMesh,
  Material,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshStandardMaterial,
  type MeshStandardMaterialParameters,
  Object3D,
  PerspectiveCamera,
  PlaneGeometry,
  PointLight,
  Scene,
  Shape,
  SphereGeometry,
  SRGBColorSpace,
  WebGLRenderer,
} from 'three'
import { rng } from '../../pages/home/scene/geometry'
import { INTRO_SECONDS, cameraAt, glowAt, offsetAt, wheelAngle } from './introPath'

export interface IntroHandle {
  dispose(): void
}

interface IntroOptions {
  /** Called once, when the camera has finished its move. */
  onEnd(): void
}

const RAIL_TOP = 0.58
const WHEEL_R = 0.55
const WHEEL_Y = RAIL_TOP + WHEEL_R
const BODY_BOTTOM = 1.35
const WIRE_Y = 6.0
const SLEEPER_STEP = 0.9
const MAST_STEP = 14

function standard(color: number, extra: MeshStandardMaterialParameters = {}) {
  return new MeshStandardMaterial({ color, roughness: 0.6, metalness: 0.1, ...extra })
}

function skyTexture(): CanvasTexture {
  const canvas = document.createElement('canvas')
  canvas.width = 4
  canvas.height = 256
  const context = canvas.getContext('2d')
  if (context) {
    const gradient = context.createLinearGradient(0, 0, 0, 256)
    gradient.addColorStop(0, '#0a1230')
    gradient.addColorStop(0.45, '#4d3a78')
    gradient.addColorStop(0.75, '#e8805a')
    gradient.addColorStop(1, '#ffd29a')
    context.fillStyle = gradient
    context.fillRect(0, 0, 4, 256)
  }
  const texture = new CanvasTexture(canvas)
  texture.colorSpace = SRGBColorSpace
  return texture
}

/** A thin bar between two points in the XY plane (used for the pantograph). */
function bar(material: Material, from: [number, number], to: [number, number], thickness = 0.09): Mesh {
  const dx = to[0] - from[0]
  const dy = to[1] - from[1]
  const mesh = new Mesh(new BoxGeometry(Math.hypot(dx, dy), thickness, thickness), material)
  mesh.position.set((from[0] + to[0]) / 2, (from[1] + to[1]) / 2, 0)
  mesh.rotation.z = Math.atan2(dy, dx)
  return mesh
}

export function createIntroScene(canvas: HTMLCanvasElement, options: IntroOptions): IntroHandle {
  const renderer = new WebGLRenderer({ canvas, antialias: true })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.toneMapping = ACESFilmicToneMapping
  renderer.toneMappingExposure = 1.25

  const scene = new Scene()
  scene.background = skyTexture()
  scene.fog = new Fog(new Color('#d68a68'), 55, 230)

  const camera = new PerspectiveCamera(48, 1, 0.1, 600)

  // ----- light -----
  scene.add(new HemisphereLight(0xffd2b0, 0x3a4a66, 2.4))
  scene.add(new AmbientLight(0x4a5a8a, 0.9))
  const sun = new DirectionalLight(0xffa860, 3.2)
  sun.position.set(30, 12, 18)
  scene.add(sun)
  const fill = new DirectionalLight(0x6f8fff, 1.0)
  fill.position.set(-20, 15, -20)
  scene.add(fill)

  // ----- ground, ballast, rails -----
  const ground = new Mesh(new PlaneGeometry(700, 700), standard(0x2c5a3f, { roughness: 1 }))
  ground.rotation.x = -Math.PI / 2
  scene.add(ground)

  const ballast = new Mesh(new BoxGeometry(500, 0.3, 4.4), standard(0x6f7378, { roughness: 1 }))
  ballast.position.y = 0.15
  scene.add(ballast)

  const railMaterial = standard(0xb4bcc6, { metalness: 0.7, roughness: 0.35 })
  for (const z of [-0.72, 0.72]) {
    const rail = new Mesh(new BoxGeometry(500, 0.16, 0.14), railMaterial)
    rail.position.set(0, RAIL_TOP - 0.08, z)
    scene.add(rail)
  }

  // sleepers: evenly spaced, so sliding the group by less than one step loops seamlessly
  const sleeperCount = 560
  const sleepers = new Group()
  const sleeperMesh = new InstancedMesh(new BoxGeometry(0.34, 0.12, 3.3), standard(0x4a3b31, { roughness: 1 }), sleeperCount)
  const matrix = new Matrix4()
  for (let i = 0; i < sleeperCount; i++) {
    matrix.makeTranslation((i - sleeperCount / 2) * SLEEPER_STEP, 0.36, 0)
    sleeperMesh.setMatrixAt(i, matrix)
  }
  sleepers.add(sleeperMesh)
  scene.add(sleepers)

  // ----- overhead line: a mast every 14 units on the far side, one wire along the track -----
  const mastMaterial = standard(0x4a5461)
  const masts = new Group()
  const mastGeometry = new BoxGeometry(0.22, 7.4, 0.22)
  const armGeometry = new BoxGeometry(0.16, 0.16, 3.4)
  for (let i = -20; i <= 20; i++) {
    const mast = new Mesh(mastGeometry, mastMaterial)
    mast.position.set(i * MAST_STEP, 3.7, -3.2)
    const arm = new Mesh(armGeometry, mastMaterial)
    arm.position.set(i * MAST_STEP, WIRE_Y + 0.5, -1.5)
    masts.add(mast, arm)
  }
  scene.add(masts)
  const wire = new Mesh(new BoxGeometry(600, 0.05, 0.05), standard(0x20262e))
  wire.position.set(0, WIRE_Y, 0)
  scene.add(wire)

  // ----- far scenery: a skyline with lit windows, and low mountains -----
  const random = rng(7)
  const skyline = new Group()
  const buildingMaterial = standard(0x3a4a70, { roughness: 1 })
  const windowMaterial = new MeshBasicMaterial({ color: 0xffd98a, transparent: true, opacity: 0, fog: false })
  const windowGeometry = new BoxGeometry(0.55, 0.7, 0.1)
  const windows = new InstancedMesh(windowGeometry, windowMaterial, 900)
  let windowCount = 0
  for (let x = -260; x < 260; x += 3 + random() * 6) {
    const width = 3 + random() * 6
    const height = 5 + random() * 24 * (0.4 + random())
    const depth = -48 - random() * 30
    const building = new Mesh(new BoxGeometry(width, height, 5), buildingMaterial)
    building.position.set(x, height / 2, depth)
    skyline.add(building)
    const rows = Math.floor(height / 2.2)
    const cols = Math.floor(width / 1.4)
    for (let row = 0; row < rows && windowCount < 900; row++) {
      for (let col = 0; col < cols && windowCount < 900; col++) {
        if (random() < 0.55) continue
        matrix.makeTranslation(x - width / 2 + 0.9 + col * 1.4, 1.6 + row * 2.2, depth + 2.55)
        windows.setMatrixAt(windowCount++, matrix)
      }
    }
  }
  windows.count = windowCount
  skyline.add(windows)
  scene.add(skyline)

  const mountainMaterial = standard(0x4a5b86, { roughness: 1 })
  for (let i = 0; i < 9; i++) {
    const mountain = new Mesh(new ConeGeometry(26 + random() * 22, 20 + random() * 26, 5), mountainMaterial)
    mountain.position.set(-210 + i * 52 + random() * 20, 8, -130 - random() * 30)
    scene.add(mountain)
  }

  // ----- the train: a locomotive pulling three coaches, heading toward +x -----
  const glowMaterials: MeshStandardMaterial[] = []
  const wheels: Mesh[] = []
  const wheelGeometry = new CylinderGeometry(WHEEL_R, WHEEL_R, 0.14, 20)
  wheelGeometry.rotateX(Math.PI / 2) // the wheel's axis points along z
  const spokeGeometry = new BoxGeometry(WHEEL_R * 1.7, 0.1, 0.18)
  const wheelMaterial = standard(0x2a323d, { metalness: 0.5 })
  const spokeMaterial = standard(0x8d99a8, { metalness: 0.6 })

  function addWheels(car: Group, bogieXs: number[]) {
    for (const bx of bogieXs) {
      for (const dx of [-0.6, 0.6]) {
        for (const z of [-0.95, 0.95]) {
          const wheel = new Mesh(wheelGeometry, wheelMaterial)
          wheel.position.set(bx + dx, WHEEL_Y, z)
          wheel.add(new Mesh(spokeGeometry, spokeMaterial))
          car.add(wheel)
          wheels.push(wheel)
        }
      }
    }
  }

  function glowing(): MeshStandardMaterial {
    const material = standard(0x20384f, { emissive: new Color(0xffd78a), emissiveIntensity: 0, roughness: 0.3 })
    glowMaterials.push(material)
    return material
  }

  const coachBody = standard(0xefe9da)
  const coachBand = standard(0x1b64c0)
  const coachStripe = standard(0xf2a900)
  const roofMaterial = standard(0xaeb6c1)
  const underframe = standard(0x2f3742)
  const coachWindow = glowing()

  function makeCoach(): Group {
    const car = new Group()
    const body = new Mesh(new BoxGeometry(9.6, 2.7, 2.9), coachBody)
    body.position.y = BODY_BOTTOM + 1.35
    const band = new Mesh(new BoxGeometry(9.64, 0.7, 2.94), coachBand)
    band.position.y = BODY_BOTTOM + 0.35
    const stripe = new Mesh(new BoxGeometry(9.66, 0.09, 2.96), coachStripe)
    stripe.position.y = BODY_BOTTOM + 0.78
    const roof = new Mesh(new BoxGeometry(9.3, 0.25, 2.6), roofMaterial)
    roof.position.y = BODY_BOTTOM + 2.82
    const frame = new Mesh(new BoxGeometry(8.8, 0.34, 2.4), underframe)
    frame.position.y = BODY_BOTTOM - 0.1
    car.add(body, band, stripe, roof, frame)
    const windowGeometry3 = new BoxGeometry(0.95, 0.85, 0.06)
    for (let i = 0; i < 7; i++) {
      for (const side of [-1, 1]) {
        const pane = new Mesh(windowGeometry3, coachWindow)
        pane.position.set(-3.6 + i * 1.2, BODY_BOTTOM + 1.75, side * 1.46)
        car.add(pane)
      }
    }
    addWheels(car, [-3.1, 3.1])
    return car
  }

  const locoBody = standard(0x1b64c0, { roughness: 0.45 })
  const locoWhite = standard(0xf6f2e6)
  const cabGlass = glowing()
  const dark = standard(0x232a33)

  function makeLoco(): Group {
    const car = new Group()
    // side profile: a flat roof, a sloping nose
    const profile = new Shape()
    profile.moveTo(0, 0)
    profile.lineTo(8.6, 0)
    profile.lineTo(8.6, 1.5)
    profile.lineTo(7.3, 3.1)
    profile.lineTo(0.2, 3.1)
    profile.lineTo(0, 2.9)
    profile.closePath()
    const shell = new ExtrudeGeometry(profile, { depth: 2.9, bevelEnabled: false })
    shell.translate(-4.3, BODY_BOTTOM, -1.45)
    car.add(new Mesh(shell, locoBody))

    const stripe = new Mesh(new BoxGeometry(8.64, 0.14, 2.94), locoWhite)
    stripe.position.set(0, BODY_BOTTOM + 0.95, 0)
    const amber = new Mesh(new BoxGeometry(8.66, 0.08, 2.96), coachStripe)
    amber.position.set(0, BODY_BOTTOM + 0.72, 0)
    car.add(stripe, amber)

    // windscreen on the sloping nose, and the cab side windows
    const screen = new Mesh(new BoxGeometry(0.06, 1.7, 2.3), cabGlass)
    screen.position.set(3.68, BODY_BOTTOM + 2.3, 0) // the middle of the slope, a touch outside it
    screen.rotation.z = 0.683
    car.add(screen)
    for (const side of [-1, 1]) {
      const cab = new Mesh(new BoxGeometry(1.5, 0.95, 0.06), cabGlass)
      cab.position.set(2.4, BODY_BOTTOM + 2.15, side * 1.48)
      car.add(cab)
    }

    // pantograph reaching the contact wire
    const pantograph = new Group()
    pantograph.add(
      bar(dark, [-0.7, 4.3], [0.2, 5.1]),
      bar(dark, [0.2, 5.1], [-0.1, WIRE_Y - 0.05]),
      bar(dark, [0.6, 4.3], [-0.1, 5.1]),
    )
    const strip = new Mesh(new BoxGeometry(0.14, 0.12, 1.7), dark)
    strip.position.set(-0.1, WIRE_Y - 0.03, 0)
    pantograph.add(strip)
    pantograph.position.x = -1.4
    car.add(pantograph)

    addWheels(car, [-2.6, 2.4])
    return car
  }

  const train = new Group()
  const cars: { group: Group; length: number }[] = [
    { group: makeCoach(), length: 9.6 },
    { group: makeCoach(), length: 9.6 },
    { group: makeCoach(), length: 9.6 },
    { group: makeLoco(), length: 8.6 },
  ]
  const gap = 0.55
  const total = cars.reduce((sum, c) => sum + c.length, 0) + gap * (cars.length - 1)
  let cursor = -total / 2
  const coupler = new BoxGeometry(gap + 0.2, 0.3, 0.4)
  cars.forEach((car, index) => {
    car.group.position.x = cursor + car.length / 2
    train.add(car.group)
    if (index < cars.length - 1) {
      const link = new Mesh(coupler, underframe)
      link.position.set(cursor + car.length + gap / 2, BODY_BOTTOM + 0.4, 0)
      train.add(link)
    }
    cursor += car.length + gap
  })
  scene.add(train)

  // headlight: a glowing lamp, a soft cone of light and a point light on the track ahead
  const noseX = total / 2
  const lamp = new Mesh(new SphereGeometry(0.22, 12, 12), new MeshBasicMaterial({ color: 0xfff6c8 }))
  lamp.position.set(noseX + 0.05, BODY_BOTTOM + 1.15, 0)
  const beamMaterial = new MeshBasicMaterial({
    color: 0xfff3b8,
    transparent: true,
    opacity: 0,
    blending: AdditiveBlending,
    depthWrite: false,
    side: DoubleSide,
    fog: false,
  })
  const beam = new Mesh(new ConeGeometry(2.0, 15, 28, 1, true), beamMaterial)
  beam.rotation.z = Math.PI / 2 // the point faces back at the lamp, the wide end ahead
  beam.position.set(noseX + 7.5, BODY_BOTTOM + 1.0, 0)
  const headlight = new PointLight(0xffe2a0, 0, 26, 1.6)
  headlight.position.set(noseX + 2, BODY_BOTTOM + 1.2, 0)
  train.add(lamp, beam, headlight)

  // ----- size and drawing -----
  function resize() {
    const width = canvas.clientWidth || window.innerWidth
    const height = canvas.clientHeight || window.innerHeight
    renderer.setSize(width, height, false)
    camera.aspect = width / height
    camera.updateProjectionMatrix()
  }
  resize()
  const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(resize) : null
  observer?.observe(canvas)

  const started = performance.now()
  let frame = 0
  let ended = false
  let disposed = false

  function draw() {
    if (disposed) return
    const seconds = (performance.now() - started) / 1000
    const progress = Math.min(1, seconds / INTRO_SECONDS)
    const offset = offsetAt(seconds)

    sleepers.position.x = -(offset % SLEEPER_STEP)
    masts.position.x = -(offset % MAST_STEP)
    skyline.position.x = -offset * 0.04
    for (const wheel of wheels) wheel.rotation.z = -wheelAngle(offset, WHEEL_R)
    train.position.y = Math.sin(offset * 1.1) * 0.018 * (1 - progress * 0.6)

    const glow = glowAt(progress)
    for (const material of glowMaterials) material.emissiveIntensity = 0.15 + glow * 1.5
    windowMaterial.opacity = glow * 0.9
    beamMaterial.opacity = glow * 0.1
    headlight.intensity = glow * 90

    const path = cameraAt(progress)
    camera.position.set(...path.position)
    camera.lookAt(...path.target)
    renderer.render(scene, camera)

    if (progress >= 1) {
      if (!ended) {
        ended = true
        options.onEnd()
      }
      return // the last picture stays while the page fades out
    }
    frame = requestAnimationFrame(draw)
  }
  frame = requestAnimationFrame(draw)

  return {
    dispose() {
      if (disposed) return
      disposed = true
      cancelAnimationFrame(frame)
      observer?.disconnect()
      const geometries = new Set<BufferGeometry>()
      const materials = new Set<Material>()
      scene.traverse((object: Object3D) => {
        const mesh = object as Mesh
        if (mesh.geometry) geometries.add(mesh.geometry)
        const material = mesh.material
        if (Array.isArray(material)) material.forEach((m) => materials.add(m))
        else if (material) materials.add(material)
      })
      geometries.forEach((g) => g.dispose())
      materials.forEach((m) => m.dispose())
      ;(scene.background as CanvasTexture | null)?.dispose()
      renderer.dispose()
      renderer.forceContextLoss()
    },
  }
}
