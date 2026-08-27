<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api, errorMessage } from '../api/client'
import { loadHistory } from '../api/segments'
import { useLiveVehicles } from '../api/live'
import type { History, Position, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppSelect from '../components/AppSelect.vue'
import TelemetryTable from '../components/TelemetryTable.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMap from '../components/VehicleMap.vue'
import { formatMetricNumber, metricDefinition, metricLabel, preferredHistoryMetric } from '../vehicleDisplay'

const { t } = useI18n()
const route = useRoute()
const vehicle = ref<Vehicle | null>(null)

// The header and the map marker show the vehicle's current state, so they follow
// the stream. The charts and the table below are a stated time range and are left
// alone: a range that reloaded under the reader would move what they are reading.
const live = useLiveVehicles()
watch(live.vehicles, (next) => {
  const current = next.find((item) => item.id === vehicle.value?.id)
  if (current) vehicle.value = current
})
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
      loadHistory(vehicleId, { start, end, maxPoints: 1500 }),
    ])
    const options = metricOptions.value.map((definition) => definition.key)
    if (!options.includes(metric.value)) {
      metric.value = preferredHistoryMetric(vehicle.value, history.value.available_metrics, options.includes('vehicle.speed'))
    }
  } catch (reason) { error.value = errorMessage(reason, t('common.error')) }
}
watch(days, load)
onMounted(load)
</script>

<template>
  <div class="page history-page">
    <header class="page-header">
      <div>
        <h1>{{ vehicle?.name }} · {{ t('history.title') }}</h1>
        <p v-if="vehicleDetails">{{ vehicleDetails }}</p>
      </div>
      <div class="header-actions">
        <RouterLink class="button secondary" to="/vehicles"><AppIcon name="arrow-left" :size="15" />{{ t('nav.vehicles') }}</RouterLink>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <div class="history-controls">
      <label class="field inline-field"><span>{{ t('history.metric') }}</span><AppSelect v-model="metric"><option v-for="definition in metricOptions" :key="definition.key" :value="definition.key">{{ metricLabel(definition, t) }} · {{ definition.key }}</option></AppSelect></label>
      <label class="field inline-field range-field"><span>{{ t('history.range') }}</span><AppSelect v-model="days"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></AppSelect></label>
      <dl class="history-summary">
        <div class="history-stat"><dt>{{ t('history.latest') }}</dt><dd>{{ latestDisplay }}<small v-if="latestValue !== undefined && selectedMetric.unit">{{ selectedMetric.unit }}</small></dd></div>
        <div v-if="history" class="history-stat"><dt>{{ t('history.sourceSamples') }}</dt><dd>{{ history.original_count }}</dd></div>
        <div class="history-stat"><dt>{{ t('common.status') }}</dt><dd><span :class="['status',{online:vehicle?.state?.online}]">{{ vehicle?.state?.online ? t('common.online') : t('common.stale') }}</span></dd></div>
      </dl>
    </div>

    <div v-if="history?.points.length" class="history-grid">
      <section class="panel history-chart">
        <header><h2>{{ metricLabel(selectedMetric, t) }}</h2><span class="mono panel-meta">{{ metric }}</span></header>
        <div class="chart-stage"><TimeSeriesChart :series="series" :height="380" /></div>
      </section>
      <section class="panel route-panel">
        <header><h2>{{ t('history.route') }}</h2><span class="route-count">{{ routePoints.length }}</span></header>
        <div class="route-map"><VehicleMap :position="lastPosition" :route="routePoints" /></div>
      </section>
    </div>
    <div v-else class="panel empty">{{ t('history.noData') }}</div>

    <TelemetryTable class="entries-section" :vehicle-id="vehicleId" :days="days" />
  </div>
</template>

<style scoped>
.history-controls{display:flex;align-items:flex-end;flex-wrap:wrap;gap:14px 20px;margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid var(--line)}
.inline-field{width:min(320px,100%)}
.range-field{width:150px}
.history-summary{display:flex;align-items:flex-start;flex-wrap:wrap;gap:26px;margin:0 0 0 auto}
.history-stat{min-width:0}
.history-stat dt{color:var(--muted);font-size:var(--font-caption)}
.history-stat dd{min-height:25px;margin:2px 0 0;display:flex;align-items:center;gap:3px;font-size:var(--font-value-sm);font-weight:500;letter-spacing:-.02em;font-variant-numeric:tabular-nums}
.history-stat dd small{color:var(--muted);font-size:var(--font-caption);font-weight:400;letter-spacing:0}
.history-stat dd .status{font-size:var(--font-caption);font-weight:400;letter-spacing:0}

.entries-section{margin-top:12px}
.history-grid{display:grid;grid-template-columns:minmax(0,1.15fr) minmax(360px,.85fr);gap:12px}
.route-panel,.history-chart{min-width:0;overflow:hidden}
.route-panel header,.history-chart header{height:46px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:0 14px;border-bottom:1px solid var(--line)}
.route-panel h2,.history-chart h2{margin:0;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em}
.panel-meta,.route-count{color:var(--muted);font-size:var(--font-caption)}
.route-map{height:400px}
.chart-stage{padding:8px 8px 8px 0}

@media(max-width:1100px){.history-grid{grid-template-columns:1fr}.route-map{height:360px}}
@media(max-width:700px){
  .history-controls{align-items:stretch;flex-direction:column;gap:12px}
  .inline-field,.range-field{width:100%}
  .history-summary{margin:0;gap:20px}
  .route-map{height:320px}
}
</style>
