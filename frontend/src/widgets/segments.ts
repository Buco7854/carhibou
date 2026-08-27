import { api } from '../api/client'
import type { ChargeSegment, DriveSegment, History, SegmentKind, Segments, SelectedSegment } from '../api/types'

export interface FeedSegment {
  kind: SegmentKind
  start: string
  end: string
  duration_seconds: number
  drive?: DriveSegment
  charge?: ChargeSegment
}

export const EMPTY_SEGMENTS: Segments = { drives: [], charges: [] }

export function rangeStart(days: number, now = Date.now()): Date {
  return new Date(now - days * 86_400_000)
}

function timed(row: unknown): boolean {
  const candidate = row as { start?: unknown; end?: unknown }
  return Boolean(row) && typeof candidate.start === 'string' && typeof candidate.end === 'string'
}

/** A segment response missing or malforming either list degrades to an empty one. */
export function normalizeSegments(value: unknown): Segments {
  const source = (value ?? {}) as { drives?: unknown; charges?: unknown }
  return {
    drives: Array.isArray(source.drives) ? source.drives.filter(timed) : [],
    charges: Array.isArray(source.charges) ? source.charges.filter(timed) : [],
  }
}

export async function loadSegmentsBetween(vehicleId: string, start: Date, end: Date): Promise<Segments> {
  const query = `start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`
  return api<unknown>(`/vehicles/${vehicleId}/segments?${query}`).then(normalizeSegments).catch(() => EMPTY_SEGMENTS)
}

export async function loadSegments(vehicleId: string, days: number): Promise<Segments> {
  return loadSegmentsBetween(vehicleId, rangeStart(days), new Date())
}

export async function loadSegmentHistory(vehicleId: string, segment: { start: string; end: string }, maxPoints = 400): Promise<History> {
  const query = `start=${encodeURIComponent(segment.start)}&end=${encodeURIComponent(segment.end)}&max_points=${maxPoints}`
  return api<History>(`/vehicles/${vehicleId}/history?${query}`)
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

/** The selection when it is in range and of the wanted kind, else the newest one. */
export function followSelection(feed: FeedSegment[], selected: SelectedSegment | null, kind?: SegmentKind): FeedSegment | null {
  const candidates = kind ? feed.filter((segment) => segment.kind === kind) : feed
  return candidates.find((segment) => isSelected(selected, segment)) ?? candidates[0] ?? null
}

export function metricNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

const EARTH_RADIUS_KM = 6371

export function haversineKm(from: { lat: number; lng: number }, to: { lat: number; lng: number }): number {
  const toRad = (degrees: number) => (degrees * Math.PI) / 180
  const deltaLat = toRad(to.lat - from.lat)
  const deltaLng = toRad(to.lng - from.lng)
  const a = Math.sin(deltaLat / 2) ** 2
    + Math.cos(toRad(from.lat)) * Math.cos(toRad(to.lat)) * Math.sin(deltaLng / 2) ** 2
  return 2 * EARTH_RADIUS_KM * Math.asin(Math.min(1, Math.sqrt(a)))
}
