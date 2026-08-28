<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EMPTY_SEGMENTS, loadHistory, loadSegments, rangeStart } from '../api/segments'
import type { DashboardWidget, History, Segments } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { historyValue, metricDefinition, metricLabel } from '../vehicleDisplay'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { followSelection, mergeSegments } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const history = ref<History | null>(null)
const segments = ref<Segments | null>(null)
let segmentRequest = 0
let request = 0

// A generic chart never guesses its axes: unset means unset, and the card says
// so rather than plotting metrics the vehicle may not have.
const xMetric = computed(() => props.widget.x_metric ?? '')
const yMetric = computed(() => props.widget.y_metric ?? '')
const configured = computed(() => Boolean(xMetric.value && yMetric.value))
const xDefinition = computed(() => metricDefinition(xMetric.value))
const yDefinition = computed(() => metricDefinition(yMetric.value))
const days = computed(() => props.widget.time_range_days ?? 7)
/**
 * This card is a shape, so its head names the axes it is bound to and nothing
 * else. A concept name would claim the card is about that concept when it is
 * about whatever the reader pointed it at, so the Charge-curve entry in the
 * picker is only a shortcut for the prefill and does not survive into the head.
 * The generic name is honest just once: when no axes have been chosen.
 */
const heading = computed(() => {
  if (props.widget.title) return props.widget.title
  if (!configured.value) return t('dashboards.xyChart')
  return t('dashboards.axisPair', { y: metricLabel(yDefinition.value, t), x: metricLabel(xDefinition.value, t) })
})

// A selection this range holds scopes the chart to that window. One it does not
// hold is said so, and no selection at all plots the widget's own range rather
// than guessing at a segment.
const follow = computed(() => runtime.selectedSegment.value
  ? followSelection(mergeSegments(segments.value ?? EMPTY_SEGMENTS), runtime.selectedSegment.value)
  : ({ state: 'none' } as const))
const outOfRange = computed(() => follow.value.state === 'out-of-range')



// A source reports keys as they change, so a point rarely carries both. Each
// series carries its last known value forward before the two are paired.
const paired = computed<Array<[number, number]>>(() => {
  let x: number | null = null
  let y: number | null = null
  const points: Array<[number, number]> = []
  for (const point of history.value?.points ?? []) {
    x = historyValue(point, xMetric.value) ?? x
    y = historyValue(point, yMetric.value) ?? y
    if (x !== null && y !== null) points.push([x, y])
  }
  return points
})

const series = computed(() => [{
  name: metricLabel(yDefinition.value, t),
  unit: yDefinition.value.unit,
  data: paired.value,
}])
const hasData = computed(() => paired.value.length > 1)
const peak = computed(() => paired.value.length ? Math.max(...paired.value.map((point) => point[1])) : undefined)
const average = computed(() => paired.value.length
  ? paired.value.reduce((total, point) => total + point[1], 0) / paired.value.length
  : undefined)

async function load(): Promise<void> {
  const current = ++request
  history.value = null
  const id = vehicle.value?.id
  if (!id) return
  if (outOfRange.value) return
  const scoped = follow.value.state === 'segment' ? follow.value.segment : null
  const window = scoped
    ? { start: scoped.start, end: scoped.end }
    : { start: rangeStart(days.value).toISOString(), end: new Date().toISOString() }
  const result = await loadHistory(id, { ...window, maxPoints: 400 }).catch(() => null)
  if (current === request && result) history.value = result
}
async function loadFeed(): Promise<void> {
  const current = ++segmentRequest
  segments.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadSegments(id, days.value)
  if (current === segmentRequest) segments.value = result
}

watch([() => vehicle.value?.id, days, runtime.dataVersion], loadFeed, { immediate: true })
watch(
  [() => vehicle.value?.id, days, xMetric, yMetric, () => follow.value.state === 'segment' ? follow.value.segment.start : follow.value.state],
  load,
  { immediate: true },
)
</script>

<template>
  <article class="widget-card xy-chart-widget">
    <div class="widget-head">
      <h2>{{ heading }}</h2>
      <small v-if="hasData && peak !== undefined">{{ t('insights.peakAverage', { peak: peak.toFixed(1), average: (average ?? 0).toFixed(1) }) }}</small>
    </div>
    <div v-if="hasData" class="chart">
      <TimeSeriesChart :series="series" x-type="value" :x-unit="xDefinition.unit" height="100%" />
    </div>
    <DashboardWidgetEmpty
      v-else
      :icon="yDefinition.icon"
      :loading="configured && Boolean(vehicle) && !outOfRange && history === null"
      :message="!configured ? t('dashboards.chooseAxes') : outOfRange ? t('insights.notInRange') : t('insights.noPairs')"
    />
  </article>
</template>

<style scoped>
.xy-chart-widget{padding:12px 14px 4px}
.chart{min-width:0;min-height:110px;flex:1}
</style>
