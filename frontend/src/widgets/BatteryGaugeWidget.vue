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
    <div class="widget-head"><h2>{{ widget.title || metricLabel(energy,t) }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="energy.value!==null">
      <div class="gauge"><strong class="energy-value">{{ Math.round(energy.value) }}</strong><em>{{ energy.unit }}</em><small v-if="typeof charging==='boolean'">{{ t('metrics.charging') }} · {{ t(charging ? 'metrics.active' : 'metrics.inactive') }}</small></div>
      <i class="energy-track"><b :style="{ width:`${energy.progress}%` }" /></i>
    </template>
    <DashboardWidgetEmpty v-else :icon="energy.icon" />
  </article>
</template>

<style scoped>
.gauge{min-height:0;display:flex;align-items:baseline;flex:1;padding-bottom:10px}
.gauge strong{font-size:clamp(30px,3.4vw,44px);font-weight:500;letter-spacing:-.03em;line-height:1;font-variant-numeric:tabular-nums}
.gauge em{margin-left:4px;color:var(--muted);font-size:13px;font-style:normal}
.gauge small{margin-left:auto;color:var(--muted);font-size:12px}
.energy-track{height:3px;display:block;overflow:hidden;background:var(--panel-2);border-radius:2px}
.energy-track b{display:block;height:100%;background:var(--muted);border-radius:2px}
</style>
