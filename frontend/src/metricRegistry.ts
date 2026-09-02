import { readonly, ref } from 'vue'
import { api } from './api/client'
import type { MetricRegistry, MetricRegistryEntry, PositionDescriptor } from './api/types'

/**
 * The targets the rule editor accepts for a fix.
 *
 * This list validates what an author types, so it has to hold whether or not
 * the server describes position, which is why it is named here. It is not help
 * text: everything the reference says about a fix comes from the descriptor
 * below, so there is no second copy of the meanings to drift.
 */
export const POSITION_TARGETS: readonly string[] = [
  'position.latitude',
  'position.longitude',
  'position.altitude',
  'position.speed',
  'position.heading',
  'position.accuracy',
]

/**
 * The canonical metric keys, fetched once and shared by every surface that
 * offers them. Two editors on two pages ask for the same list, and the list
 * only changes when the server is redeployed.
 */
const entries = ref<MetricRegistryEntry[]>([])
const position = ref<PositionDescriptor | null>(null)
const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
let inFlight: Promise<void> | null = null

export const metricKeys = readonly(entries)
/** Null on a server that does not describe position, which shows nothing. */
export const positionDescriptor = readonly(position)
export const metricKeyStatus = readonly(status)

export async function loadMetricKeys(force = false): Promise<void> {
  if (!force && (status.value === 'ready' || status.value === 'loading')) {
    await inFlight
    return
  }
  status.value = 'loading'
  inFlight = api<MetricRegistry>('/metrics/registry')
    .then((payload) => {
      // A server that predates the endpoint can answer this path with something
      // else entirely, so the list is only adopted once it looks like one.
      if (!Array.isArray(payload?.metrics)) throw new Error('unexpected registry payload')
      entries.value = payload.metrics
      // Absent on a server that predates the descriptor. The reference omits the
      // entry in that case rather than falling back to a copy of its own.
      const fix = payload.position
      position.value = fix && typeof fix.meaning === 'string' && Array.isArray(fix.fields) ? fix : null
      status.value = 'ready'
    })
    .catch(() => {
      // The endpoint can be absent on a server that has not been redeployed
      // yet, and an author is no worse off than before the reference existed,
      // so this reports rather than throws.
      entries.value = []
      position.value = null
      status.value = 'error'
    })
    .finally(() => {
      inFlight = null
    })
  await inFlight
}

/** Only for tests, which need each case to start from an unfetched registry. */
export function resetMetricKeys(): void {
  entries.value = []
  position.value = null
  status.value = 'idle'
  inFlight = null
}
