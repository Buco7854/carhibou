<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { History, Position, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppSelect from '../components/AppSelect.vue'
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
const vehicleDetails = computed(() => [vehicle.value?.manufacturer, vehicle.value?.model, vehicle.value?.year].filter(Boolean).join(' · '))
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
  <div class="page history-page">
    <header class="page-header"><div><span class="eyebrow">{{ t('history.eyebrow') }}</span><h1>{{ vehicle?.name }} · {{ t('history.title') }}</h1><p>{{ t('history.pageHint') }}</p></div><RouterLink class="button secondary no-underline" to="/"><AppIcon name="arrow-left" :size="15" />{{ t('nav.dashboards') }}</RouterLink></header>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="history-overview">
      <section class="panel history-context">
        <div class="history-identity"><span class="history-icon"><AppIcon name="vehicle" /></span><div><strong>{{ vehicle?.name }}</strong><small v-if="vehicleDetails">{{ vehicleDetails }}</small></div><span :class="['status',{online:vehicle?.state?.online}]">{{ vehicle?.state?.online?t('common.online'):t('common.stale') }}</span></div>
        <div class="history-stats">
          <div class="history-stat"><span>{{ t('history.latest') }}</span><strong>{{ latestDisplay }}<small v-if="latestValue !== undefined && selectedMetric.unit">{{ selectedMetric.unit }}</small></strong><em>{{ metricLabel(selectedMetric, t) }}</em></div>
          <div v-if="history" class="history-stat"><span>{{ t('history.sourceSamples') }}</span><strong>{{ history.original_count }}</strong><em>{{ t('history.selectedRange') }}</em></div>
        </div>
      </section>
      <section class="panel history-controls">
        <header><div><span class="eyebrow">{{ t('history.filters') }}</span><h2>{{ t('history.chooseData') }}</h2></div><p>{{ t('history.filtersHint') }}</p></header>
        <div class="history-filters">
          <label class="field"><span>{{ t('history.metric') }}</span><AppSelect v-model="metric"><option v-for="definition in metricOptions" :key="definition.key" :value="definition.key">{{ metricLabel(definition, t) }} · {{ definition.key }}</option></AppSelect></label>
          <label class="field"><span>{{ t('history.range') }}</span><AppSelect v-model="days"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></AppSelect></label>
        </div>
      </section>
    </div>
    <div v-if="history?.points.length" class="history-grid">
      <section class="panel history-chart"><header><div><span class="eyebrow">{{ metric }}</span><h2>{{ metricLabel(selectedMetric, t) }}</h2></div><span class="metric-chip">{{ days === 1 ? t('history.day') : days === 7 ? t('history.week') : t('history.month') }}</span></header><div class="chart-stage"><TimeSeriesChart :series="series" :height="390" /></div></section>
      <section class="panel route-panel"><header><div><span class="eyebrow">{{ t('history.route') }}</span><h2>{{ vehicle?.name }}</h2></div><span class="route-count"><AppIcon name="location" :size="14" />{{ routePoints.length }}</span></header><div class="route-map"><VehicleMap :position="lastPosition" :route="routePoints" /></div></section>
    </div>
    <div v-else class="panel empty">{{ t('history.noData') }}</div>
  </div>
</template>

<style scoped>
.history-overview{display:grid;grid-template-columns:minmax(300px,.72fr) minmax(440px,1.28fr);gap:14px;margin-bottom:14px}.history-context,.history-controls{min-width:0;padding:18px}.history-context{display:grid;gap:18px}.history-identity{min-width:0;display:grid;grid-template-columns:42px minmax(0,1fr) auto;align-items:center;gap:11px;padding-bottom:17px;border-bottom:1px solid var(--line)}.history-icon{width:41px;height:41px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:10px}.history-identity strong,.history-identity small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.history-identity strong{font-size:13px}.history-identity small{margin-top:4px;color:var(--muted);font-size:9px}.history-stats{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.history-stat{min-width:0;padding:12px;background:var(--panel-2);border-radius:9px}.history-stat span,.history-stat strong,.history-stat em{display:block}.history-stat span{color:var(--muted);font-size:8px;text-transform:uppercase;letter-spacing:.05em}.history-stat strong{margin-top:7px;font-size:20px;font-weight:500}.history-stat strong small{margin-left:3px;color:var(--muted);font-size:9px;font-weight:400}.history-stat em{margin-top:4px;overflow:hidden;color:var(--muted);font-size:8px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.history-controls{display:flex;flex-direction:column;justify-content:space-between;gap:18px}.history-controls>header{display:flex;align-items:flex-start;justify-content:space-between;gap:22px}.history-controls h2{margin:0;font-size:16px}.history-controls header p{max-width:320px;margin:0;color:var(--muted);font-size:9px;line-height:1.5;text-align:right}.history-filters{min-width:0;display:grid;grid-template-columns:minmax(240px,1fr) minmax(150px,.42fr);gap:13px}.history-grid{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(380px,.9fr);gap:14px}.route-panel,.history-chart{min-width:0;overflow:hidden}.route-panel header,.history-chart header{height:64px;display:flex;align-items:center;justify-content:space-between;padding:11px 16px;border-bottom:1px solid var(--line)}.route-panel h2,.history-chart h2{margin:0;font-size:14px}.route-count,.metric-chip{display:flex;align-items:center;gap:5px;padding:6px 8px;color:var(--muted);background:var(--panel-2);border-radius:8px;font-size:8px}.route-count .app-icon{color:var(--accent)}.route-map{height:420px}.chart-stage{padding:0 10px 10px}
@media(max-width:1150px){.history-overview{grid-template-columns:1fr}.history-context{grid-template-columns:minmax(260px,.8fr) 1.2fr;align-items:center}.history-identity{padding:0 18px 0 0;border-right:1px solid var(--line);border-bottom:0}.history-grid{grid-template-columns:1fr}.route-map{height:390px}}
@media(max-width:720px){.history-context{grid-template-columns:1fr}.history-identity{padding:0 0 16px;border-right:0;border-bottom:1px solid var(--line)}.history-controls>header{display:block}.history-controls header p{margin-top:7px;text-align:left}.history-filters{grid-template-columns:1fr}.history-grid{grid-template-columns:1fr}.route-map{height:340px}}
@media(max-width:480px){.history-stats{grid-template-columns:1fr}.history-stat:nth-child(2){display:none}.history-context,.history-controls{padding:15px}}
</style>
