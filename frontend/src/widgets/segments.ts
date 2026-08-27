import { normalizeSegments } from '../api/segments'
import type { ChargeSegment, DriveSegment, SegmentKind, Segments, SelectedSegment } from '../api/types'

export interface FeedSegment {
  kind: SegmentKind
  start: string
  end: string
  duration_seconds: number
  drive?: DriveSegment
  charge?: ChargeSegment
}

export function mergeSegments(segments: Segments | null | undefined): FeedSegment[] {
  const safe = normalizeSegments(segments)
  const drives = safe.drives.map<FeedSegment>((drive) => ({ kind: 'drive', start: drive.start, end: drive.end, duration_seconds: drive.duration_seconds ?? 0, drive }))
  const charges = safe.charges.map<FeedSegment>((charge) => ({ kind: 'charge', start: charge.start, end: charge.end, duration_seconds: charge.duration_seconds ?? 0, charge }))
  return [...drives, ...charges].sort((left, right) => right.start.localeCompare(left.start))
}

export function segmentKey(segment: { kind: SegmentKind; start: string }): string {
  return `${segment.kind}:${segment.start}`
}

export function isSelected(selected: SelectedSegment | null, segment: FeedSegment): boolean {
  return Boolean(selected) && selected!.kind === segment.kind && selected!.start === segment.start
}

export type FollowResult =
  | { state: 'segment'; segment: FeedSegment }
  | { state: 'out-of-range' }
  | { state: 'none' }

/**
 * A follower shows the selection when its own range holds it. When a selection
 * exists that this range cannot show, saying so beats quietly showing another
 * segment; the newest-segment fallback is only for having no selection at all.
 */
export function followSelection(feed: FeedSegment[], selected: SelectedSegment | null, kind?: SegmentKind): FollowResult {
  const candidates = kind ? feed.filter((segment) => segment.kind === kind) : feed
  if (selected) {
    const match = candidates.find((segment) => isSelected(selected, segment))
    return match ? { state: 'segment', segment: match } : { state: 'out-of-range' }
  }
  const newest = candidates[0]
  return newest ? { state: 'segment', segment: newest } : { state: 'none' }
}

export function metricNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}
