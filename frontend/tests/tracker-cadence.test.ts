import { describe, expect, it } from 'vitest'
import {
  CADENCE_PRESETS,
  drivingDelaySeconds,
  formatDataVolume,
  formatDuration,
  monthlyUploadBytes,
} from '../src/trackerCadence'

const megabytes = (bytes: number) => bytes / 1_000_000
const preset = (key: string) => CADENCE_PRESETS.find((item) => item.key === key)!

describe('tracker cadence', () => {
  it('prices each preset so a metered plan can be matched to one', () => {
    const priced = (key: string) => megabytes(monthlyUploadBytes(preset(key), 6))
    // The presets only earn their place if the cheap ones fit a small plan and
    // the expensive one visibly does not.
    expect(priced('live')).toBeGreaterThan(100)
    expect(priced('standard')).toBeLessThan(50)
    expect(priced('saver')).toBeLessThan(10)
    expect(priced('minimal')).toBeLessThan(5)
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

  it('never uploads as often as it samples, which is the expensive mistake', () => {
    for (const preset of CADENCE_PRESETS) {
      expect(preset.upload_seconds).toBeGreaterThan(preset.sampling_seconds)
      expect(preset.parked_upload_seconds).toBeGreaterThan(preset.parked_sampling_seconds)
    }
    // Batching is where the saving is, and it saturates: the first step is worth
    // far more than every later one put together.
    const at = (upload: number) => monthlyUploadBytes(
      { sampling_seconds: 1, upload_seconds: upload, parked_sampling_seconds: 1, parked_upload_seconds: upload }, 6,
    )
    expect(at(1) - at(5)).toBeGreaterThan((at(5) - at(300)) * 3)
  })

  it('reports how stale a long upload interval leaves the dashboard', () => {
    expect(drivingDelaySeconds({ sampling_seconds: 15, upload_seconds: 900, parked_sampling_seconds: 600, parked_upload_seconds: 1800 })).toBe(900)
    expect(formatDuration(900, 'en')).toContain('15')
    expect(formatDuration(45, 'en')).toContain('45')
  })

  it('charges for signals and for requests', () => {
    const saver = preset('saver')
    expect(monthlyUploadBytes(saver, 20)).toBeGreaterThan(monthlyUploadBytes(saver, 0))
    const chatty = { ...saver, upload_seconds: saver.sampling_seconds, parked_upload_seconds: saver.parked_sampling_seconds }
    expect(monthlyUploadBytes(chatty)).toBeGreaterThan(monthlyUploadBytes(saver))
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
