import { describe, expect, it } from 'vitest'
import { breakAtTimeGaps, breakAtXReversals } from '../src/chartData'

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

describe('time series gaps', () => {
  /** The driving cadence from the reported bug: a sample about every 15 s. */
  const driving = [
    '2026-09-04T08:13:51Z', '2026-09-04T08:14:06Z', '2026-09-04T08:14:21Z',
    '2026-09-04T08:14:37Z', '2026-09-04T08:14:52Z', '2026-09-04T08:15:07Z',
    '2026-09-04T08:15:23Z', '2026-09-04T08:15:38Z', '2026-09-04T08:15:53Z',
    '2026-09-04T08:16:12Z',
  ]
  const speeds = (stamps: string[], value: number) => stamps.map((at) => [at, value] as [string, number])

  it('breaks the line where the source reported nothing for an hour and a half', () => {
    const points = [...speeds(driving, 30), ['2026-09-04T09:54:48Z', 0] as [string, number]]
    const data = breakAtTimeGaps(points)
    expect(data).toEqual([...speeds(driving, 30), null, ['2026-09-04T09:54:48Z', 0]])
  })

  it('leaves an uninterrupted drive in one run', () => {
    expect(breakAtTimeGaps(speeds(driving, 30))).toEqual(speeds(driving, 30))
  })

  it('absorbs a single dropped sample rather than fracturing a 15 s cadence', () => {
    const dropped = driving.filter((at) => at !== '2026-09-04T08:14:52Z')
    expect(breakAtTimeGaps(speeds(dropped, 30))).toEqual(speeds(dropped, 30))
  })

  it('keeps a parked car reporting every ten minutes connected to itself', () => {
    const parked = [0, 10, 20, 30, 40].map((minute) => `2026-09-04T02:${String(minute).padStart(2, '0')}:00Z`)
    expect(breakAtTimeGaps(speeds(parked, 0))).toEqual(speeds(parked, 0))
  })

  it('has no cadence to judge a lone reading against, so it breaks nothing', () => {
    expect(breakAtTimeGaps([['2026-09-04T08:13:51Z', 30]])).toEqual([['2026-09-04T08:13:51Z', 30]])
  })
})
