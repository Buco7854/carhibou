<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { chargingState, energySummary, isPercentage, metricLabel } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const state = computed(() => chargingState(vehicle.value))
const level = computed(() => {
  const energy = energySummary(vehicle.value)
  return isPercentage(energy) ? energy : null
})
</script>

<template>
  <article class="widget-card charging-widget">
    <div class="widget-head"><h2>{{ widget.title || t('metrics.charging') }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="state.active !== null">
      <div class="charging-state">
        <strong :class="{ 'is-charging':state.active }">{{ state.active ? t('vehicles.charging') : t('vehicles.notCharging') }}</strong>
        <span v-if="state.active && state.power !== null" class="rate">{{ state.power.toFixed(1) }}<em>kW</em></span>
      </div>
      <i v-if="level" class="level"><b :class="{ 'is-charging':state.active }" :style="{ width:`${level.progress}%` }" /></i>
      <small v-if="level" class="level-note">{{ metricLabel(level, t) }} · {{ Math.round(Number(level.value)) }}%</small>
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
.level{height:3px;display:block;margin-top:10px;overflow:hidden;background:var(--panel-2);border-radius:2px}
.level b{display:block;height:100%;background:var(--muted);border-radius:2px}
.level b.is-charging{background:var(--success)}
.level-note{margin-top:6px;color:var(--muted);font-size:12px}
</style>
