<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { History, Position, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMap from '../components/VehicleMap.vue'
import { formatMetricNumber, metricDefinition, metricLabel, preferredHistoryMetric } from '../vehicleDisplay'

const { t } = useI18n()
const route = useRoute()
const vehicle = ref<Vehicle | null>(null)
const history = ref<History | null>(null)
const metric = ref('')
const days = ref(1)
const error = ref('')
const vehicleId = String(route.params.id)
const routePoints = computed<Array<[number, number]>>(() => (history.value?.points ?? []).flatMap((point) => point.latitude !== null && point.longitude !== null ? [[point.latitude, point.longitude]] : []))
const lastPosition = computed<Position | null>(() => {
  const point = [...(history.value?.points ?? [])].reverse().find((row) => row.latitude !== null && row.longitude !== null)
  return point ? { latitude: point.latitude!, longitude: point.longitude!, altitude: null, speed: point.speed, heading: point.heading, accuracy: null } : null
})
const metricOptions = computed(() => {
  const options = new Set(history.value?.available_metrics ?? [])
  if ((history.value?.points ?? []).some((point) => typeof point.speed === 'number')) options.add('vehicle.speed')
  return [...options].sort().map((key) => metricDefinition(key))
})
const selectedMetric = computed(() => metricDefinition(metric.value))
const series = computed(() => [{
  name: metricLabel(selectedMetric.value, t),
  unit: selectedMetric.value.unit,
  data: (history.value?.points ?? []).flatMap((point) => {
    const value = metric.value === 'vehicle.speed' ? point.speed : point.metrics[metric.value]
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])
const latestValue = computed(() => [...(series.value[0]?.data ?? [])].at(-1)?.[1])
const latestDisplay = computed(() => latestValue.value === undefined ? '—' : formatMetricNumber(latestValue.value, selectedMetric.value))

async function load() {
  error.value = ''
  const end = new Date()
  const start = new Date(end.getTime() - days.value * 86_400_000)
  try {
    ;[vehicle.value, history.value] = await Promise.all([
      api<Vehicle>(`/vehicles/${vehicleId}`),
      api<History>(`/vehicles/${vehicleId}/history?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&max_points=1500`),
    ])
    const options = metricOptions.value.map((definition) => definition.key)
    if (!options.includes(metric.value)) {
      metric.value = preferredHistoryMetric(vehicle.value, history.value.available_metrics, options.includes('vehicle.speed'))
    }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
watch(days, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('history.eyebrow') }}</span><h1>{{ vehicle?.name }} · {{ t('history.title') }}</h1></div><RouterLink class="button secondary no-underline" to="/">← {{ t('nav.dashboard') }}</RouterLink></header>
    <p v-if="error" class="error">{{ error }}</p>
    <section class="panel history-toolbar">
      <div class="history-identity"><span class="history-icon"><AppIcon name="vehicle" /></span><div><strong>{{ vehicle?.name }}</strong><small>{{ vehicle?.manufacturer }} {{ vehicle?.model }}</small></div><span :class="['status',{online:vehicle?.state?.online}]">{{ vehicle?.state?.online?t('common.online'):t('common.stale') }}</span></div>
      <label class="field"><span>{{ t('history.metric') }}</span><select v-model="metric" class="select"><option v-for="definition in metricOptions" :key="definition.key" :value="definition.key">{{ metricLabel(definition, t) }} · {{ definition.key }}</option></select></label>
      <label class="field range-field"><span>{{ t('history.range') }}</span><select v-model="days" class="select"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></select></label>
      <div class="history-stat"><span>{{ metricLabel(selectedMetric, t) }}</span><strong>{{ latestDisplay }}<small v-if="latestValue !== undefined && selectedMetric.unit">{{ selectedMetric.unit }}</small></strong></div>
      <div v-if="history" class="history-stat"><span>{{ t('history.samples', { count: history.original_count }) }}</span><strong>{{ history.original_count }}</strong></div>
    </section>
    <div v-if="history?.points.length" class="history-grid">
      <section class="panel route-panel"><header><div><span class="eyebrow">{{ t('history.route') }}</span><h2>{{ vehicle?.name }}</h2></div><span class="route-count"><AppIcon name="location" :size="14" />{{ routePoints.length }}</span></header><div class="route-map"><VehicleMap :position="lastPosition" :route="routePoints" /></div></section>
      <section class="panel history-chart"><header><div><span class="eyebrow">{{ metric }}</span><h2>{{ metricLabel(selectedMetric, t) }}</h2></div><span class="metric-chip">{{ days === 1 ? t('history.day') : days === 7 ? t('history.week') : t('history.month') }}</span></header><TimeSeriesChart :series="series" :height="390" /></section>
    </div>
    <div v-else class="panel empty">{{ t('history.noData') }}</div>
  </div>
</template>

<style scoped>
.history-toolbar{display:grid;grid-template-columns:minmax(190px,1fr) minmax(190px,260px) 145px 125px 125px;gap:11px;align-items:end;margin-bottom:13px;padding:13px}.history-identity{align-self:stretch;display:grid;grid-template-columns:36px 1fr auto;align-items:center;gap:9px;padding-right:11px;border-right:1px solid var(--line)}.history-icon{width:35px;height:35px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:9px}.history-identity strong,.history-identity small{display:block}.history-identity strong{font-size:10px}.history-identity small{margin-top:3px;color:var(--muted);font-size:8px}.history-stat{align-self:stretch;padding:8px 9px;background:var(--panel-2);border:1px solid var(--line);border-radius:9px}.history-stat span,.history-stat strong{display:block}.history-stat span{overflow:hidden;color:var(--muted);font-size:7px;text-overflow:ellipsis;white-space:nowrap}.history-stat strong{margin-top:5px;font-size:15px;font-weight:500}.history-stat strong small{margin-left:3px;color:var(--muted);font-size:8px;font-weight:400}.history-grid{display:grid;grid-template-columns:minmax(0,1.35fr) minmax(360px,.65fr);gap:13px}.route-panel,.history-chart{overflow:hidden}.route-panel header,.history-chart header{height:62px;display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-bottom:1px solid var(--line)}.route-panel h2,.history-chart h2{margin:0;font-size:14px}.route-count,.metric-chip{display:flex;align-items:center;gap:5px;padding:6px 8px;color:var(--muted);background:var(--panel-2);border-radius:8px;font-size:7px}.route-count .app-icon{color:var(--accent)}.route-map{height:420px}.history-chart{padding-bottom:9px}.history-chart>div{padding:0 9px}
@media(max-width:1250px){.history-toolbar{grid-template-columns:1fr 1fr 140px}.history-identity{grid-column:1/-1;border:0;border-bottom:1px solid var(--line);padding:0 0 12px}.history-grid{grid-template-columns:1fr}.route-map{height:400px}}
@media(max-width:620px){.history-toolbar{grid-template-columns:1fr 1fr}.history-identity{grid-column:1/-1}.history-toolbar>.field{grid-column:span 1}.history-stat{display:none}.route-map{height:330px}}
</style>
