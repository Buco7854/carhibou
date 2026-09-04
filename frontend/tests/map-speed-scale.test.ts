import { describe, expect, it } from 'vitest'
import { TRAIL_BAND_COUNT, bandFor, speedBands } from '../src/mapSpeedScale'

describe('trail speed scale', () => {
  it('scales to the drive it is plotting rather than to a fixed ladder', () => {
    // A town run and a motorway run share no speed at all. Under the old fixed
    // stops (0-30-60-90-120) the first was one colour end to end and the second
    // was another, so in both cases the ramp said nothing.
    const town = speedBands([0, 6, 11, 17, 23, 28])
    const motorway = speedBands([96, 101, 108, 114, 119, 126])
    expect(town.at(0)!.from).toBe(0)
    expect(town.at(-1)!.to).toBe(28)
    expect(motorway.at(0)!.from).toBe(96)
    expect(motorway.at(-1)!.to).toBe(126)
    // Both use the whole ramp, so both separate their own slow from their own fast.
    expect(town.at(0)!.step).toBe(1)
    expect(town.at(-1)!.step).toBe(TRAIL_BAND_COUNT)
    expect(motorway.at(-1)!.step).toBe(TRAIL_BAND_COUNT)
  })

  it('separates close speeds instead of collapsing them into one colour', () => {
    // Most of this drive sits between 28 and 34, with one motorway stretch. A
    // linear minimum-to-maximum ramp puts every one of those points in its
    // palest band; equal population per band keeps them apart.
    const speeds = [28, 29, 30, 31, 32, 33, 34, 120]
    const bands = speedBands(speeds)
    const steps = new Set(speeds.slice(0, 7).map((speed) => bandFor(speed, bands)!.step))
    expect(steps.size).toBeGreaterThan(1)
    expect(bandFor(120, bands)!.step).toBe(TRAIL_BAND_COUNT)
  })

  it('never offers a band no point falls in', () => {
    // Half of this drive stood still, so there are fewer distinct edges than
    // bands. An empty band would be a legend entry that means nothing.
    const bands = speedBands([0, 0, 0, 0, 0, 0, 40, 80])
    expect(bands.length).toBeLessThan(TRAIL_BAND_COUNT)
    for (const band of bands) expect(band.to).toBeGreaterThan(band.from)
    expect(bands.at(-1)!.step).toBe(TRAIL_BAND_COUNT)
  })

  it('claims nothing about a drive at one speed, or about a trail with none', () => {
    const flat = speedBands([50, 50, 50])
    expect(flat).toHaveLength(1)
    // The middle of the ramp: neither "crawling" nor "careful" is established.
    expect(flat[0]!.step).toBe(Math.ceil(TRAIL_BAND_COUNT / 2))
    expect(speedBands([null, undefined, Number.NaN])).toEqual([])
  })

  it('reads an unreported speed as an absence rather than as the slowest band', () => {
    const bands = speedBands([0, 20, 40, 60, 80, 100])
    expect(bandFor(null, bands)).toBeNull()
    expect(bandFor(undefined, bands)).toBeNull()
    // Ends are inclusive: the fastest point belongs to the fastest band.
    expect(bandFor(100, bands)!.step).toBe(TRAIL_BAND_COUNT)
    expect(bandFor(0, bands)!.step).toBe(1)
  })
})
