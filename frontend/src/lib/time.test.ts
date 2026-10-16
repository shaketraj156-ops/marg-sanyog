import { describe, expect, it } from 'vitest'
import {
  addDays,
  daysBetween,
  fmtDate,
  fmtDateTime,
  fmtDuration,
  fmtHours,
  fmtTime,
  istFromLocalInput,
  istMidnight,
  localInputFromIso,
  mondayOf,
  nextMonday,
  percentChange,
  percentReduction,
  plural,
} from './time'

describe('IST conversion', () => {
  it('builds midnight in Asia/Kolkata', () => {
    expect(istMidnight('2026-10-19')).toBe('2026-10-19T00:00:00+05:30')
  })

  it('converts a datetime-local value', () => {
    expect(istFromLocalInput('2026-10-19T08:30')).toBe('2026-10-19T08:30:00+05:30')
    expect(istFromLocalInput('2026-10-19T08:30:45')).toBe('2026-10-19T08:30:00+05:30')
  })

  it('goes back to a datetime-local value', () => {
    expect(localInputFromIso('2026-10-19T08:30:00+05:30')).toBe('2026-10-19T08:30')
    expect(localInputFromIso(null)).toBe('')
  })
})

describe('dates', () => {
  it('adds days across month ends', () => {
    expect(addDays('2026-10-30', 3)).toBe('2026-11-02')
    expect(addDays('2026-10-19', -19)).toBe('2026-09-30')
  })

  it('counts days between dates', () => {
    expect(daysBetween('2026-10-19', '2026-10-26')).toBe(7)
    expect(daysBetween('2026-10-26', '2026-10-19')).toBe(-7)
  })

  it('formats weekday, day and month without using the browser time zone', () => {
    expect(fmtDate('2026-10-19')).toBe('Mon 19 Oct')
    expect(fmtDate('2026-10-19T23:59:00+05:30')).toBe('Mon 19 Oct')
    expect(fmtDate('2026-12-01')).toBe('Tue 1 Dec')
  })

  it('formats times and date-times straight from the string', () => {
    expect(fmtTime('2026-10-19T08:30:00+05:30')).toBe('08:30')
    expect(fmtDateTime('2026-10-19T08:30:00+05:30')).toBe('Mon 19 Oct 08:30')
    expect(fmtDateTime(null)).toBe('-')
  })

  it('finds the Monday of a week', () => {
    expect(mondayOf('2026-10-19')).toBe('2026-10-19') // already a Monday
    expect(mondayOf('2026-10-25')).toBe('2026-10-19') // Sunday
    expect(mondayOf('2026-10-22')).toBe('2026-10-19')
  })

  it('finds the next Monday', () => {
    expect(nextMonday(new Date(2026, 9, 17))).toBe('2026-10-19') // Saturday
    expect(nextMonday(new Date(2026, 9, 18))).toBe('2026-10-19') // Sunday
    expect(nextMonday(new Date(2026, 9, 19))).toBe('2026-10-19') // Monday itself
    expect(nextMonday(new Date(2026, 9, 20))).toBe('2026-10-26') // Tuesday
  })
})

describe('durations and numbers', () => {
  it('formats durations', () => {
    expect(fmtDuration(45)).toBe('45 min')
    expect(fmtDuration(120)).toBe('2 h')
    expect(fmtDuration(150)).toBe('2 h 30 min')
  })

  it('formats hours', () => {
    expect(fmtHours(24)).toBe('24 h')
    expect(fmtHours(7.5)).toBe('7.5 h')
  })

  it('computes percentage change and reduction', () => {
    expect(percentChange(15, 10)).toBe(-33)
    expect(percentReduction(15, 10)).toBe(33)
    expect(percentReduction(56, 17)).toBe(70)
    expect(percentChange(10, 15)).toBe(50)
    expect(percentReduction(10, 15)).toBe(-50)
  })

  it('has no percentage when there is no baseline', () => {
    expect(percentChange(0, 5)).toBeNull()
    expect(percentReduction(0, 0)).toBeNull()
  })
})

describe('plural', () => {
  it('uses the singular only for one', () => {
    expect(plural(1, 'train')).toBe('1 train')
    expect(plural(0, 'train')).toBe('0 trains')
    expect(plural(3, 'train')).toBe('3 trains')
    expect(plural(2, 'closure')).toBe('2 closures')
  })
})
