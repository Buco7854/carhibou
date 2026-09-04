/**
 * The colour scale a speed trail is painted with.
 *
 * A fixed ramp (0-30-60-90-120) tells a reader almost nothing about the drive
 * they are looking at: a town run spends every metre in one band and a motorway
 * run spends every metre in another, so in both cases the colour is a constant
 * and the segments carry no information. The scale therefore comes from the data
 * actually plotted.
 *
 * It is quantile-based rather than linear between the drive's own minimum and
 * maximum, because drive speeds are not evenly distributed: a drive is mostly
 * junctions, queues and one steady cruise, so a linear scale collapses the
 * bottom two thirds of the points into the palest band and separates nothing.
 * Equal population per band means two speeds that differ end up in different
 * bands whenever there are points between them, which is exactly the complaint
 * a linear scale earns. The price is that a band's width in km/h is no longer
 * constant, which is why the legend prints the real edges instead of a gradient.
 *
 * Bands are deduplicated rather than forced to five: a drive that stood still
 * for half of its points has fewer distinct edges than bands, and an empty band
 * in the legend would be a colour that means nothing.
 */

/** Steps in the ramp, and so the most bands a trail can carry. */
export const TRAIL_BAND_COUNT = 5

export interface SpeedBand {
  /** The slowest speed this band covers. */
  from: number
  /** The fastest speed this band covers. */
  to: number
  /** Which ramp step paints it, 1 (slowest) to TRAIL_BAND_COUNT (fastest). */
  step: number
}

function finiteSpeeds(speeds: ReadonlyArray<number | null | undefined>): number[] {
  return speeds
    .filter((speed): speed is number => typeof speed === 'number' && Number.isFinite(speed))
    .sort((left, right) => left - right)
}

/**
 * The bands the plotted speeds earn, slowest first.
 *
 * One band when every point reports the same speed, none when no point reports
 * one at all: an unknown speed is an absence, and absences are drawn in the
 * muted ink rather than given a place on the scale.
 */
export function speedBands(speeds: ReadonlyArray<number | null | undefined>): SpeedBand[] {
  const sorted = finiteSpeeds(speeds)
  if (!sorted.length) return []
  const slowest = sorted[0]!
  const fastest = sorted.at(-1)!
  // Nothing varies, so nothing is being encoded; the middle step avoids claiming
  // either "careful" or "crawling" about a drive at one constant speed.
  if (slowest === fastest) return [{ from: slowest, to: fastest, step: Math.ceil(TRAIL_BAND_COUNT / 2) }]

  const edges: number[] = []
  for (let quantile = 1; quantile < TRAIL_BAND_COUNT; quantile += 1) {
    const rank = Math.ceil((quantile / TRAIL_BAND_COUNT) * sorted.length) - 1
    const edge = sorted[Math.min(sorted.length - 1, Math.max(0, rank))]!
    if (edge > slowest && edge < fastest && !edges.includes(edge)) edges.push(edge)
  }

  const bounds = [slowest, ...edges, fastest]
  const count = bounds.length - 1
  return Array.from({ length: count }, (_, index) => ({
    from: bounds[index]!,
    to: bounds[index + 1]!,
    // Fewer bands than steps still reach the top of the ramp, so the fastest
    // stretch of any drive is the reddest thing on the map.
    step: 1 + Math.round((index * (TRAIL_BAND_COUNT - 1)) / (count - 1)),
  }))
}

/** The band a speed falls in, or null when the trail has no scale at all. */
export function bandFor(speed: number | null | undefined, bands: readonly SpeedBand[]): SpeedBand | null {
  if (!bands.length || typeof speed !== 'number' || !Number.isFinite(speed)) return null
  return bands.find((band) => speed <= band.to) ?? bands.at(-1)!
}
