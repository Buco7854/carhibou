<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatAge, formatMetricNumber, isStale, metricLabel, metricReading, observedAt } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const reading = computed(() => metricReading(vehicle.value, props.widget.metric ?? ''))
const value = computed(() => {
  if (reading.value.value === null) return ''
  if (typeof reading.value.value === 'boolean') return t(reading.value.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value.value, reading.value)
})
const unit = computed(() => props.widget.unit ?? reading.value.unit)
</script>

<template>
  <article class="widget-card metric-widget">
    <div class="widget-head"><h2>{{ widget.title || metricLabel(reading,t) }}</h2></div>
    <template v-if="reading.value!==null">
      <div class="metric-value" :class="{ 'is-stale': isStale(reading) }">{{ value }}<span v-if="reading.kind==='number'&&unit" class="metric-unit">{{ unit }}</span></div>
      <small class="metric-owner">{{ isStale(reading) ? formatAge(observedAt(reading), locale) : vehicle?.name }}</small>
    </template>
    <DashboardWidgetEmpty v-else :icon="reading.icon" />
  </article>
</template>

<style scoped>
.metric-widget .metric-value{margin-top:auto}
.metric-value.is-stale{color:var(--muted)}
.metric-owner{margin-top:4px;overflow:hidden;color:var(--muted-2);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
</style>
