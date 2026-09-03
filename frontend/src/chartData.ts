export type ChartPoint = [string | number, number]
export type ChartDatum = ChartPoint | null

/**
 * Break an XY line whenever its x value moves against its dominant direction.
 *
 * XY history is ordered by observation time, not by x. Connecting a later
 * charge that starts at a lower SOC to the previous charge draws a diagonal
 * across data that never existed. A naturally descending plot remains intact:
 * only a change against the series' prevailing direction is a reversal. A null
 * is ECharts' explicit line break, so every monotonic run remains visible
 * without inventing the join between them.
 */
export function breakAtXReversals(points: ChartPoint[]): ChartDatum[] {
  const numeric = points.flatMap(([x]) => typeof x === 'number' ? [x] : [])
  let rises = 0
  let falls = 0
  for (let index = 1; index < numeric.length; index += 1) {
    if (numeric[index]! > numeric[index - 1]!) rises += 1
    if (numeric[index]! < numeric[index - 1]!) falls += 1
  }
  const direction = rises === falls ? 0 : rises > falls ? 1 : -1
  const data: ChartDatum[] = []
  let previousX: number | null = null
  for (const point of points) {
    const x = typeof point[0] === 'number' ? point[0] : null
    const change = x !== null && previousX !== null ? x - previousX : 0
    if (direction !== 0 && change !== 0 && Math.sign(change) !== direction) data.push(null)
    data.push(point)
    previousX = x
  }
  return data
}
