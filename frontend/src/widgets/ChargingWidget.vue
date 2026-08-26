<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { chargingState } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const state = computed(() => chargingState(vehicle.value))
</script>

<template>
  <article class="widget-card charging-widget">
    <div class="widget-head"><h2>{{ widget.title || t('metrics.charging') }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="state.active !== null">
      <div class="charging-state">
        <strong :class="{ 'is-charging':state.active }">{{ state.active ? t('vehicles.charging') : t('vehicles.notCharging') }}</strong>
        <span v-if="state.active && state.power !== null" class="rate">{{ state.power.toFixed(1) }}<em>kW</em></span>
      </div>
      <!-- The charge level belongs to the energy card, which says it larger and
           says it once. Repeating it here made a card about the charge into a
           second, quieter card about the level. -->
    </template>
    <DashboardWidgetEmpty v-else icon="charging" />
  </article>
</template>

<style scoped>
.charging-state{display:flex;align-items:baseline;justify-content:space-between;gap:12px;margin-top:auto}
.charging-state strong{font-size:17px;font-weight:500}
.charging-state strong.is-charging{color:var(--success)}
.rate{font-size:24px;font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.rate em{margin-left:3px;color:var(--muted);font-size:12px;font-style:normal;font-weight:400}
</style>
