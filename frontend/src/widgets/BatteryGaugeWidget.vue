<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { energySummary, metricLabel } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const energy = computed(() => energySummary(vehicle.value))
const charging = computed(() => vehicle.value?.state?.metrics['charging.active'])
</script>

<template>
  <article class="widget-card energy-widget">
    <header><span class="eyebrow">{{ widget.title || metricLabel(energy,t) }}</span><small>{{ vehicle?.name }}</small></header>
    <template v-if="energy.value!==null">
      <div class="gauge"><strong class="energy-value">{{ Math.round(energy.value) }}</strong><em>{{ energy.unit }}</em><small v-if="typeof charging==='boolean'">{{ t('metrics.charging') }} · {{ t(charging ? 'metrics.active' : 'metrics.inactive') }}</small></div>
      <i class="energy-track"><b :style="{ width:`${energy.progress}%` }" /></i>
    </template>
    <DashboardWidgetEmpty v-else :icon="energy.icon" />
  </article>
</template>

<style scoped>
.energy-widget{padding:15px 17px}.energy-widget header{display:flex;align-items:center;justify-content:space-between;gap:12px}.energy-widget header .eyebrow{margin:0}.energy-widget header small{overflow:hidden;color:var(--muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.gauge{min-height:0;display:flex;align-items:end;flex:1}.gauge strong{font-size:clamp(37px,4vw,53px);font-weight:500;letter-spacing:-.075em;line-height:.86}.gauge em{margin:0 0 4px 5px;color:var(--accent);font-size:14px;font-style:normal}.gauge small{margin:0 0 5px auto;color:var(--muted);font-size:8px}.energy-track{height:6px;display:block;overflow:hidden;background:var(--panel-2);border-radius:4px}.energy-track b{display:block;height:100%;background:var(--accent)}
</style>
