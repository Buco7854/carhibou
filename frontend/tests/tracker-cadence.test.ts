import { describe, expect, it } from 'vitest'
import { CADENCE_PRESETS, formatDataVolume, monthlyUploadBytes } from '../src/trackerCadence'

const megabytes = (bytes: number) => bytes / 1_000_000
const preset = (key: string) => CADENCE_PRESETS.find((item) => item.key === key)!

describe('tracker cadence', () => {
  it('prices each preset so a metered plan can be matched to one', () => {
    const priced = (key: string) => megabytes(monthlyUploadBytes(preset(key), 6))
    // The presets only earn their place if the cheap ones fit a small plan and
    // the expensive one visibly does not.
    expect(priced('live')).toBeGreaterThan(100)
    expect(priced('standard')).toBeGreaterThan(50)
    expect(priced('saver')).toBeLessThan(50)
    expect(priced('minimal')).toBeLessThan(10)
    expect(CADENCE_PRESETS.map((item) => priced(item.key))).toEqual(
      [...CADENCE_PRESETS.map((item) => priced(item.key))].sort((left, right) => right - left),
    )
  })

  it('is dominated by the parked cadence, because that is most of the month', () => {
    const live = preset('live')
    const drivingOnly = { ...live, parked_sampling_seconds: live.sampling_seconds, parked_upload_seconds: live.upload_seconds }
    // One second everywhere against one second driving: the parked cadence is
    // what makes a live driving cadence affordable at all.
    expect(monthlyUploadBytes(drivingOnly, 6)).toBeGreaterThan(monthlyUploadBytes(live, 6) * 4)
  })

  it('weighs the estimate by how much the vehicle is driven', () => {
    const standard = preset('standard')
    expect(monthlyUploadBytes(standard, 6, 4)).toBeGreaterThan(monthlyUploadBytes(standard, 6, 1))
    // Never driven still costs the parked cadence, because the tracker is powered.
    expect(monthlyUploadBytes(standard, 6, 0)).toBeGreaterThan(0)
    // Out-of-range hours are clamped rather than producing a negative month.
    expect(monthlyUploadBytes(standard, 6, 99)).toBe(monthlyUploadBytes(standard, 6, 24))
    expect(monthlyUploadBytes(standard, 6, -5)).toBe(monthlyUploadBytes(standard, 6, 0))
  })

  it('charges for signals and for requests', () => {
    const saver = preset('saver')
    expect(monthlyUploadBytes(saver, 20)).toBeGreaterThan(monthlyUploadBytes(saver, 0))
    const batched = { ...saver, upload_seconds: 600, parked_upload_seconds: 3600 }
    expect(monthlyUploadBytes(batched)).toBeLessThan(monthlyUploadBytes(saver))
  })

  it('stops batching beyond the agent limit of 500 samples per request', () => {
    const base = { sampling_seconds: 1, upload_seconds: 500, parked_sampling_seconds: 1, parked_upload_seconds: 500 }
    const beyond = { ...base, upload_seconds: 5000, parked_upload_seconds: 5000 }
    expect(monthlyUploadBytes(beyond)).toBeCloseTo(monthlyUploadBytes(base), 5)
  })

  it('reports nothing rather than infinity for an unusable interval', () => {
    expect(monthlyUploadBytes({ sampling_seconds: 0, upload_seconds: 60, parked_sampling_seconds: 0, parked_upload_seconds: 60 })).toBe(0)
  })

  it('scales the unit to the volume', () => {
    expect(formatDataVolume(4_900_000, 'en')).toBe('4.9 MB')
    expect(formatDataVolume(296_000_000, 'en')).toBe('296 MB')
    expect(formatDataVolume(1_520_000_000, 'en')).toBe('1.5 GB')
  })
})
