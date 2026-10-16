import type { ScheduleBlock } from '../api/types'

export interface LaidOutMember {
  requestId: number
  label: string
  dept: string
  startHour: number
  endHour: number
}

export interface LaidOutBlock {
  key: string
  source: ScheduleBlock
  section: string
  blockId: number | null
  startHour: number
  endHour: number
  trains: number
  members: LaidOutMember[]
}

const HOUR_MS = 3_600_000

/** Hours between two ISO timestamps (positive when `to` is later). */
export function hoursBetween(from: string, to: string): number {
  return (Date.parse(to) - Date.parse(from)) / HOUR_MS
}

/** Hours since the horizon start for a member time like "08:30" on the block's day.
 * The API writes an end at midnight as "24:00". */
function memberHour(block: ScheduleBlock, horizonStart: string, clock: string): number {
  if (clock === '24:00') return hoursBetween(horizonStart, block.end)
  const day = block.start.slice(0, 10)
  const offset = block.start.slice(19)
  return hoursBetween(horizonStart, `${day}T${clock}:00${offset}`)
}

/** Positions of every block (and its members) in hours from the start of the plan horizon. */
export function layoutBlocks(blocks: ScheduleBlock[], horizonStart: string): LaidOutBlock[] {
  return blocks
    .map((block, index) => ({
      key: `${block.id ?? 'b'}-${block.section_code}-${index}`,
      source: block,
      section: block.section_code,
      blockId: block.id,
      startHour: hoursBetween(horizonStart, block.start),
      endHour: hoursBetween(horizonStart, block.end),
      trains: block.trains_affected,
      members: block.members.map((m) => ({
        requestId: m.request_id,
        label: m.request,
        dept: m.dept,
        startHour: memberHour(block, horizonStart, m.start),
        endHour: memberHour(block, horizonStart, m.end),
      })),
    }))
    .sort((a, b) => a.section.localeCompare(b.section) || a.startHour - b.startHour)
}

/** Sections to draw as rows: every section of the network plus any that appear in the plan. */
export function rowSections(all: string[], blocks: ScheduleBlock[]): string[] {
  return [...new Set([...all, ...blocks.map((b) => b.section_code)])].sort()
}

export const DEPT_COLORS: Record<string, string> = {
  ENGG: '#1f6fb2',
  TRD: '#e08a00',
  SNT: '#2a9d6f',
}
export const FALLBACK_COLOR = '#6b7a8c'

export function deptColor(dept: string): string {
  return DEPT_COLORS[dept] ?? FALLBACK_COLOR
}
