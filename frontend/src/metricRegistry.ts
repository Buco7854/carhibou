import { readonly, ref } from 'vue'
import { api } from './api/client'
import type { MetricRegistry, MetricRegistryEntry } from './api/types'

/**
 * The canonical metric keys, fetched once and shared by every surface that
 * offers them. Two editors on two pages ask for the same list, and the list
 * only changes when the server is redeployed.
 */
const entries = ref<MetricRegistryEntry[]>([])
const status = ref<'idle' | 'loading' | 'ready' | 'error'>('idle')
let inFlight: Promise<void> | null = null

export const metricKeys = readonly(entries)
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
      status.value = 'ready'
    })
    .catch(() => {
      // The endpoint can be absent on a server that has not been redeployed
      // yet, and an author is no worse off than before the reference existed,
      // so this reports rather than throws.
      entries.value = []
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
  status.value = 'idle'
  inFlight = null
}
