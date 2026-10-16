import { useMemo, useState } from 'react'
import type { ScheduleBlock } from '../api/types'
import { addDays, fmtDate, fmtDuration, fmtTime, plural } from '../lib/time'
import { DEPT_COLORS, deptColor, layoutBlocks, rowSections } from '../lib/gantt'
import type { LaidOutBlock } from '../lib/gantt'

const LABEL_W = 64
const PLOT_W = 1100
const TOP = 38
const ROW_H = 58
const PAD = 8

interface Props {
  blocks: ScheduleBlock[]
  horizonStart: string
  days: number
  /** Every section of the network, so rows without closures still show. */
  sections: string[]
  title?: string
  /** 'auto' opens on the first day that has a closure; 'week' shows the whole plan. */
  defaultView?: 'week' | 'auto'
}

interface Hover {
  block: LaidOutBlock
  x: number
  y: number
}

/** Timeline of closures: one row per section, bars coloured by department. Plain SVG. */
export function Gantt({ blocks, horizonStart, days, sections, title, defaultView = 'week' }: Props) {
  const [view, setView] = useState<'week' | number>(() => {
    if (defaultView === 'week' || blocks.length === 0) return 'week'
    const first = Math.min(...layoutBlocks(blocks, horizonStart).map((b) => Math.floor(b.startHour / 24)))
    return Math.min(days - 1, Math.max(0, first))
  })
  const [hover, setHover] = useState<Hover | null>(null)

  const laid = useMemo(() => layoutBlocks(blocks, horizonStart), [blocks, horizonStart])
  const rows = useMemo(() => rowSections(sections, blocks), [sections, blocks])
  const startDate = horizonStart.slice(0, 10)

  const rangeStart = view === 'week' ? 0 : view * 24
  const rangeEnd = view === 'week' ? days * 24 : view * 24 + 24
  const x = (hour: number) => LABEL_W + ((hour - rangeStart) / (rangeEnd - rangeStart)) * PLOT_W
  const height = TOP + rows.length * ROW_H + 8

  const ticks: { hour: number; label: string; major: boolean }[] = []
  if (view === 'week') {
    for (let d = 0; d <= days; d++) {
      ticks.push({ hour: d * 24, label: d < days ? fmtDate(addDays(startDate, d)).slice(0, 6) : '', major: true })
    }
  } else {
    for (let h = 0; h <= 24; h += 2) {
      ticks.push({ hour: rangeStart + h, label: `${String(h % 24).padStart(2, '0')}:00`, major: h % 6 === 0 })
    }
  }

  return (
    <div className="gantt">
      <div className="gantt-toolbar">
        {title && <h3>{title}</h3>}
        <div className="segmented" role="group" aria-label="Timeline range">
          <button
            type="button"
            className={view === 'week' ? 'active' : ''}
            onClick={() => setView('week')}
          >
            Whole plan
          </button>
          {Array.from({ length: days }, (_, d) => (
            <button
              key={d}
              type="button"
              className={view === d ? 'active' : ''}
              onClick={() => setView(d)}
            >
              {fmtDate(addDays(startDate, d)).slice(0, 6)}
            </button>
          ))}
        </div>
      </div>

      <div className="gantt-scroll" onMouseLeave={() => setHover(null)}>
        <svg
          viewBox={`0 0 ${LABEL_W + PLOT_W + 8} ${height}`}
          className="gantt-svg"
          role="img"
          aria-label={title ?? 'Closure timeline'}
        >
          {ticks.map((tick) => (
            <g key={tick.hour}>
              <line
                x1={x(tick.hour)}
                x2={x(tick.hour)}
                y1={TOP - 6}
                y2={height - 4}
                className={tick.major ? 'grid grid-major' : 'grid'}
              />
              {tick.label && (
                <text x={x(tick.hour) + 4} y={TOP - 14} className="axis-label">
                  {tick.label}
                </text>
              )}
            </g>
          ))}

          {rows.map((section, index) => {
            const top = TOP + index * ROW_H
            return (
              <g key={section}>
                <rect x={0} y={top} width={LABEL_W + PLOT_W} height={ROW_H} className={index % 2 ? 'row-odd' : 'row-even'} />
                <text x={10} y={top + ROW_H / 2 + 5} className="row-label">
                  {section}
                </text>
              </g>
            )
          })}

          {laid.map((block) => {
            if (block.endHour <= rangeStart || block.startHour >= rangeEnd) return null
            const row = rows.indexOf(block.section)
            if (row < 0) return null
            const top = TOP + row * ROW_H + PAD
            const inner = ROW_H - PAD * 2
            const left = x(Math.max(block.startHour, rangeStart))
            const width = Math.max(8, x(Math.min(block.endHour, rangeEnd)) - left)
            const lane = Math.max(4, Math.min(16, inner / Math.max(1, block.members.length)))
            return (
              <g
                key={block.key}
                className="gantt-block"
                data-section={block.section}
                onMouseMove={(e) => {
                  const box = (e.currentTarget.ownerSVGElement as SVGSVGElement).getBoundingClientRect()
                  setHover({ block, x: e.clientX - box.left, y: e.clientY - box.top })
                }}
                onMouseLeave={() => setHover(null)}
              >
                <rect x={left} y={top} width={width} height={inner} rx={5} className="block-frame" />
                {block.members.map((member, i) => {
                  const mLeft = x(Math.max(member.startHour, rangeStart))
                  const mWidth = Math.max(3, x(Math.min(member.endHour, rangeEnd)) - mLeft)
                  return (
                    <rect
                      key={member.requestId}
                      x={mLeft}
                      y={top + 2 + i * lane}
                      width={mWidth}
                      height={lane - 2}
                      rx={3}
                      fill={deptColor(member.dept)}
                    />
                  )
                })}
              </g>
            )
          })}
        </svg>

        {hover && (
          <div className="gantt-tooltip" style={{ left: hover.x + 14, top: hover.y + 14 }} role="tooltip">
            <strong>
              {hover.block.section}
              {hover.block.blockId ? ` · block ${hover.block.blockId}` : ''}
            </strong>
            <div>{describeBlock(hover.block)}</div>
            <ul>
              {hover.block.members.map((m) => (
                <li key={m.requestId}>
                  <i className="dot" style={{ background: deptColor(m.dept) }} />
                  {m.label} · {m.dept}
                  <span> {memberClock(hover.block, m.requestId)}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>

      <div className="legend" aria-label="Departments">
        {Object.entries(DEPT_COLORS).map(([dept, color]) => (
          <span key={dept}>
            <i className="dot" style={{ background: color }} />
            {dept}
          </span>
        ))}
        <span className="legend-note">Hover a bar for its requests. Frames show the whole closure.</span>
      </div>
    </div>
  )
}

function describeBlock(block: LaidOutBlock): string {
  const { source } = block
  const minutes = Math.round((block.endHour - block.startHour) * 60)
  return `${fmtDate(source.start)} ${fmtTime(source.start)}-${fmtTime(source.end)} · ${fmtDuration(minutes)} · ${plural(block.trains, 'train')} affected`
}

function memberClock(block: LaidOutBlock, requestId: number): string {
  const member = block.source.members.find((m) => m.request_id === requestId)
  return member ? `${member.start}-${member.end}` : ''
}
