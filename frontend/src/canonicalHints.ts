/**
 * Whether an author's output key is a near miss of a canonical one.
 *
 * A profile may legitimately publish anything: a key nobody agreed on is still
 * recorded and still usable. So this never decides anything, it only notices
 * that `battery_soc` was probably meant to be `battery.soc` and says so. A key
 * that looks nothing like a canonical one gets no suggestion at all, because a
 * wrong guess is worse than silence for somebody who meant what they typed.
 */

/** Separators and case carry no meaning here, so comparison drops both. */
function flatten(key: string): string {
  return key.toLowerCase().replace(/[^a-z0-9]/g, '')
}

function editDistance(left: string, right: string): number {
  let previous = Array.from({ length: right.length + 1 }, (_unused, index) => index)
  for (let row = 1; row <= left.length; row += 1) {
    const current = [row]
    for (let column = 1; column <= right.length; column += 1) {
      current[column] = Math.min(
        previous[column]! + 1,
        current[column - 1]! + 1,
        previous[column - 1]! + (left[row - 1] === right[column - 1] ? 0 : 1),
      )
    }
    previous = current
  }
  return previous[right.length]!
}

/**
 * How far off a key may be and still be treated as the same key mistyped.
 * Short names are allowed one slip; anything shorter than four characters is
 * too easy to land near a real key by accident.
 */
function tolerance(flat: string): number {
  if (flat.length < 4) return 0
  return flat.length <= 6 ? 1 : 2
}

export function suggestCanonicalKey(candidate: string, canonical: readonly string[]): string | null {
  const typed = candidate.trim()
  // Position is not a metric, and its targets are canonical in their own right.
  if (!typed || typed.startsWith('position.') || canonical.includes(typed)) return null

  const flat = flatten(typed)
  if (!flat) return null
  // Ties are broken by name so the same key always draws the same suggestion.
  const ordered = [...canonical].sort()

  // Written with the wrong separators or in camel case.
  const spelled = ordered.find((key) => flatten(key) === flat)
  if (spelled) return spelled

  // Written without its namespace: `soc` for `battery.soc`.
  const bare = ordered.find((key) => flatten(key.split('.').slice(1).join('.')) === flat)
  if (bare) return bare

  const limit = tolerance(flat)
  if (!limit) return null
  let best: { key: string; distance: number } | null = null
  for (const key of ordered) {
    // Compared whole and unqualified, so `batery.soc` and `bttery` both land.
    const distance = Math.min(
      editDistance(flat, flatten(key)),
      editDistance(flat, flatten(key.split('.').slice(1).join('.'))),
    )
    if (distance <= limit && (!best || distance < best.distance)) best = { key, distance }
  }
  return best?.key ?? null
}
