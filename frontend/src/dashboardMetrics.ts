/** How a card draws what it was given, and therefore how much it can be given. */
export type CardPresentation = 'reading' | 'gauge' | 'table' | 'chart'

/**
 * Whether a presentation can show more than one metric.
 *
 * This is a property of the drawing, not a preference. A gauge is a proportion of
 * one thing and a reading is one number; asking either to show a second would mean
 * inventing an arrangement neither has. A table and a chart are lists by nature and
 * take as many as they are given.
 */
export function presentationAllowsMany(presentation: CardPresentation): boolean {
  return presentation === 'table' || presentation === 'chart'
}

/**
 * Resolve what a card asked for against what a vehicle actually reports.
 *
 * A pattern is either an exact canonical name or a prefix ending in `*`. Exact is
 * predictable and is what a card about one reading wants; a prefix keeps a card
 * correct when a profile gains a signal, so a card asking for `tyre.*` shows a
 * fourth wheel without being edited.
 *
 * Order follows the patterns, so a card's arrangement is the author's rather than
 * whatever order the vehicle happened to report in, and a metric matched twice
 * appears once.
 */
export function resolveMetricPatterns(patterns: string[], available: string[]): string[] {
  const resolved: string[] = []
  const seen = new Set<string>()
  for (const pattern of patterns) {
    const matches = pattern.endsWith('*')
      ? available.filter((name) => name.startsWith(pattern.slice(0, -1))).sort()
      : available.filter((name) => name === pattern)
    for (const name of matches) {
      if (seen.has(name)) continue
      seen.add(name)
      resolved.push(name)
    }
  }
  return resolved
}

/**
 * What a card will actually draw.
 *
 * A presentation that shows one metric is given one even when its patterns match
 * more, because the alternative is a card that silently drops the difference or
 * draws something its shape cannot hold. Which one it keeps is the first the
 * patterns named, so the choice stays the author's.
 */
export function metricsForCard(
  patterns: string[],
  available: string[],
  presentation: CardPresentation,
): string[] {
  const resolved = resolveMetricPatterns(patterns, available)
  return presentationAllowsMany(presentation) ? resolved : resolved.slice(0, 1)
}
