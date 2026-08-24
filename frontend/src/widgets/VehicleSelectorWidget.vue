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
      <div class="selector-heading">
        <span class="eyebrow">{{ widget.title || t('dashboards.vehicleSelector') }}</span>
        <small>{{ t('dashboards.vehicleSelectorHint') }}</small>
      </div>
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
      <div v-if="selected" class="selector-state">
        <i :class="{ online:selected.state?.online }" />
        <span><strong>{{ selected.name }}</strong><small>{{ selected.state?.online ? t('common.online') : t('common.parked') }}</small></span>
      </div>
    </template>
    <DashboardWidgetEmpty v-else icon="vehicle" :message="t('vehicles.noVehicles')" />
  </article>
</template>

<style scoped>
.vehicle-selector-widget{flex-direction:row;align-items:center;gap:14px;padding:9px 14px}.selector-heading{min-width:145px;display:grid;gap:2px}.selector-heading .eyebrow{margin:0}.selector-heading small{color:var(--muted);font-size:8px}.vehicle-select{width:min(100%,520px);flex:1}.vehicle-select :deep(.app-select-trigger){min-height:39px;background:var(--panel-2)}.selector-state{min-width:145px;display:grid;grid-template-columns:8px minmax(0,1fr);align-items:center;gap:9px;margin-left:auto}.selector-state i{width:8px;height:8px;grid-row:1/3;background:var(--muted-2);border-radius:50%}.selector-state i.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}.selector-state span,.selector-state strong,.selector-state small{min-width:0;display:block}.selector-state strong,.selector-state small{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.selector-state strong{font-size:10px}.selector-state small{margin-top:2px;color:var(--muted);font-size:8px}@media(max-width:700px){.vehicle-selector-widget{gap:9px;padding-inline:10px}.selector-heading{min-width:90px}.selector-heading small,.selector-state{display:none}}
</style>
