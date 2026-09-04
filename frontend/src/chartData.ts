export type ChartPoint = [string | number, number]
export type ChartDatum = ChartPoint | null

/**
 * Split an XY line wherever its x value moves against its dominant direction.
 *
 * XY history is ordered by observation time, not by x. Connecting a later
 * charge that starts at a lower SOC to the previous charge draws a diagonal
 * across data that never existed. A naturally descending plot remains intact:
 * only a change against the series' prevailing direction is a reversal, and
 * each stretch between two reversals is one run — for a charge curve, one
 * session.
 *
 * Runs are returned rather than only broken apart because who they belong to is
 * worth saying: a caller that knows when each run began can name it, and a
 * caller that does not can join them back with a break between.
 */
export function splitAtXReversals(points: ChartPoint[]): ChartPoint[][] {
  const numeric = points.flatMap(([x]) => typeof x === 'number' ? [x] : [])
  let rises = 0
  let falls = 0
  for (let index = 1; index < numeric.length; index += 1) {
    if (numeric[index]! > numeric[index - 1]!) rises += 1
    if (numeric[index]! < numeric[index - 1]!) falls += 1
  }
  const direction = rises === falls ? 0 : rises > falls ? 1 : -1
  const runs: ChartPoint[][] = []
  let run: ChartPoint[] = []
  let previousX: number | null = null
  for (const point of points) {
    const x = typeof point[0] === 'number' ? point[0] : null
    const change = x !== null && previousX !== null ? x - previousX : 0
    if (direction !== 0 && change !== 0 && Math.sign(change) !== direction && run.length) {
      runs.push(run)
      run = []
    }
    run.push(point)
    previousX = x
  }
  if (run.length) runs.push(run)
  return runs
}

/**
 * The same runs as one series, with ECharts' explicit break between them.
 *
 * For a caller with nothing to say about which run is which: every monotonic
 * run stays visible and the join between them is never invented.
 */
export function breakAtXReversals(points: ChartPoint[]): ChartDatum[] {
  return splitAtXReversals(points).flatMap<ChartDatum>((run, index) => (index ? [null, ...run] : run))
}

/**
 * The spacing a series actually keeps, ignoring the outliers that motivate all
 * of this: the median gap is what the source does, not what it did once.
 */
export function medianGap(stamps: number[]): number {
  if (stamps.length < 2) return Number.POSITIVE_INFINITY
  const gaps = stamps.slice(1).map((at, index) => at - stamps[index]!).sort((left, right) => left - right)
  return gaps[Math.floor(gaps.length / 2)] ?? Number.POSITIVE_INFINITY
}

/**
 * How long a source may go quiet before the line across the silence is a guess.
 *
 * Three of the source's own intervals is generous enough to survive jitter and
 * a dropped sample, and short enough that an outage is never dressed up as a
 * slow change. The floor is what keeps the two compatible: a car sampling every
 * 15 s while driving would otherwise break its line on any single missed
 * report, which says "no data" about a span the source can perfectly well
 * vouch for.
 *
 * The cadence is measured rather than declared because history rows do not
 * carry the delivery promise the upload arrived under — only the raw samples on
 * /history/observations do, and those never reach a chart.
 */
const GAP_TOLERANCE = 3
const MIN_VOUCHED_MS = 60_000

function vouchedSpan(stamps: number[]): number {
  const median = medianGap(stamps)
  if (!Number.isFinite(median)) return Number.POSITIVE_INFINITY
  return Math.max(MIN_VOUCHED_MS, median * GAP_TOLERANCE)
}

/**
 * Break a time series wherever its source reported nothing at all.
 *
 * The same problem `breakAtXReversals` solves for an XY plot's axis: a line is
 * a claim about what happened between its ends, and two readings either side of
 * an outage are not evidence of anything in between. A car that sent 0 km/h at
 * 11:17, went silent, and sent 90 km/h at 17:54 was drawn as a six-hour
 * acceleration. A null is ECharts' explicit break, so each span the source
 * covered stays visible and the gap between them stays empty — the area fill
 * splits with the line, since `connectNulls` is false for both.
 */
export function breakAtTimeGaps(points: ChartPoint[]): ChartDatum[] {
  const stamps = points.map(([x]) => typeof x === 'number' ? x : Date.parse(x))
  const limit = vouchedSpan(stamps.filter((at) => Number.isFinite(at)))
  if (!Number.isFinite(limit)) return [...points]
  const data: ChartDatum[] = []
  points.forEach((point, index) => {
    if (index > 0 && stamps[index]! - stamps[index - 1]! > limit) data.push(null)
    data.push(point)
  })
  return data
}
