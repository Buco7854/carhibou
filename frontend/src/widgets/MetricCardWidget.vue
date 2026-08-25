<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatMetricNumber, metricLabel, metricReading } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
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
      <div class="metric-value">{{ value }}<span v-if="reading.kind==='number'&&unit" class="metric-unit">{{ unit }}</span></div>
      <small class="metric-owner">{{ vehicle?.name }}</small>
    </template>
    <DashboardWidgetEmpty v-else :icon="reading.icon" />
  </article>
</template>

<style scoped>
.metric-widget .metric-value{margin-top:auto}
.metric-owner{margin-top:4px;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
</style>
