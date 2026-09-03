import { describe, expect, it } from 'vitest'
import { breakAtXReversals } from '../src/chartData'

describe('XY chart line runs', () => {
  it('does not connect separate charge sessions across a lower starting SOC', () => {
    expect(breakAtXReversals([
      [55, 3.2], [75, 3.1], [100, 0.2],
      [42, 3.3], [60, 3.2],
    ])).toEqual([
      [55, 3.2], [75, 3.1], [100, 0.2],
      null,
      [42, 3.3], [60, 3.2],
    ])
  })

  it('keeps equal and increasing x values in one run', () => {
    expect(breakAtXReversals([[55, 3.2], [55, 3.1], [56, 3.3]]))
      .toEqual([[55, 3.2], [55, 3.1], [56, 3.3]])
  })

  it('keeps a naturally descending series connected', () => {
    expect(breakAtXReversals([[82, 2], [77, 11], [71, 6]]))
      .toEqual([[82, 2], [77, 11], [71, 6]])
  })
})
