import { onScopeDispose, readonly, ref, type Ref } from 'vue'
import { openLiveEventStream, type LiveConnectionStatus } from './events'
import type { Vehicle } from './types'

/**
 * One live stream, shared by every page that shows vehicle state.
 *
 * The stream already existed and only the dashboard listened to it, so every other
 * page showed whatever was true when it was opened until somebody reloaded. A
 * browser also caps how many of these it will hold open per origin, which is the
 * reason this is one connection with several subscribers rather than one each.
 */
const vehicles = ref<Vehicle[]>([])
const status = ref<LiveConnectionStatus>('connecting')
let source: EventSource | undefined
let subscribers = 0

function open(): void {
  if (source) return
  source = openLiveEventStream({
    onStatus: (next) => { status.value = next },
    onVehicleStates: (next) => { vehicles.value = next },
    onSessionExpired: () => window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`),
  })
}

function close(): void {
  source?.close()
  source = undefined
  status.value = 'connecting'
}

export interface LiveVehicles {
  vehicles: Readonly<Ref<Vehicle[]>>
  status: Readonly<Ref<LiveConnectionStatus>>
}

/**
 * Subscribe for the lifetime of the calling component.
 *
 * The connection opens for the first subscriber and closes after the last leaves,
 * so a page that nobody is looking at is not holding one.
 */
export function useLiveVehicles(): LiveVehicles {
  subscribers += 1
  open()
  onScopeDispose(() => {
    subscribers -= 1
    if (subscribers <= 0) {
      subscribers = 0
      close()
    }
  })
  return { vehicles: readonly(vehicles) as Readonly<Ref<Vehicle[]>>, status: readonly(status) as Readonly<Ref<LiveConnectionStatus>> }
}
