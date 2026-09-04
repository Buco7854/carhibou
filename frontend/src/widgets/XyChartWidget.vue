<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { EMPTY_SEGMENTS, loadHistory, loadSegments, rangeStart } from '../api/segments'
import type { DashboardWidget, History, Segments } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { medianGap, splitAtXReversals, type ChartPoint } from '../chartData'
import { formatInstantBrief, formatMetricNumber, historyValue, metricDefinition, metricLabel } from '../vehicleDisplay'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { followSelection, mergeSegments } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
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
const scoped = computed(() => (follow.value.state === 'segment' ? follow.value.segment : null))
/**
 * That the chart is showing one session rather than the range.
 *
 * Picking a charge in the activity feed narrows this card to that window, which
 * looks identical to a range that happens to hold one session: the other lines
 * are gone and nothing says they were dropped on purpose. Naming the session is
 * what tells the two apart. The way back is the tap that got here — the feed row
 * is a toggle — so this is a caption and not another control.
 */
const scopeLabel = computed(() => (scoped.value
  ? `${t(`insights.kind.${scoped.value.kind}`)} · ${formatInstantBrief(scoped.value.start, locale.value)}`
  : ''))



/**
 * How long a reading may stand in for itself before it stops being true.
 *
 * The two axes almost never arrive together: on a real car the charge level
 * comes from one CAN frame and the charge power from another, in separate
 * samples, so pairing them at all means carrying each one forward. Carrying it
 * without limit is what makes a scatter plot lie: a charge level from an hour
 * ago plotted against a power from now is a point that never existed.
 *
 * The bound follows the data rather than a guess about it. Each axis reports at
 * some cadence, and a value is worth carrying across a few of its own intervals
 * and no further, so the window is four times the slower axis's median spacing.
 * A car on CAN alternating frames every eight seconds gets about a minute; a
 * connector relaying one key every ten gets the half hour it needs to pair at
 * all. The clamp stops a fast cadence making the window uselessly tight, and
 * stops a source that spoke twice in a day making it meaningless. A series with
 * only one reading has no cadence to measure, so it gets the widest window and
 * the pairing still fails if its partner is further away than that.
 */
const MIN_CARRY_MS = 30_000
const MAX_CARRY_MS = 1_800_000

function carryWindow(xStamps: number[], yStamps: number[]): number {
  const slower = Math.max(medianGap(xStamps), medianGap(yStamps))
  if (!Number.isFinite(slower)) return MAX_CARRY_MS
  return Math.min(MAX_CARRY_MS, Math.max(MIN_CARRY_MS, slower * 4))
}

interface PairedReading { at: number; x: number; y: number }

const paired = computed<PairedReading[]>(() => {
  const points = history.value?.points ?? []
  const xStamps: number[] = []
  const yStamps: number[] = []
  const observed: Array<{ at: number; x: number | null; y: number | null }> = []
  for (const point of points) {
    const at = new Date(point.recorded_at).getTime()
    const x = historyValue(point, xMetric.value)
    const y = historyValue(point, yMetric.value)
    if (x === null && y === null) continue
    if (x !== null) xStamps.push(at)
    if (y !== null) yStamps.push(at)
    observed.push({ at, x, y })
  }
  if (!xStamps.length || !yStamps.length) return []

  const window = carryWindow(xStamps, yStamps)
  const pairs: PairedReading[] = []
  let lastX: { at: number; value: number } | null = null
  let lastY: { at: number; value: number } | null = null
  for (const sample of observed) {
    if (sample.x !== null) lastX = { at: sample.at, value: sample.x }
    if (sample.y !== null) lastY = { at: sample.at, value: sample.y }
    if (!lastX || !lastY) continue
    // Both ends must still be recent enough to describe the same moment.
    if (sample.at - lastX.at > window || sample.at - lastY.at > window) continue
    const previous = pairs.at(-1)
    if (previous && previous.x === lastX.value && previous.y === lastY.value) continue
    pairs.push({ at: sample.at, x: lastX.value, y: lastY.value })
  }
  return pairs
})

/**
 * The plot's monotonic runs, each with the moment it began.
 *
 * On a charge curve a run is a session: the x axis is the charge level, so it
 * climbs while one session lasts and drops back when the next one starts lower.
 * The runs come out in order and lose no points, so walking the pairs alongside
 * them recovers when each one started.
 */
const runs = computed<Array<{ startedAt: number; data: ChartPoint[] }>>(() => {
  let offset = 0
  return splitAtXReversals(paired.value.map((pair) => [pair.x, pair.y] as ChartPoint)).map((data) => {
    const startedAt = paired.value[offset]?.at ?? 0
    offset += data.length
    return { startedAt, data }
  })
})

/**
 * One series per run, named for when it began.
 *
 * Several sessions used to share one colour and one name, so a reader saw two
 * anonymous lines and no way to tell this morning's charge from tonight's. A
 * run now carries its own start, its own palette slot and its own legend entry.
 * One run keeps exactly what it had: the metric's own name, no legend, and the
 * single-series tooltip that does not repeat a name the card's head has said.
 */
const series = computed(() => {
  const unit = yDefinition.value.unit
  if (runs.value.length < 2) {
    return [{ name: metricLabel(yDefinition.value, t), unit, data: runs.value[0]?.data ?? [] }]
  }
  return runs.value.map((run) => ({
    name: formatInstantBrief(new Date(run.startedAt).toISOString(), locale.value),
    unit,
    data: run.data,
  }))
})
const hasData = computed(() => paired.value.length > 1)
// Both figures describe everything the range holds, however many runs it took.
const peak = computed(() => paired.value.length ? Math.max(...paired.value.map((pair) => pair.y)) : undefined)
const average = computed(() => paired.value.length
  ? paired.value.reduce((total, pair) => total + pair.y, 0) / paired.value.length
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
      <div class="chart-title">
        <h2>{{ heading }}</h2>
        <span v-if="scopeLabel" class="chart-scope">{{ scopeLabel }}</span>
      </div>
      <small v-if="hasData && peak !== undefined">{{ t('insights.peakAverage', { peak: formatMetricNumber(peak, yDefinition, locale), average: formatMetricNumber(average ?? 0, yDefinition, locale) }) }}</small>
    </div>
    <div v-if="hasData" class="chart">
      <!-- A custom title need not name the metrics, so the axes say which they
           are only then; by default the heading has already said it. -->
      <TimeSeriesChart
        :series="series"
        x-type="value"
        :x-unit="xDefinition.unit"
        :y-unit="yDefinition.unit"
        :x-name="widget.title ? metricLabel(xDefinition, t) : ''"
        :y-name="widget.title ? metricLabel(yDefinition, t) : ''"
        :label="heading"
        height="100%"
      />
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
.chart-title{min-width:0}
/* Which session the card was narrowed to, under the shape's own name. */
.chart-scope{display:block;margin-top:2px;overflow:hidden;color:var(--text);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
</style>
