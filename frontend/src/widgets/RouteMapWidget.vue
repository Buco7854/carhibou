<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, History, Segments } from '../api/types'
import { formatDuration } from '../agentCadence'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import VehicleMap, { type TrailPoint } from '../components/VehicleMap.vue'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, loadHistory, loadSegments, rangeStart } from '../api/segments'
import { pathLengthKm } from '../geo'
import { formatInstant } from '../vehicleDisplay'
import { followSelection, mergeSegments, metricNumber } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const segments = ref<Segments | null>(null)
const history = ref<History | null>(null)
const marks = ref<number[]>([])
let segmentRequest = 0
let historyRequest = 0

const follow = computed(() => followSelection(mergeSegments(segments.value ?? EMPTY_SEGMENTS), runtime.selectedSegment.value, 'drive'))
const drive = computed(() => follow.value.state === 'segment' ? follow.value.segment : null)
const outOfRange = computed(() => follow.value.state === 'out-of-range')
const points = computed(() => (history.value?.points ?? []).filter((point) => point.latitude !== null && point.longitude !== null))
const trail = computed<TrailPoint[]>(() => points.value.map((point) => ({ lat: point.latitude!, lng: point.longitude!, speed: point.speed })))
const position = computed(() => vehicle.value?.state?.position ?? null)
const hasTrail = computed(() => trail.value.length > 1)
const hasMapData = computed(() => !outOfRange.value && (hasTrail.value || Boolean(position.value)))

function pick(index: number): void {
  const chosen = marks.value.includes(index) ? marks.value.filter((mark) => mark !== index) : [...marks.value, index]
  marks.value = chosen.slice(-2).sort((left, right) => left - right)
}

const readout = computed(() => {
  if (marks.value.length !== 2) return null
  const [from, to] = marks.value as [number, number]
  const slice = points.value.slice(from, to + 1)
  if (slice.length < 2) return null
  const leg = (rows: typeof slice) => pathLengthKm(rows.map((row) => ({ lat: row.latitude!, lng: row.longitude! })))
  const walked = leg(slice)
  const whole = leg(points.value)
  const measured = drive.value?.drive?.distance_km
  // The trail is downsampled, so its haversine runs short of the distance the
  // server measured over every row; the drive's own total sets the scale.
  const scale = measured !== undefined && whole > 0 ? measured / whole : null
  const distance = scale === null ? walked : walked * scale
  const seconds = (new Date(slice.at(-1)!.recorded_at).getTime() - new Date(slice[0]!.recorded_at).getTime()) / 1000
  const socFrom = metricNumber(slice[0]!.metrics['battery.soc'])
  const socTo = metricNumber(slice.at(-1)!.metrics['battery.soc'])
  const capacity = vehicle.value?.battery_nominal_capacity_kwh ?? null
  const socDelta = socFrom !== null && socTo !== null ? socFrom - socTo : null
  return {
    estimated: scale === null,
    distance: distance.toFixed(1),
    duration: formatDuration(Math.max(seconds, 0), locale.value),
    soc: socDelta === null ? null : `${socDelta.toFixed(0)}%`,
    energy: socDelta === null || capacity === null ? null : `${((socDelta / 100) * capacity).toFixed(1)} kWh`,
  }
})

async function loadFeed(): Promise<void> {
  const current = ++segmentRequest
  segments.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadSegments(id, props.widget.time_range_days ?? 7)
  if (current === segmentRequest) segments.value = result
}

async function loadTrail(): Promise<void> {
  const current = ++historyRequest
  history.value = null
  marks.value = []
  const id = vehicle.value?.id
  if (!id) return
  const window = drive.value ?? { start: rangeStart(props.widget.time_range_days ?? 7).toISOString(), end: new Date().toISOString() }
  const result = await loadHistory(id, { start: window.start, end: window.end, maxPoints: 400 }).catch(() => null)
  if (current === historyRequest && result) history.value = result
}

watch([() => vehicle.value?.id, () => props.widget.time_range_days, runtime.dataVersion], loadFeed, { immediate: true })
watch([() => vehicle.value?.id, () => drive.value && `${drive.value.start}-${drive.value.end}`, runtime.dataVersion], loadTrail, { immediate: true })
</script>

<template>
  <article class="widget-card route-map-widget">
    <div class="widget-head">
      <div>
        <h2>{{ widget.title || t('dashboards.routeMap') }}</h2>
        <span>{{ drive ? formatInstant(drive.start) : t('insights.wholeRange') }}</span>
      </div>
      <small>{{ t('insights.pickHint') }}</small>
    </div>
    <div v-if="hasMapData" class="map-stage">
      <VehicleMap :position="position" :trail="trail" :marks="marks" @pick="pick" />
    </div>
    <DashboardWidgetEmpty v-else icon="location" :loading="Boolean(vehicle)&&!outOfRange&&history===null" :message="outOfRange ? t('insights.notInRange') : t('insights.noRoute')" />
    <dl v-if="readout" class="route-readout">
      <div><dt>{{ readout.estimated ? t('insights.distanceEstimate') : t('insights.distance') }}</dt><dd>{{ readout.distance }} km</dd></div>
      <div><dt>{{ t('insights.duration') }}</dt><dd>{{ readout.duration }}</dd></div>
      <div v-if="readout.soc"><dt>{{ t('insights.socUsed') }}</dt><dd>{{ readout.soc }}</dd></div>
      <div v-if="readout.energy"><dt>{{ t('insights.energyUsed') }}</dt><dd>{{ readout.energy }}</dd></div>
    </dl>
  </article>
</template>

<style scoped>
.route-map-widget{padding:0}
.route-map-widget .dashboard-widget-empty{padding:12px 14px}
.route-map-widget .widget-head{min-height:46px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px 10px;border-bottom:1px solid var(--line)}
.route-map-widget .widget-head>div{min-width:0}
.route-map-widget h2{margin:0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);font-weight:500;letter-spacing:.01em;text-overflow:ellipsis;white-space:nowrap}
.route-map-widget .widget-head span{display:block;margin-top:2px;overflow:hidden;color:var(--text);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.route-map-widget .widget-head small{flex:none;color:var(--muted-2);font-size:var(--font-micro);text-align:right}
.map-stage{position:relative;min-height:0;flex:1}
.map-stage :deep(.map-frame),.map-stage :deep(.vehicle-map){height:100%;min-height:0}
.route-readout{display:flex;flex-wrap:wrap;gap:6px 20px;margin:0;padding:10px 14px;border-top:1px solid var(--line)}
.route-readout dt{color:var(--muted);font-size:var(--font-micro)}
.route-readout dd{margin:1px 0 0;font-size:var(--font-caption);font-weight:500;font-variant-numeric:tabular-nums}
@media(max-width:700px){.route-map-widget .widget-head small{display:none}.route-readout{gap:6px 14px}}
</style>
