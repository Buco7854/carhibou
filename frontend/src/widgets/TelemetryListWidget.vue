<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatFixedNumber, formatNumber } from '../numberFormat'
import { formatAge, formatMetricNumber, isStale, metricLabel, metricNumber, metricReading, observedAt, secondaryReadings, type MetricReading } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
/**
 * The chosen metrics, or the ones worth showing when nobody has chosen yet.
 *
 * A card configured with metrics shows exactly those, in that order, and stays
 * silent about the rest. One saved before the card was configurable keeps the
 * old behaviour rather than emptying itself.
 */
const readings = computed(() => {
  const chosen = props.widget.metrics ?? []
  const rows = chosen.length
    ? chosen.map((key) => metricReading(vehicle.value, key))
    : secondaryReadings(vehicle.value)
  return rows.filter((reading) => reading.value !== null)
})
const speed = computed(() => (props.widget.metrics ?? []).length ? null : metricNumber(vehicle.value, 'vehicle.speed'))
const signal = computed(() => {
  if ((props.widget.metrics ?? []).length) return null
  const value = vehicle.value?.state?.agent.mobile_signal
  return typeof value === 'number' ? value : null
})
const hasTelemetry = computed(() => speed.value !== null || readings.value.length > 0 || signal.value !== null)

function value(reading: MetricReading): string {
  if (reading.value === null) return '—'
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value, reading, locale.value)
}
</script>

<template>
  <article class="widget-card telemetry-widget">
    <div class="widget-head"><h2>{{ widget.title || t('dashboard.telemetry') }}</h2><small>{{ vehicle?.name }}</small></div>
    <dl v-if="hasTelemetry">
      <div v-if="speed!==null"><dt>{{ t('metrics.vehicleSpeed') }}</dt><dd>{{ formatFixedNumber(speed, locale, 0) }}<small>km/h</small></dd></div>
      <div v-for="reading in readings" :key="reading.key"><dt>{{ metricLabel(reading,t) }}<small v-if="isStale(reading)" class="stale-age">{{ formatAge(observedAt(reading), locale) }}</small></dt><dd :class="{ 'is-stale': isStale(reading) }">{{ value(reading) }}<small v-if="reading.value!==null&&reading.kind==='number'&&reading.unit">{{ reading.unit }}</small></dd></div>
      <div v-if="signal!==null"><dt>{{ t('dashboard.signal') }}</dt><dd>{{ formatNumber(signal, locale) }}<small>dBm</small></dd></div>
    </dl>
    <DashboardWidgetEmpty v-else icon="signal" />
  </article>
</template>

<style scoped>
.telemetry-widget{padding:0}
.telemetry-widget .widget-head{margin:0;padding:12px 14px 10px;border-bottom:1px solid var(--line)}
.telemetry-widget dl{min-height:0;margin:0;overflow:auto}
.telemetry-widget .dashboard-widget-empty{padding:12px 14px}
.telemetry-widget dl>div{min-height:38px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:6px 14px;border-bottom:1px solid var(--line)}
.telemetry-widget dl>div:last-child{border-bottom:0}
.telemetry-widget dt{overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.telemetry-widget dd{display:flex;align-items:baseline;gap:3px;margin:0;font-size:var(--font-value-xs);font-weight:500;font-variant-numeric:tabular-nums}
.telemetry-widget dd small{color:var(--muted);font-size:var(--font-caption);font-weight:400}
.telemetry-widget dd.is-stale{color:var(--muted)}
.telemetry-widget .stale-age{display:block;margin-top:1px;color:var(--muted-2);font-size:var(--font-micro)}
</style>
