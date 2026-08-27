import { computed, inject, type ComputedRef, type InjectionKey, type Ref } from 'vue'
import type { DashboardWidget, Vehicle } from '../api/types'
import type { LiveConnectionStatus } from '../api/events'

export interface DashboardRuntime {
  vehicles: Ref<Vehicle[]>
  selectedVehicleId: Ref<string>
  liveStatus: Ref<LiveConnectionStatus>
  selectVehicle: (id: string) => void
}

export const dashboardRuntimeKey: InjectionKey<DashboardRuntime> = Symbol('dashboard-runtime')

export function useDashboardRuntime(): DashboardRuntime {
  const runtime = inject(dashboardRuntimeKey)
  if (!runtime) throw new Error('dashboard widget must be rendered inside DashboardsView')
  return runtime
}

export function useDashboardVehicle(widget: DashboardWidget): ComputedRef<Vehicle | null> {
  const runtime = useDashboardRuntime()
  return computed(() => {
    const id = widget.vehicle_id || runtime.selectedVehicleId.value
    return runtime.vehicles.value.find((vehicle) => vehicle.id === id) ?? null
  })
}
