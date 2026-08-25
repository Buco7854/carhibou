<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, Vehicle } from '../api/types'
import AppSelect from '../components/AppSelect.vue'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardRuntime } from './dashboardContext'

defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const runtime = useDashboardRuntime()
const selected = computed(() => runtime.vehicles.value.find(
  (vehicle) => vehicle.id === runtime.selectedVehicleId.value,
))

function vehicleDetails(vehicle: Vehicle): string {
  return [vehicle.manufacturer, vehicle.model].filter(Boolean).join(' · ')
}
</script>

<template>
  <article class="widget-card vehicle-selector-widget">
    <template v-if="runtime.vehicles.value.length">
      <span class="selector-label">{{ widget.title || t('dashboards.vehicleSelector') }}</span>
      <AppSelect
        class="vehicle-select"
        searchable
        :model-value="runtime.selectedVehicleId.value"
        :aria-label="t('dashboard.chooseVehicle')"
        :search-placeholder="t('vehicles.search')"
        :no-results-text="t('vehicles.noMatch')"
        @update:model-value="runtime.selectVehicle(String($event))"
      >
        <option v-for="vehicle in runtime.vehicles.value" :key="vehicle.id" :value="vehicle.id">
          {{ vehicle.name }}{{ vehicleDetails(vehicle) ? ` · ${vehicleDetails(vehicle)}` : '' }}
        </option>
      </AppSelect>
      <span v-if="selected" :class="['status',{online:selected.state?.online}]">{{ selected.state?.online ? t('common.online') : t('common.parked') }}</span>
    </template>
    <DashboardWidgetEmpty v-else icon="vehicle" :message="t('vehicles.noVehicles')" />
  </article>
</template>

<style scoped>
.vehicle-selector-widget{flex-direction:row;align-items:center;gap:12px;padding:8px 14px}
.selector-label{flex:none;color:var(--muted);font-size:12px}
.vehicle-select{width:min(100%,460px);flex:1}
.vehicle-select :deep(.app-select-trigger){min-height:32px;padding-block:5px}
.vehicle-selector-widget>.status{flex:none;margin-left:auto}
@media(max-width:700px){.vehicle-selector-widget{gap:9px;padding-inline:10px}.selector-label{display:none}}
</style>
