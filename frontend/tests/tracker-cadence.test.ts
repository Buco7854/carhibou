import { describe, expect, it } from 'vitest'
import { CADENCE_PRESETS, formatDataVolume, monthlyUploadBytes } from '../src/trackerCadence'

const megabytes = (bytes: number) => bytes / 1_000_000

describe('tracker cadence', () => {
  it('prices each preset so a metered plan can be matched to one', () => {
    const priced = Object.fromEntries(
      CADENCE_PRESETS.map((preset) => [
        preset.key,
        megabytes(monthlyUploadBytes(preset.samplingSeconds, preset.uploadSeconds, 6)),
      ]),
    )
    // The point of the presets is that the cheap ones fit a small plan and the
    // expensive one visibly does not.
    expect(priced.live).toBeGreaterThan(1000)
    expect(priced.standard).toBeGreaterThan(50)
    expect(priced.saver).toBeLessThan(50)
    expect(priced.minimal).toBeLessThan(10)
  })

  it('charges for signals and for requests', () => {
    const bare = monthlyUploadBytes(60, 600, 0)
    const withSignals = monthlyUploadBytes(60, 600, 20)
    expect(withSignals).toBeGreaterThan(bare)

    // Uploading in larger batches costs fewer requests at the same sample rate.
    expect(monthlyUploadBytes(5, 600)).toBeLessThan(monthlyUploadBytes(5, 10))
  })

  it('stops batching beyond the agent limit of 500 samples per request', () => {
    // Past the cap a longer interval cannot reduce the request count further.
    expect(monthlyUploadBytes(1, 500)).toBeCloseTo(monthlyUploadBytes(1, 5000), 5)
  })

  it('reports nothing rather than infinity for an unusable interval', () => {
    expect(monthlyUploadBytes(0, 60)).toBe(0)
    expect(monthlyUploadBytes(60, 0)).toBe(0)
  })

  it('scales the unit to the volume', () => {
    expect(formatDataVolume(4_900_000, 'en')).toBe('4.9 MB')
    expect(formatDataVolume(296_000_000, 'en')).toBe('296 MB')
    expect(formatDataVolume(1_520_000_000, 'en')).toBe('1.5 GB')
  })
})
