import { describe, expect, it } from 'vitest'
import type { ScheduleBlock } from '../api/types'
import { deptColor, hoursBetween, layoutBlocks, rowSections } from './gantt'

const HORIZON = '2026-10-19T00:00:00+05:30'

function block(partial: Partial<ScheduleBlock> & Pick<ScheduleBlock, 'start' | 'end'>): ScheduleBlock {
  return { id: 1, section_code: 'A-B', trains_affected: 3, members: [], ...partial }
}

describe('hoursBetween', () => {
  it('measures hours between ISO timestamps with offsets', () => {
    expect(hoursBetween(HORIZON, '2026-10-19T04:30:00+05:30')).toBe(4.5)
    expect(hoursBetween(HORIZON, '2026-10-20T00:00:00+05:30')).toBe(24)
  })

  it('is negative before the horizon', () => {
    expect(hoursBetween(HORIZON, '2026-10-18T22:00:00+05:30')).toBe(-2)
  })
})

describe('layoutBlocks', () => {
  it('places a block in hours from the horizon start', () => {
    const [laid] = layoutBlocks(
      [block({ start: '2026-10-21T03:30:00+05:30', end: '2026-10-21T06:30:00+05:30' })],
      HORIZON,
    )
    expect(laid.startHour).toBe(2 * 24 + 3.5)
    expect(laid.endHour).toBe(2 * 24 + 6.5)
    expect(laid.trains).toBe(3)
    expect(laid.section).toBe('A-B')
  })

  it('places members on the same day as their block', () => {
    const [laid] = layoutBlocks(
      [
        block({
          start: '2026-10-20T03:30:00+05:30',
          end: '2026-10-20T06:30:00+05:30',
          members: [
            { request: 'R5', request_id: 5, dept: 'SNT', start: '03:30', end: '05:30' },
            { request: 'R13', request_id: 13, dept: 'ENGG', start: '03:30', end: '06:30' },
          ],
        }),
      ],
      HORIZON,
    )
    expect(laid.members.map((m) => [m.label, m.startHour, m.endHour])).toEqual([
      ['R5', 27.5, 29.5],
      ['R13', 27.5, 30.5],
    ])
  })

  it('reads a member that ends at midnight ("24:00") as the end of the block', () => {
    const [laid] = layoutBlocks(
      [
        block({
          start: '2026-10-19T22:00:00+05:30',
          end: '2026-10-20T00:00:00+05:30',
          members: [{ request: 'R1', request_id: 1, dept: 'TRD', start: '22:00', end: '24:00' }],
        }),
      ],
      HORIZON,
    )
    expect(laid.members[0].endHour).toBe(24)
    expect(laid.endHour).toBe(24)
  })

  it('sorts by section and then by time', () => {
    const laid = layoutBlocks(
      [
        block({ id: 1, section_code: 'B-C', start: '2026-10-19T01:00:00+05:30', end: '2026-10-19T02:00:00+05:30' }),
        block({ id: 2, section_code: 'A-B', start: '2026-10-20T01:00:00+05:30', end: '2026-10-20T02:00:00+05:30' }),
        block({ id: 3, section_code: 'A-B', start: '2026-10-19T05:00:00+05:30', end: '2026-10-19T06:00:00+05:30' }),
      ],
      HORIZON,
    )
    expect(laid.map((b) => b.blockId)).toEqual([3, 2, 1])
  })

  it('keeps a reference to the source block for tooltips', () => {
    const source = block({ start: '2026-10-19T01:00:00+05:30', end: '2026-10-19T02:00:00+05:30' })
    expect(layoutBlocks([source], HORIZON)[0].source).toBe(source)
  })

  it('handles baseline blocks that have no id', () => {
    const laid = layoutBlocks(
      [block({ id: null, start: '2026-10-19T01:00:00+05:30', end: '2026-10-19T02:00:00+05:30' })],
      HORIZON,
    )
    expect(laid[0].blockId).toBeNull()
    expect(laid[0].key).toContain('b-A-B')
  })
})

describe('rows and colours', () => {
  it('draws every network section plus any extra one, sorted, without duplicates', () => {
    const blocks = [block({ section_code: 'X-Y', start: HORIZON, end: HORIZON }), block({ section_code: 'A-B', start: HORIZON, end: HORIZON })]
    expect(rowSections(['C-D', 'A-B'], blocks)).toEqual(['A-B', 'C-D', 'X-Y'])
  })

  it('colours departments consistently with a fallback', () => {
    expect(deptColor('ENGG')).not.toBe(deptColor('TRD'))
    expect(deptColor('TRD')).not.toBe(deptColor('SNT'))
    expect(deptColor('UNKNOWN')).toBe(deptColor('OTHER'))
  })
})
