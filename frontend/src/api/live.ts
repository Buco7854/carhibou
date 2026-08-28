import { onScopeDispose, readonly, ref, watch, type Ref } from 'vue'
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

/**
 * The shortest gap between two refetches driven by the stream.
 *
 * A vehicle uploading continuously produces a state event about once a second,
 * and every page reacting to each one would refetch far more often than anybody
 * can read. This is the floor: bursts collapse into one trailing refetch.
 */
const REFRESH_INTERVAL_MS = 5000

/**
 * Run `refresh` when the data behind a page has probably changed.
 *
 * The stream carries one event, a vehicle snapshot, and it changes whenever new
 * telemetry lands, so it doubles as the "there is new data" signal for anything
 * derived from telemetry. Records the stream says nothing about (agents,
 * connectors) pass `pollMs` and get a slow poll on the same throttle.
 *
 * A hidden tab refetches nothing and remembers that it owes one, so returning to
 * it brings the page up to date at once rather than after the next event.
 */
export function useLiveRefresh(refresh: () => unknown, options: { pollMs?: number } = {}): void {
  const { vehicles } = useLiveVehicles()
  let lastRun = 0
  let timer: ReturnType<typeof setTimeout> | undefined
  let owed = false

  function run(): void {
    lastRun = Date.now()
    owed = false
    void refresh()
  }

  function schedule(): void {
    if (typeof document !== 'undefined' && document.hidden) {
      owed = true
      return
    }
    if (timer !== undefined) return
    const wait = REFRESH_INTERVAL_MS - (Date.now() - lastRun)
    if (wait <= 0) {
      run()
      return
    }
    owed = true
    timer = setTimeout(() => {
      timer = undefined
      if (typeof document === 'undefined' || !document.hidden) run()
    }, wait)
  }

  watch(vehicles, schedule)

  const poll = options.pollMs === undefined ? undefined : setInterval(schedule, options.pollMs)
  function onVisibility(): void {
    if (!document.hidden && owed) schedule()
  }
  document.addEventListener('visibilitychange', onVisibility)

  onScopeDispose(() => {
    document.removeEventListener('visibilitychange', onVisibility)
    if (timer !== undefined) clearTimeout(timer)
    if (poll !== undefined) clearInterval(poll)
  })
}
