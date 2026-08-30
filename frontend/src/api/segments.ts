import { api } from './client'
import type { History, HistoryObservationSample, HistoryObservations, HistoryTable, Segments } from './types'

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

export interface HistoryRange {
  start: Date | string
  end?: Date | string
  maxPoints?: number
}

export async function loadHistory(vehicleId: string, range: HistoryRange): Promise<History> {
  const instant = (value: Date | string) => encodeURIComponent(typeof value === 'string' ? value : value.toISOString())
  const query = [
    `start=${instant(range.start)}`,
    ...(range.end ? [`end=${instant(range.end)}`] : []),
    `max_points=${range.maxPoints ?? 300}`,
  ].join('&')
  return api<History>(`/vehicles/${vehicleId}/history?${query}`)
}

/**
 * The steps the table endpoint accepts.
 *
 * Mirrors TABLE_STEPS in the history routes, which rejects anything else with a
 * 400 rather than rounding to something it likes. There is no endpoint that
 * lists them, so the two lists are kept in step by hand and the picker offers
 * only these.
 */
export const TABLE_STEP_SECONDS = [1, 5, 10, 30, 60, 300, 900, 3600, 21600, 86400] as const

/**
 * A row says when it starts and ends and what was known by then, but not how
 * many observations landed inside it. The timeline infers that from whether any
 * cell was observed within the bucket, which mistakes a report whose values had
 * all expired for an expiry-born row. A per-row count of received reports, say
 * `reports: number` on HistoryTableRow, would make it exact; until then the
 * inference is what the table shows.
 */
export interface HistoryTableRequest {
  start: Date | string
  end?: Date | string
  stepSeconds: number
  limit?: number
  offset?: number
}

export async function loadHistoryTable(vehicleId: string, request: HistoryTableRequest): Promise<HistoryTable> {
  const instant = (value: Date | string) => encodeURIComponent(typeof value === 'string' ? value : value.toISOString())
  const query = [
    `start=${instant(request.start)}`,
    ...(request.end ? [`end=${instant(request.end)}`] : []),
    `step_seconds=${request.stepSeconds}`,
    `limit=${request.limit ?? 100}`,
    `offset=${request.offset ?? 0}`,
  ].join('&')
  return api<HistoryTable>(`/vehicles/${vehicleId}/history/table?${query}`)
}

/**
 * The provenance behind one recorded sample.
 *
 * The endpoint pages by time rather than by id, so the sample is fetched through
 * the second it was recorded in and picked out by id. That keeps the grid on
 * /entries, which is the only endpoint that can sort and filter, and asks for
 * provenance only for the row somebody opened.
 */
export async function loadSampleProvenance(vehicleId: string, sample: { id: string; recorded_at: string }): Promise<HistoryObservationSample | null> {
  const start = new Date(sample.recorded_at)
  const end = new Date(start.getTime() + 1000)
  const query = [
    `start=${encodeURIComponent(start.toISOString())}`,
    `end=${encodeURIComponent(end.toISOString())}`,
    'limit=500',
  ].join('&')
  const page = await api<HistoryObservations>(`/vehicles/${vehicleId}/history/observations?${query}`)
  return page.samples.find((row) => row.id === sample.id) ?? null
}
