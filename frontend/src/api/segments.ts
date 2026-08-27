import { api } from './client'
import type { History, Segments } from './types'

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
