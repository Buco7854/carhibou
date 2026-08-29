import type { Vehicle } from './types'

export type LiveConnectionStatus = 'connecting' | 'open' | 'reconnecting'

/**
 * The envelope version is the stream's own, not the telemetry protocol's.
 *
 * The payload is `Vehicle`, so the normalized reading shape reaches this file
 * through that type and nothing here restates it. A protocol v2 server does not
 * by itself imply a v2 envelope, and an envelope this does not recognise is
 * dropped in silence, so the number is only safe to change alongside the server.
 */
interface VehicleStatesEnvelope {
  type: 'vehicle.states'
  version: 1
  occurred_at: string
  vehicles: Vehicle[]
}

interface LiveEventHandlers {
  onStatus: (status: LiveConnectionStatus) => void
  onVehicleStates: (vehicles: Vehicle[]) => void
  onSessionExpired: () => void
}

export function openLiveEventStream(handlers: LiveEventHandlers): EventSource {
  handlers.onStatus('connecting')
  const source = new EventSource('/api/v1/events/stream', { withCredentials: true })
  source.onopen = () => handlers.onStatus('open')
  source.onerror = () => handlers.onStatus('reconnecting')
  source.addEventListener('vehicle.states', (event) => {
    const envelope = JSON.parse((event as MessageEvent<string>).data) as VehicleStatesEnvelope
    if (envelope.type === 'vehicle.states' && envelope.version === 1 && Array.isArray(envelope.vehicles)) {
      handlers.onVehicleStates(envelope.vehicles)
    }
  })
  source.addEventListener('session.expired', () => {
    source.close()
    handlers.onSessionExpired()
  })
  return source
}
