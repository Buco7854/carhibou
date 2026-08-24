<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatMetricNumber, metricLabel, metricNumber, secondaryReadings, type MetricReading } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const speed = computed(() => metricNumber(vehicle.value, 'vehicle.speed'))
const readings = computed(() => secondaryReadings(vehicle.value).filter((reading) => reading.value !== null))
const signal = computed(() => {
  const value = vehicle.value?.state?.device.mobile_signal
  return typeof value === 'number' ? value : null
})
const hasTelemetry = computed(() => speed.value !== null || readings.value.length > 0 || signal.value !== null)

function value(reading: MetricReading): string {
  if (reading.value === null) return '—'
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value, reading)
}
</script>

<template>
  <article class="widget-card telemetry-widget">
    <header><span class="eyebrow">{{ widget.title || t('dashboard.telemetry') }}</span><small>{{ vehicle?.name }}</small></header>
    <dl v-if="hasTelemetry">
      <div v-if="speed!==null"><dt><AppIcon name="speed" :size="15" />{{ t('metrics.vehicleSpeed') }}</dt><dd>{{ Math.round(speed) }}<small>km/h</small></dd></div>
      <div v-for="reading in readings" :key="reading.key"><dt><AppIcon :name="reading.icon" :size="15" />{{ metricLabel(reading,t) }}</dt><dd>{{ value(reading) }}<small v-if="reading.value!==null&&reading.kind==='number'&&reading.unit">{{ reading.unit }}</small></dd></div>
      <div v-if="signal!==null"><dt><AppIcon name="signal" :size="15" />{{ t('dashboard.signal') }}</dt><dd>{{ signal }}<small>dBm</small></dd></div>
    </dl>
    <DashboardWidgetEmpty v-else icon="signal" />
  </article>
</template>

<style scoped>
.telemetry-widget{padding:0}.telemetry-widget header{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px 8px;border-bottom:1px solid var(--line)}.telemetry-widget header .eyebrow{margin:0}.telemetry-widget header small{overflow:hidden;color:var(--muted);font-size:8px;text-overflow:ellipsis;white-space:nowrap}.telemetry-widget dl{min-height:0;margin:0;overflow:hidden}.telemetry-widget dl>div{min-height:42px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:7px 14px;border-bottom:1px solid var(--line)}.telemetry-widget dl>div:last-child{border-bottom:0}.telemetry-widget dt{display:flex;align-items:center;gap:7px;color:var(--muted);font-size:9px}.telemetry-widget dt .app-icon{flex:none;color:var(--accent)}.telemetry-widget dd{display:flex;align-items:baseline;gap:4px;margin:0;font-size:14px;font-weight:500}.telemetry-widget dd small{color:var(--muted);font-size:8px;font-weight:400}
</style>
