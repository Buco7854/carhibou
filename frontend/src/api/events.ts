import type { Vehicle } from './types'

export type LiveConnectionStatus = 'connecting' | 'open' | 'reconnecting'

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
