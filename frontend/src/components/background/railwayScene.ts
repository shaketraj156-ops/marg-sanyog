// The background railway: a bird's-eye view of three looping tracks with small trains, and four
// slowly turning markers (blue, amber, green, purple, the colours used on the dashboard) over the
// stations. It is meant to stay calm and low in contrast, so the pages in front stay easy to read.
import {
  AmbientLight,
  BoxGeometry,
  BufferGeometry,
  CatmullRomCurve3,
  CylinderGeometry,
  DirectionalLight,
  Fog,
  GridHelper,
  Group,
  HemisphereLight,
  IcosahedronGeometry,
  Material,
  Mesh,
  MeshStandardMaterial,
  type MeshStandardMaterialParameters,
  Object3D,
  PerspectiveCamera,
  Scene,
  TubeGeometry,
  Vector3,
  WebGLRenderer,
} from 'three'
import { cameraSway, carPosition, headingOf, loopPoints } from './backgroundPath'

export interface BackgroundHandle {
  dispose(): void
}

const FRAME_MS = 1000 / 30 // 30 frames a second is plenty for something this slow

interface TrainSpec {
  curve: CatmullRomCurve3
  speed: number // ground units a second
  coaches: number
  front: number // where the front car starts (0 to 1)
}

function material(color: number, extra: MeshStandardMaterialParameters = {}) {
  return new MeshStandardMaterial({ color, roughness: 0.55, metalness: 0.1, ...extra })
}

export function createBackgroundScene(canvas: HTMLCanvasElement): BackgroundHandle {
  const renderer = new WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: 'low-power' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  renderer.setClearColor(0x000000, 0)

  const scene = new Scene()
  scene.fog = new Fog(0xf3f5f8, 70, 150)
  const camera = new PerspectiveCamera(42, 1, 0.1, 400)

  scene.add(new HemisphereLight(0xffffff, 0xaab8d0, 1.7))
  scene.add(new AmbientLight(0xffffff, 0.5))
  const sun = new DirectionalLight(0xffffff, 1.5)
  sun.position.set(20, 40, 10)
  scene.add(sun)

  const grid = new GridHelper(240, 60, 0xb9c8de, 0xd5deec)
  grid.position.y = 0
  scene.add(grid)

  // ----- three looping tracks -----
  const loops = [
    new CatmullRomCurve3(loopPoints(0, 0, 40, 20, 0.05).map((p) => new Vector3(...p)), true),
    new CatmullRomCurve3(loopPoints(-10, -3, 24, 11, 0.07).map((p) => new Vector3(...p)), true),
    new CatmullRomCurve3(loopPoints(24, 9, 17, 8, 0.06).map((p) => new Vector3(...p)), true),
  ]
  const trackMaterial = material(0x8fa6c6, { roughness: 0.8 })
  for (const curve of loops) scene.add(new Mesh(new TubeGeometry(curve, 240, 0.2, 6, true), trackMaterial))

  // ----- trains: a blue locomotive and cream coaches, each following its loop -----
  const locoMaterial = material(0x124b8f)
  const coachMaterial = material(0xf1ebdc)
  const stripeMaterial = material(0xf2a900)
  const carGeometry = new BoxGeometry(2.6, 1.0, 1.0)
  const locoGeometry = new BoxGeometry(2.9, 1.15, 1.05)
  const stripeGeometry = new BoxGeometry(2.62, 0.14, 1.02)

  const specs: TrainSpec[] = [
    { curve: loops[0], speed: 5, coaches: 4, front: 0.1 },
    { curve: loops[1], speed: 3.4, coaches: 3, front: 0.55 },
    { curve: loops[2], speed: 2.6, coaches: 2, front: 0.3 },
  ]
  const trains = specs.map((spec) => {
    const length = spec.curve.getLength()
    const cars: Mesh[] = []
    const loco = new Mesh(locoGeometry, locoMaterial)
    cars.push(loco)
    for (let i = 0; i < spec.coaches; i++) cars.push(new Mesh(carGeometry, coachMaterial))
    for (const car of cars) {
      const stripe = new Mesh(stripeGeometry, stripeMaterial)
      stripe.position.y = -0.1
      car.add(stripe)
      scene.add(car)
    }
    return { spec, length, cars, front: spec.front, gap: 3.05 / length }
  })

  // ----- stations on the biggest loop, each with a turning marker above it -----
  const markerColors = [0x124b8f, 0xf2a900, 0x1b8a5a, 0x6b4bb8]
  const markerGeometry = new IcosahedronGeometry(1.7, 0)
  const beaconGeometry = new CylinderGeometry(0.06, 0.06, 6, 6)
  const platformGeometry = new BoxGeometry(7, 0.3, 1.8)
  const platformMaterial = material(0xe3d6b2)
  const markers: { mesh: Mesh; baseY: number; phase: number }[] = []
  const stations = new Group()
  markerColors.forEach((color, i) => {
    const at = loops[0].getPointAt(i / markerColors.length)
    const tangent = loops[0].getTangentAt(i / markerColors.length)
    const platform = new Mesh(platformGeometry, platformMaterial)
    platform.position.set(at.x - tangent.z * 1.7, 0.2, at.z + tangent.x * 1.7)
    platform.rotation.y = headingOf(tangent.x, tangent.z)
    const beacon = new Mesh(beaconGeometry, material(color, { transparent: true, opacity: 0.45 }))
    beacon.position.set(platform.position.x, 3.3, platform.position.z)
    const marker = new Mesh(
      markerGeometry,
      material(color, { transparent: true, opacity: 0.85, emissive: color, emissiveIntensity: 0.25, roughness: 0.3 }),
    )
    marker.position.set(platform.position.x, 7.5, platform.position.z)
    stations.add(platform, beacon, marker)
    markers.push({ mesh: marker, baseY: 7.5, phase: i * 1.6 })
  })
  scene.add(stations)

  // ----- size, pointer and drawing -----
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

  const pointer = { x: 0, y: 0, targetX: 0, targetY: 0 }
  const onPointer = (event: PointerEvent) => {
    pointer.targetX = (event.clientX / window.innerWidth) * 2 - 1
    pointer.targetY = (event.clientY / window.innerHeight) * 2 - 1
  }
  window.addEventListener('pointermove', onPointer, { passive: true })

  const started = performance.now()
  let last = started
  let frame = 0
  let disposed = false
  const ahead = new Vector3()

  function draw(now: number) {
    if (disposed) return
    frame = requestAnimationFrame(draw)
    if (now - last < FRAME_MS) return
    const delta = Math.min((now - last) / 1000, 0.1)
    last = now
    const seconds = (now - started) / 1000

    for (const train of trains) {
      train.front = (train.front + (train.spec.speed * delta) / train.length) % 1
      train.cars.forEach((car, index) => {
        const u = carPosition(train.front, index, train.gap)
        train.spec.curve.getPointAt(u, ahead)
        car.position.set(ahead.x, 0.85, ahead.z)
        const tangent = train.spec.curve.getTangentAt(u)
        car.rotation.y = headingOf(tangent.x, tangent.z)
      })
    }
    for (const marker of markers) {
      marker.mesh.rotation.y = seconds * 0.5 + marker.phase
      marker.mesh.rotation.x = seconds * 0.3 + marker.phase
      marker.mesh.position.y = marker.baseY + Math.sin(seconds * 0.9 + marker.phase) * 0.6
    }

    pointer.x += (pointer.targetX - pointer.x) * 0.05
    pointer.y += (pointer.targetY - pointer.y) * 0.05
    const sway = cameraSway(seconds, pointer.x, pointer.y)
    camera.position.set(...sway.position)
    camera.lookAt(...sway.target)
    renderer.render(scene, camera)
  }
  frame = requestAnimationFrame(draw)

  return {
    dispose() {
      if (disposed) return
      disposed = true
      cancelAnimationFrame(frame)
      observer?.disconnect()
      window.removeEventListener('pointermove', onPointer)
      const geometries = new Set<BufferGeometry>()
      const materials = new Set<Material>()
      scene.traverse((object: Object3D) => {
        const mesh = object as Mesh
        if (mesh.geometry) geometries.add(mesh.geometry)
        const m = mesh.material
        if (Array.isArray(m)) m.forEach((x) => materials.add(x))
        else if (m) materials.add(m)
      })
      geometries.forEach((g) => g.dispose())
      materials.forEach((m) => m.dispose())
      renderer.dispose()
      renderer.forceContextLoss()
    },
  }
}
