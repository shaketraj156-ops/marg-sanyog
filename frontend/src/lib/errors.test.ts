import { describe, expect, it } from 'vitest'
import { ApiError } from '../api/client'
import { describeError, describeWait } from './errors'

describe('describeWait', () => {
  it('counts short waits in seconds', () => {
    expect(describeWait('Too many login attempts from this address. Try again in 45 seconds.')).toBe(
      'Too many login attempts from this address. Try again in 45 seconds.',
    )
    expect(describeWait('Try again in 1 seconds.')).toBe('Try again in 1 second.')
  })

  it('counts long waits in minutes, rounding up', () => {
    expect(describeWait('Too many failed attempts. Try again in 900 seconds.')).toBe(
      'Too many failed attempts. Try again in 15 minutes.',
    )
    expect(describeWait('Try again in 121 seconds.')).toBe('Try again in 3 minutes.')
  })

  it('leaves other text alone', () => {
    expect(describeWait('Something else')).toBe('Something else')
  })
})

describe('describeError for a lockout', () => {
  it('shows the wait in minutes', () => {
    const error = new ApiError(429, 'too_many_attempts', 'Too many failed attempts. Try again in 900 seconds.')
    expect(describeError(error)).toBe('Too many failed attempts. Try again in 15 minutes.')
  })
})
