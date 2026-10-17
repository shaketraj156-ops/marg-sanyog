import type { MutableRefObject } from 'react'
import {
  CARS,
  CAR_BOTTOM,
  CAR_GAP,
  CAR_TOP,
  TRAIN_FRONT_X,
  WHEEL_Y,
  WIRE_Y,
  wheelCentres,
  type Car,
} from './geometry'

const CAR_H = CAR_BOTTOM - CAR_TOP

function Coach({ car }: { car: Car }) {
  const { x, w } = car
  const windows = [0, 1, 2, 3].map((i) => x + 54 + i * 28)
  return (
    <g>
      <rect x={x} y={CAR_TOP} width={w} height={CAR_H} rx={9} fill="#efe9da" />
      <rect x={x + 4} y={CAR_TOP - 5} width={w - 8} height={7} rx={3} fill="#aeb6c1" />
      <rect x={x + 44} y={CAR_TOP - 11} width={64} height={7} rx={3} fill="#b9c0ca" />
      <rect x={x + w - 112} y={CAR_TOP - 11} width={64} height={7} rx={3} fill="#b9c0ca" />
      <rect x={x + 2} y={686} width={w - 4} height={4} fill="#f2a900" />
      <rect x={x + 2} y={692} width={w - 4} height={26} fill="#124b8f" />
      {windows.map((wx) => (
        <g key={wx}>
          <rect x={wx} y={656} width={22} height={26} rx={4} fill="#20384f" />
          <rect x={wx + 3} y={659} width={8} height={20} rx={2} fill="#ffffff" opacity={0.16} />
        </g>
      ))}
      {[x + 14, x + w - 40].map((dx) => (
        <g key={dx}>
          <rect x={dx} y={654} width={26} height={60} rx={3} fill="#d9d3c1" stroke="#b9b29e" strokeWidth={1.5} />
          <rect x={dx + 5} y={660} width={16} height={24} rx={3} fill="#20384f" />
        </g>
      ))}
      <rect x={x + 8} y={CAR_BOTTOM - 2} width={w - 16} height={12} rx={3} fill="#2f3742" />
    </g>
  )
}

function Loco({ car }: { car: Car }) {
  const { x, w } = car
  const front = x + w
  const px = x + 100 // the pantograph
  const body = `M ${x},650 Q ${x},640 ${x + 10},640 H ${front - 74} L ${front - 8},678 Q ${front},686 ${front},698 V ${CAR_BOTTOM} H ${x} Z`
  return (
    <g>
      {/* pantograph reaching up to the contact wire */}
      <g stroke="#232a33" strokeWidth={3.5} fill="none" strokeLinecap="round" strokeLinejoin="round">
        <rect x={px - 30} y={630} width={46} height={5} rx={2} fill="#232a33" stroke="none" />
        <polyline points={`${px - 22},630 ${px + 6},612 ${px - 12},${WIRE_Y + 3}`} />
        <polyline points={`${px - 10},630 ${px + 14},612 ${px - 2},${WIRE_Y + 3}`} />
        <line x1={px - 30} y1={WIRE_Y + 1} x2={px + 4} y2={WIRE_Y + 1} strokeWidth={4.5} />
      </g>
      <path d={body} fill="#124b8f" />
      <rect x={x + 10} y={634} width={w - 84} height={8} rx={3} fill="#8c96a3" />
      <rect x={x + 2} y={690} width={w - 38} height={6} fill="#f6f2e6" />
      <rect x={x + 2} y={698} width={w - 38} height={3} fill="#f2a900" />
      {Array.from({ length: 7 }, (_, i) => (
        <rect key={i} x={x + 24 + i * 12} y={660} width={6} height={22} rx={2} fill="#0d3a72" />
      ))}
      <rect x={front - 132} y={652} width={42} height={28} rx={4} fill="#20384f" />
      <path d={`M ${front - 70},652 L ${front - 24},682 L ${front - 24},696 L ${front - 70},696 Z`} fill="#20384f" />
      <rect x={front - 8} y={706} width={8} height={14} rx={2} fill="#2a313b" />
      <circle cx={front - 4} cy={696} r={5.5} fill="#fff6c8" />
      <rect x={x + 8} y={CAR_BOTTOM - 2} width={w - 16} height={12} rx={3} fill="#2f3742" />
    </g>
  )
}

function Couplers() {
  return (
    <g fill="#2a313b">
      {CARS.slice(0, -1).map((car) => (
        <rect key={car.x} x={car.x + car.w - 2} y={700} width={CAR_GAP + 4} height={9} rx={2} />
      ))}
    </g>
  )
}

/** The wheels turn as the world slides; the scene sets each wheel's rotation as you scroll. */
function Wheels({ wheelsRef }: { wheelsRef: MutableRefObject<SVGGElement[]> }) {
  return (
    <g>
      {wheelCentres().map((cx, i) => (
        <g key={cx}>
          <rect x={cx - 3} y={WHEEL_Y - 4} width={6} height={6} fill="#2a313b" />
          <g
            ref={(el) => {
              if (el) wheelsRef.current[i] = el
            }}
            data-cx={cx}
          >
            <circle cx={cx} cy={WHEEL_Y} r={14} fill="#2a323d" />
            <circle cx={cx} cy={WHEEL_Y} r={9.5} fill="#3a4452" />
            <line x1={cx} y1={WHEEL_Y - 9} x2={cx} y2={WHEEL_Y + 9} stroke="#8d99a8" strokeWidth={2} />
            <line x1={cx - 9} y1={WHEEL_Y} x2={cx + 9} y2={WHEEL_Y} stroke="#8d99a8" strokeWidth={2} />
            <circle cx={cx} cy={WHEEL_Y} r={3.5} fill="#8d99a8" />
          </g>
        </g>
      ))}
      {CARS.map((car) => {
        const inset = car.kind === 'loco' ? 58 : 36
        return [car.x + inset, car.x + car.w - inset].map((bx) => (
          <rect key={`${car.x}-${bx}`} x={bx - 22} y={726} width={44} height={9} rx={3} fill="#2a313b" />
        ))
      })}
    </g>
  )
}

export function TrainBody({ wheelsRef }: { wheelsRef: MutableRefObject<SVGGElement[]> }) {
  return (
    <g>
      <Wheels wheelsRef={wheelsRef} />
      {CARS.map((car) => (car.kind === 'loco' ? <Loco key={car.x} car={car} /> : <Coach key={car.x} car={car} />))}
      <Couplers />
    </g>
  )
}

/** Lit windows, the open doors and the headlight: drawn above the night tint so they glow. */
export function TrainLights({ doorsRef }: { doorsRef: MutableRefObject<SVGGElement | null> }) {
  return (
    <g>
      <polygon points={`${TRAIN_FRONT_X},694 ${TRAIN_FRONT_X + 520},630 ${TRAIN_FRONT_X + 520},780`} fill="url(#beam)" />
      <circle cx={TRAIN_FRONT_X - 4} cy={696} r={26} fill="url(#lampGlow)" />
      {CARS.map((car) => {
        if (car.kind === 'loco') {
          return <rect key={car.x} x={car.x + car.w - 132} y={652} width={42} height={28} rx={4} fill="#ffdf9a" opacity={0.95} />
        }
        return [0, 1, 2, 3].map((i) => (
          <rect key={`${car.x}-${i}`} x={car.x + 54 + i * 28} y={656} width={22} height={26} rx={4} fill="#ffdf9a" opacity={0.95} />
        ))
      })}
      <g ref={doorsRef} className="door-glow">
        {CARS.filter((c) => c.kind === 'coach').flatMap((car) =>
          [car.x + 14, car.x + car.w - 40].map((dx) => (
            <rect key={`${car.x}-${dx}`} x={dx + 3} y={656} width={20} height={56} rx={3} fill="#fff1c9" />
          )),
        )}
      </g>
    </g>
  )
}
