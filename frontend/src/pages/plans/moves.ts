import type { Schedule } from '../../api/types'

export interface Movable {
  requestId: number
  label: string
  dept: string
  section: string
  /** Current start as a datetime-local value, for example "2026-10-19T04:00". */
  startLocal: string
  summary: string
}

/** Every placed request of a schedule, with its current start, for the move pickers. */
export function movableRequests(schedule: Schedule): Movable[] {
  const items: Movable[] = []
  for (const block of schedule.blocks) {
    for (const m of block.members) {
      items.push({
        requestId: m.request_id,
        label: m.request,
        dept: m.dept,
        section: block.section_code,
        startLocal: `${block.start.slice(0, 10)}T${m.start}`,
        summary: `${m.request} · ${m.dept} · ${block.section_code} · ${block.start.slice(0, 10)} ${m.start}-${m.end}`,
      })
    }
  }
  return items.sort((a, b) => a.requestId - b.requestId)
}
