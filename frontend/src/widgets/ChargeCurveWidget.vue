<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, History, Segments } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, loadHistory, loadSegments } from '../api/segments'
import { followSelection, mergeSegments, metricNumber } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const segments = ref<Segments | null>(null)
const history = ref<History | null>(null)
let segmentRequest = 0
let historyRequest = 0

const follow = computed(() => followSelection(mergeSegments(segments.value ?? EMPTY_SEGMENTS), runtime.selectedSegment.value, 'charge'))
const charge = computed(() => follow.value.state === 'segment' ? follow.value.segment : null)

// A connector reports keys as they change, so a point rarely carries both. Each
// series carries its last known value forward before the two are paired.
const curve = computed(() => {
  let soc: number | null = null
  let power: number | null = null
  const points: Array<[number, number]> = []
  for (const point of history.value?.points ?? []) {
    soc = metricNumber(point.metrics['battery.soc']) ?? soc
    power = metricNumber(point.metrics['charging.power']) ?? power
    if (soc !== null && power !== null) points.push([soc, power])
  }
  return points.sort((left, right) => left[0] - right[0])
})
const series = computed(() => [{ name: t('insights.chargePower'), unit: 'kW', data: curve.value }])
const hasData = computed(() => curve.value.length > 1)
const peak = computed(() => charge.value?.charge?.peak_power ?? (curve.value.length ? Math.max(...curve.value.map((point) => point[1])) : undefined))
const average = computed(() => charge.value?.charge?.avg_power ?? (curve.value.length ? curve.value.reduce((total, point) => total + point[1], 0) / curve.value.length : undefined))

async function loadFeed(): Promise<void> {
  const current = ++segmentRequest
  segments.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadSegments(id, props.widget.time_range_days ?? 7)
  if (current === segmentRequest) segments.value = result
}

async function loadCurve(): Promise<void> {
  const current = ++historyRequest
  history.value = null
  const id = vehicle.value?.id
  const window = charge.value
  if (!id || !window) return
  const result = await loadHistory(id, { start: window.start, end: window.end, maxPoints: 400 }).catch(() => null)
  if (current === historyRequest && result) history.value = result
}

watch([() => vehicle.value?.id, () => props.widget.time_range_days], loadFeed, { immediate: true })
watch(() => charge.value && `${charge.value.start}-${charge.value.end}`, loadCurve, { immediate: true })
</script>

<template>
  <article class="widget-card charge-curve-widget">
    <div class="widget-head">
      <h2>{{ widget.title || t('insights.chargeCurve') }}</h2>
      <small v-if="hasData && peak !== undefined">{{ t('insights.peakAverage', { peak: peak.toFixed(1), average: (average ?? 0).toFixed(1) }) }}</small>
    </div>
    <div v-if="hasData" class="chart"><TimeSeriesChart :series="series" x-type="value" x-unit="%" height="100%" /></div>
    <DashboardWidgetEmpty v-else icon="charging" :loading="Boolean(vehicle)&&(segments===null||(Boolean(charge)&&history===null))" :message="follow.state==='out-of-range' ? t('insights.notInRange') : t('insights.noCharge')" />
  </article>
</template>

<style scoped>
.charge-curve-widget{padding:12px 14px 4px}
.chart{min-width:0;min-height:110px;flex:1}
</style>
