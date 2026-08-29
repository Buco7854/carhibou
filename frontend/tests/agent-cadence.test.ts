import { describe, expect, it } from 'vitest'
import {
  CADENCE_PRESETS,
  drivingDelaySeconds,
  formatDataVolume,
  monthlyUploadBytes,
} from '../src/agentCadence'

const megabytes = (bytes: number) => bytes / 1_000_000
const preset = (key: string) => CADENCE_PRESETS.find((item) => item.key === key)!

describe('agent cadence', () => {
  it('prices each preset so a metered plan can be matched to one', () => {
    const priced = (key: string) => megabytes(monthlyUploadBytes(preset(key), 6))
    // The presets only earn their place if the cheap ones fit a small plan and
    // the expensive one visibly does not.
    expect(priced('live')).toBeGreaterThan(100)
    expect(priced('standard')).toBeLessThan(50)
    expect(priced('saver')).toBeLessThan(20)
    expect(priced('frugal')).toBeLessThan(10)
    expect(priced('minimal')).toBeLessThan(3)
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
    // Never driven still costs the parked cadence, because the agent is powered.
    expect(monthlyUploadBytes(standard, 6, 0)).toBeGreaterThan(0)
    // Out-of-range hours are clamped rather than producing a negative month.
    expect(monthlyUploadBytes(standard, 6, 99)).toBe(monthlyUploadBytes(standard, 6, 24))
    expect(monthlyUploadBytes(standard, 6, -5)).toBe(monthlyUploadBytes(standard, 6, 0))
  })

  it('uploads as often as it samples, so no preset adds lag of its own', () => {
    for (const preset of CADENCE_PRESETS) {
      expect(preset.upload_seconds).toBe(preset.sampling_seconds)
      expect(preset.parked_upload_seconds).toBe(preset.parked_sampling_seconds)
      // A reading cannot appear before it is taken, so this is the floor rather
      // than a delay the preset chose to add.
      expect(drivingDelaySeconds(preset)).toBe(preset.sampling_seconds)
    }
  })

  it('saves data by lowering resolution, which is the compromise on offer', () => {
    for (const [faster, slower] of ['live standard', 'standard saver', 'saver frugal', 'frugal minimal'].map(
      (pair) => pair.split(' ').map(preset),
    )) {
      expect(slower!.sampling_seconds).toBeGreaterThan(faster!.sampling_seconds)
      expect(monthlyUploadBytes(slower!, 6)).toBeLessThan(monthlyUploadBytes(faster!, 6))
    }
  })

  it('counts delaying the upload past the sample as lag, and only that', () => {
    const matched = { sampling_seconds: 30, upload_seconds: 30, parked_sampling_seconds: 600, parked_upload_seconds: 600 }
    expect(drivingDelaySeconds(matched)).toBe(30)
    // Holding samples back adds their wait on top of the sampling floor.
    expect(drivingDelaySeconds({ ...matched, upload_seconds: 900 })).toBe(900)
  })

  it('charges for signals and for requests', () => {
    const saver = preset('saver')
    expect(monthlyUploadBytes(saver, 20)).toBeGreaterThan(monthlyUploadBytes(saver, 0))
    // Batching does save, which is what makes it a trade rather than a free
    // choice: the interface offers it and prices the lag it costs.
    const delayed = { ...saver, upload_seconds: 900, parked_upload_seconds: 1800 }
    expect(monthlyUploadBytes(delayed)).toBeLessThan(monthlyUploadBytes(saver))
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
