import { gsap } from 'gsap'
import { ScrollTrigger } from 'gsap/ScrollTrigger'
import { memo, useEffect, useMemo, useRef } from 'react'
import type { RefObject } from 'react'
import { TrainBody, TrainLights } from './Train'
import {
  CAR_BOTTOM,
  END_OFFSET,
  MAST_SPACING,
  PARALLAX,
  PLATFORM_W,
  RAIL_Y,
  STATIONS,
  STATION_OFFSETS,
  START_OFFSET,
  WIRE_Y,
  clouds,
  droppers,
  layerSpan,
  mastPositions,
  messengerWire,
  ridge,
  skyline,
  stars,
  trees,
  wheelCentres,
} from './geometry'
import { FRONT_TINT, bob, doorsOpen, frameState, journey, signalGreen, signalX, wheelAngle } from './frame'

interface Props {
  /** The section that is pinned while the scene plays. */
  triggerRef: RefObject<HTMLElement | null>
  /** False shows one still picture (reduced motion, narrow screens, tests). */
  animated: boolean
  /** Pixels of scrolling for the whole journey. */
  scrollDistance: number
  /** Called with the journey progress (0 to 1) as it changes. */
  onProgress?: (progress: number) => void
}

type Els = Partial<Record<string, SVGElement | null>>

const FAR_X = 5600
const FAR_Y = -3000

/** The still picture: the train standing at the first platform in daylight. */
const STILL_T = 0.13

function HeroSceneInner({ triggerRef, animated, scrollDistance, onProgress }: Props) {
  const els = useRef<Els>({})
  const wheels = useRef<SVGGElement[]>([])
  const doors = useRef<SVGGElement | null>(null)
  const signals = useRef<{ red: SVGElement | null; green: SVGElement | null; glow: SVGElement | null }[]>([])
  const progressRef = useRef(onProgress)
  useEffect(() => {
    progressRef.current = onProgress
  })

  const ref = (key: string) => (el: SVGElement | null) => {
    els.current[key] = el
  }

  // The scenery is generated once, from fixed seeds, so it looks the same on every visit.
  const scenery = useMemo(() => {
    const mountainSpan = layerSpan(PARALLAX.mountains)
    const skylineSpan = layerSpan(PARALLAX.skyline)
    const hillSpan = layerSpan(PARALLAX.hills)
    const cloudSpan = layerSpan(PARALLAX.clouds)
    const masts = mastPositions(-1500, END_OFFSET + 1600 + 1500)
    return {
      mountains: ridge(11, mountainSpan.from, mountainSpan.to, 744, 150, 330),
      mountainsNear: ridge(23, mountainSpan.from, mountainSpan.to, 744, 90, 210),
      buildings: skyline(5, skylineSpan.from, skylineSpan.to),
      hills: ridge(37, hillSpan.from, hillSpan.to, 776, 24, 96),
      trees: trees(9, hillSpan.from, hillSpan.to, 758),
      clouds: clouds(3, cloudSpan.from, cloudSpan.to),
      stars: stars(17, 90),
      masts,
      messenger: messengerWire(masts),
      droppers: droppers(masts),
      wheelCentres: wheelCentres(),
    }
  }, [])

  // Apply one moment of the journey to the drawing. No React re-render: just set attributes.
  const apply = (t: number, offset: number, speed: number) => {
    const e = els.current
    const f = frameState(t, offset)
    const opacity = (key: string, value: number) => {
      const el = e[key]
      if (el) el.style.opacity = String(value)
    }
    const move = (key: string, x: number, y = 0) => e[key]?.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)})`)

    opacity('day', f.dayOpacity)
    opacity('sunset', f.sunsetOpacity)
    opacity('stars', f.starsOpacity)
    opacity('clouds', f.cloudsOpacity)
    opacity('nightTint', f.nightTint)
    opacity('warmTint', f.warmTint)
    opacity('warmTintFront', f.warmTint * FRONT_TINT)
    opacity('nightTintFront', f.nightTint * FRONT_TINT)
    opacity('lights', f.lightsOpacity)
    opacity('lightsFront', f.lightsOpacity)
    opacity('sun', f.sun.opacity)
    opacity('moon', f.moon.opacity)
    move('sun', f.sun.x, f.sun.y)
    move('moon', f.moon.x, f.moon.y)
    move('mountains', f.translate.mountains)
    move('skyline', f.translate.skyline)
    move('skylineLit', f.translate.skyline)
    move('hills', f.translate.hills)
    move('clouds', f.translate.clouds)
    move('world', f.translate.world)
    move('worldLights', f.translate.world)
    const shift = (offset % 46) * -1
    e.sleepers?.setAttribute('patternTransform', `translate(${shift.toFixed(2)} 0)`)

    const angle = wheelAngle(offset)
    wheels.current.forEach((wheel) => {
      const cx = Number(wheel.dataset.cx)
      wheel.setAttribute('transform', `rotate(${angle.toFixed(1)} ${cx} 734)`)
    })
    const lift = bob(offset, speed)
    move('train', 0, lift)
    move('trainLights', 0, lift)
    if (doors.current) doors.current.style.opacity = doorsOpen(t) ? '1' : '0'

    signals.current.forEach((lamp, i) => {
      const green = signalGreen(i, offset)
      if (lamp.red) lamp.red.style.opacity = green ? '0.18' : '1'
      if (lamp.green) lamp.green.style.opacity = green ? '1' : '0.18'
      lamp.glow?.setAttribute('fill', green ? '#3ddc84' : '#ff4d4d')
    })
  }

  useEffect(() => {
    if (!animated) {
      apply(STILL_T, STATION_OFFSETS[0], 0)
      return
    }
    const trigger = triggerRef.current
    if (!trigger) return

    gsap.registerPlugin(ScrollTrigger)
    const state = { offset: START_OFFSET }
    let last = state.offset
    const context = gsap.context(() => {
      const timeline = gsap.timeline({
        scrollTrigger: {
          trigger,
          start: 'top top',
          end: `+=${scrollDistance}`,
          scrub: 0.9, // smooth damping
          pin: true, // the section stays put while the world slides past
          anticipatePin: 1,
        },
      })
      journey().forEach((segment) => {
        timeline.to(
          state,
          { offset: segment.toOffset, duration: segment.to - segment.from, ease: segment.ease },
          segment.from,
        )
      })
      timeline.eventCallback('onUpdate', () => {
        const t = timeline.progress()
        apply(t, state.offset, state.offset - last)
        last = state.offset
        progressRef.current?.(t)
      })
      apply(0, START_OFFSET, 0)
    })
    return () => {
      context.revert() // removes the pin and the animation, so nothing leaks between visits
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [animated, scrollDistance, triggerRef])

  const s = scenery
  const worldFrom = -1500
  const worldTo = END_OFFSET + 1600 + 1500

  return (
    <svg
      className="hero-scene"
      viewBox="0 0 1600 900"
      preserveAspectRatio="xMidYMax meet"
      aria-hidden="true"
      focusable="false"
      data-testid="hero-scene"
    >
      <defs>
        <linearGradient id="skyDay" gradientUnits="userSpaceOnUse" x1="0" y1="-200" x2="0" y2="760">
          <stop offset="0" stopColor="#4aa8ec" />
          <stop offset="0.55" stopColor="#9fd6fa" />
          <stop offset="1" stopColor="#e6f5ff" />
        </linearGradient>
        <linearGradient id="skySunset" gradientUnits="userSpaceOnUse" x1="0" y1="-200" x2="0" y2="760">
          <stop offset="0" stopColor="#3a3f86" />
          <stop offset="0.38" stopColor="#b9528a" />
          <stop offset="0.72" stopColor="#ff9d5c" />
          <stop offset="1" stopColor="#ffd9a0" />
        </linearGradient>
        <linearGradient id="skyNight" gradientUnits="userSpaceOnUse" x1="0" y1="-200" x2="0" y2="760">
          <stop offset="0" stopColor="#040a1e" />
          <stop offset="0.6" stopColor="#0a1a40" />
          <stop offset="1" stopColor="#1b3566" />
        </linearGradient>
        <linearGradient id="mountainFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#8cadd0" />
          <stop offset="1" stopColor="#c3d9ee" />
        </linearGradient>
        <linearGradient id="mountainNear" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#6f95bb" />
          <stop offset="1" stopColor="#a9c6e0" />
        </linearGradient>
        <linearGradient id="hillFill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#5fa270" />
          <stop offset="1" stopColor="#3c7d52" />
        </linearGradient>
        <linearGradient id="grassFill" gradientUnits="userSpaceOnUse" x1="0" y1="790" x2="0" y2="1000">
          <stop offset="0" stopColor="#4a8a5a" />
          <stop offset="1" stopColor="#2b5a3f" />
        </linearGradient>
        <linearGradient id="beam" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#fff3b8" stopOpacity="0.85" />
          <stop offset="1" stopColor="#fff3b8" stopOpacity="0" />
        </linearGradient>
        <linearGradient id="tintNight" gradientUnits="userSpaceOnUse" x1="0" y1="260" x2="0" y2="560">
          <stop offset="0" stopColor="#040f2e" stopOpacity="0" />
          <stop offset="1" stopColor="#040f2e" stopOpacity="1" />
        </linearGradient>
        <linearGradient id="tintWarm" gradientUnits="userSpaceOnUse" x1="0" y1="260" x2="0" y2="620">
          <stop offset="0" stopColor="#ff8a3d" stopOpacity="0" />
          <stop offset="1" stopColor="#ff8a3d" stopOpacity="1" />
        </linearGradient>
        <radialGradient id="lampGlow">
          <stop offset="0" stopColor="#ffe9a8" stopOpacity="0.95" />
          <stop offset="1" stopColor="#ffe9a8" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="sunGlow">
          <stop offset="0" stopColor="#fff4c2" stopOpacity="0.9" />
          <stop offset="0.35" stopColor="#ffd37a" stopOpacity="0.4" />
          <stop offset="1" stopColor="#ffd37a" stopOpacity="0" />
        </radialGradient>
        <radialGradient id="moonGlow">
          <stop offset="0" stopColor="#dbe7ff" stopOpacity="0.55" />
          <stop offset="1" stopColor="#dbe7ff" stopOpacity="0" />
        </radialGradient>
        <pattern id="sleepers" width="46" height="40" patternUnits="userSpaceOnUse" ref={ref('sleepers')}>
          <rect x="9" y="0" width="28" height="9" rx="1.5" fill="#4a3b31" />
          <rect x="0" y="14" width="46" height="2" fill="#797e86" opacity="0.45" />
          <rect x="0" y="27" width="46" height="2" fill="#6c7078" opacity="0.4" />
        </pattern>
        <pattern id="glass" width="14" height="18" patternUnits="userSpaceOnUse">
          <rect x="3" y="4" width="6" height="8" fill="#b4c7dc" opacity="0.75" />
        </pattern>
        <pattern id="litA" width="14" height="18" patternUnits="userSpaceOnUse">
          <rect x="3" y="4" width="6" height="8" fill="#ffd77a" />
        </pattern>
        <pattern id="litB" width="18" height="22" patternUnits="userSpaceOnUse">
          <rect x="4" y="5" width="6" height="9" fill="#ffe29a" />
          <rect x="12" y="13" width="4" height="6" fill="#ffd077" />
        </pattern>
        <pattern id="litC" width="22" height="16" patternUnits="userSpaceOnUse">
          <rect x="5" y="4" width="8" height="6" fill="#ffd98a" />
        </pattern>
      </defs>

      {/* ---- sky: night underneath, sunset above it, day on top; each fades away in turn ---- */}
      <rect x={-FAR_X} y={FAR_Y} width={FAR_X * 2 + 1600} height={FAR_Y * -1 + 900} fill="url(#skyNight)" />
      <rect ref={ref('sunset')} x={-FAR_X} y={FAR_Y} width={FAR_X * 2 + 1600} height={FAR_Y * -1 + 900} fill="url(#skySunset)" />
      <rect ref={ref('day')} x={-FAR_X} y={FAR_Y} width={FAR_X * 2 + 1600} height={FAR_Y * -1 + 900} fill="url(#skyDay)" />

      <g ref={ref('stars')} opacity="0">
        {s.stars.map((star, i) => (
          <circle key={i} className="star" cx={star.x} cy={star.y} r={star.r} fill="#ffffff" style={{ animationDelay: `${star.delay}s` }} />
        ))}
      </g>

      <g ref={ref('sun')}>
        <circle r="230" fill="url(#sunGlow)" />
        <circle r="46" fill="#fff6d0" />
      </g>
      <g ref={ref('moon')} opacity="0">
        <circle r="150" fill="url(#moonGlow)" />
        <circle r="38" fill="#f6f2dc" />
        <circle cx="-12" cy="-8" r="7" fill="#d9d4bb" opacity="0.7" />
        <circle cx="14" cy="10" r="5" fill="#d9d4bb" opacity="0.6" />
      </g>

      <g ref={ref('clouds')}>
        {s.clouds.map((cloud, i) => (
          <g key={i} transform={`translate(${cloud.x} ${cloud.y}) scale(${cloud.scale})`} fill="#ffffff" opacity="0.9">
            <ellipse cx="0" cy="0" rx="70" ry="22" />
            <ellipse cx="42" cy="-12" rx="46" ry="26" />
            <ellipse cx="-46" cy="-6" rx="40" ry="18" />
            <ellipse cx="8" cy="-22" rx="38" ry="24" />
          </g>
        ))}
      </g>

      {/* ---- distant layers: they move slower than the track, which gives the depth ---- */}
      <g ref={ref('mountains')}>
        <path d={s.mountains} fill="url(#mountainFill)" />
        <path d={s.mountainsNear} fill="url(#mountainNear)" />
      </g>
      <g ref={ref('skyline')}>
        {s.buildings.map((b, i) => (
          <g key={i}>
            <rect x={b.x} y={742 - b.h} width={b.w} height={b.h + 40} fill="#7d93ad" />
            <rect x={b.x} y={742 - b.h} width={b.w} height={b.h + 40} fill="url(#glass)" />
            <rect x={b.x} y={738 - b.h} width={b.w} height={5} fill="#6d8199" />
          </g>
        ))}
      </g>
      <g ref={ref('hills')}>
        <path d={s.hills} fill="url(#hillFill)" />
        {s.trees.map((tree, i) => (
          <g key={i}>
            <rect x={tree.x - 1.5} y={tree.y - 4} width={3} height={tree.r * 0.6} fill="#4a3b31" />
            <ellipse cx={tree.x} cy={tree.y - tree.r * 0.9} rx={tree.r * 0.8} ry={tree.r} fill={tree.shade > 0.5 ? '#2f6e4a' : '#3d8456'} />
          </g>
        ))}
      </g>

      {/* ---- the tint of the hour over the distant layers, then their lit windows. Both sit behind the
           station and the train, so the train is never covered by the lit windows ---- */}
      <rect ref={ref('warmTint')} x={-FAR_X} y={-200} width={FAR_X * 2 + 1600} height={1400} fill="url(#tintWarm)" opacity="0" />
      <rect ref={ref('nightTint')} x={-FAR_X} y={-200} width={FAR_X * 2 + 1600} height={1400} fill="url(#tintNight)" opacity="0" />
      <g ref={ref('lights')} opacity="0">
        <g ref={ref('skylineLit')}>
          {s.buildings.map((b, i) => (
            <rect key={i} x={b.x} y={742 - b.h} width={b.w} height={b.h} fill={`url(#lit${['A', 'B', 'C'][i % 3]})`} opacity={0.55 + (i % 4) * 0.12} />
          ))}
        </g>
      </g>

      {/* ---- the world the train passes: overhead line, station canopies, signals ---- */}
      <g ref={ref('world')} data-testid="world">
        <path d={s.messenger} stroke="#2b323b" strokeWidth="1.6" fill="none" />
        <line x1={worldFrom} y1={WIRE_Y} x2={worldTo} y2={WIRE_Y} stroke="#2b323b" strokeWidth="2.2" />
        {s.droppers.map((d, i) => (
          <line key={i} x1={d.x} y1={d.y1} x2={d.x} y2={d.y2} stroke="#2b323b" strokeWidth="1" />
        ))}
        {s.masts.map((x) => (
          <g key={x} fill="#4a5461">
            <rect x={x - 3.5} y={WIRE_Y - 40} width={7} height={RAIL_Y - WIRE_Y + 40 + 40} />
            <rect x={x - 26} y={WIRE_Y - 34} width={34} height={5} />
            <rect x={x - 10} y={RAIL_Y + 34} width={20} height={9} />
          </g>
        ))}

        {STATIONS.map((station) => (
          <g key={station.name}>
            {/* canopy over the platform */}
            <path
              d={`M ${station.x - PLATFORM_W / 2},500 H ${station.x + PLATFORM_W / 2} L ${station.x + PLATFORM_W / 2 - 24},528 H ${station.x - PLATFORM_W / 2 + 24} Z`}
              fill="#3a4859"
            />
            <rect x={station.x - PLATFORM_W / 2} y={496} width={PLATFORM_W} height={6} fill="#56677c" />
            <rect x={station.x - PLATFORM_W / 2 + 24} y={528} width={PLATFORM_W - 48} height={5} fill="#2c3744" />
            {[-420, -210, 0, 210, 420].map((dx) => (
              <rect key={dx} x={station.x + dx - 5} y={528} width={10} height={190} fill="#5b6b7e" />
            ))}
            {/* the name board, hanging from the canopy */}
            <rect x={station.x - 90} y={533} width={4} height={26} fill="#2c3744" />
            <rect x={station.x + 86} y={533} width={4} height={26} fill="#2c3744" />
            <rect x={station.x - 168} y={556} width={336} height={66} rx={7} fill="#f4c20d" stroke="#14181e" strokeWidth={4} />
            <text x={station.x} y={578} textAnchor="middle" className="board-small">
              STATION {station.number}
            </text>
            <text x={station.x} y={612} textAnchor="middle" className="board-name">
              {station.name}
            </text>
            {/* the platform edge, below the train */}
            <rect x={station.x - PLATFORM_W / 2} y={716} width={PLATFORM_W} height={32} fill="#9ea6b0" />
            <rect x={station.x - PLATFORM_W / 2} y={716} width={PLATFORM_W} height={5} fill="#f4c20d" />
          </g>
        ))}

        {STATIONS.map((_, i) => {
          const x = signalX(i)
          return (
            <g key={i}>
              <rect x={x - 3} y={640} width={6} height={RAIL_Y - 640 + 40} fill="#3a424d" />
              <rect x={x - 13} y={606} width={26} height={62} rx={6} fill="#1d232b" />
              <circle
                cx={x}
                cy={622}
                r={8}
                fill="#ff4d4d"
                ref={(el) => {
                  signals.current[i] = { ...(signals.current[i] ?? { green: null, glow: null }), red: el }
                }}
              />
              <circle
                cx={x}
                cy={650}
                r={8}
                fill="#3ddc84"
                ref={(el) => {
                  signals.current[i] = { ...(signals.current[i] ?? { red: null, glow: null }), green: el }
                }}
              />
            </g>
          )
        })}
      </g>

      {/* ---- the ground: grass, ballast with sleepers, and the rails ---- */}
      <rect x={-FAR_X} y={790} width={FAR_X * 2 + 1600} height={1400} fill="url(#grassFill)" />
      <rect x={-FAR_X} y={752} width={FAR_X * 2 + 1600} height={40} fill="#858b93" />
      <rect x={-FAR_X} y={752} width={FAR_X * 2 + 1600} height={40} fill="url(#sleepers)" />
      <rect x={-FAR_X} y={CAR_BOTTOM + 25} width={FAR_X * 2 + 1600} height={6} fill="#a9b3be" />
      <rect x={-FAR_X} y={CAR_BOTTOM + 25} width={FAR_X * 2 + 1600} height={2} fill="#eef3f8" />

      <g ref={ref('train')} data-testid="train">
        <TrainBody wheelsRef={wheels} />
      </g>

      {/* ---- a lighter tint over the station, ground and train, so the train stays easy to see ---- */}
      <rect ref={ref('warmTintFront')} x={-FAR_X} y={-200} width={FAR_X * 2 + 1600} height={1400} fill="url(#tintWarm)" opacity="0" />
      <rect ref={ref('nightTintFront')} x={-FAR_X} y={-200} width={FAR_X * 2 + 1600} height={1400} fill="url(#tintNight)" opacity="0" />

      {/* ---- lights in front, drawn over the tint so they glow at night ---- */}
      <g ref={ref('lightsFront')} opacity="0">
        <g ref={ref('worldLights')}>
          {STATIONS.flatMap((station) =>
            [-360, 0, 360].map((dx) => (
              <g key={`${station.name}-${dx}`}>
                <circle cx={station.x + dx} cy={540} r={70} fill="url(#lampGlow)" />
                <circle cx={station.x + dx} cy={536} r={5} fill="#fff3c4" />
              </g>
            )),
          )}
          {STATIONS.map((_, i) => (
            <circle
              key={i}
              cx={signalX(i)}
              cy={636}
              r={44}
              opacity={0.55}
              fill="#ff4d4d"
              ref={(el) => {
                signals.current[i] = { ...(signals.current[i] ?? { red: null, green: null }), glow: el }
              }}
            />
          ))}
        </g>
        <g ref={ref('trainLights')}>
          <TrainLights doorsRef={doors} />
        </g>
      </g>
    </svg>
  )
}

export const HeroScene = memo(HeroSceneInner)
export { MAST_SPACING }
