<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, Segments } from '../api/types'
import { formatDuration } from '../agentCadence'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, followSelection, loadSegments, mergeSegments } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const segments = ref<Segments | null>(null)
let request = 0

const segment = computed(() => followSelection(mergeSegments(segments.value ?? EMPTY_SEGMENTS), runtime.selectedSegment.value))

interface Stat { key: string; label: string; value: string }

function number(value: number | undefined, digits: number, unit: string): string | null {
  return value === undefined ? null : `${value.toFixed(digits)} ${unit}`
}

const stats = computed<Stat[]>(() => {
  const current = segment.value
  if (!current) return []
  const rows: Array<[string, string, string | null]> = []
  if (current.kind === 'drive' && current.drive) {
    const drive = current.drive
    rows.push(['distance', t('insights.distance'), number(drive.distance_km, 1, 'km')])
    rows.push(['duration', t('insights.duration'), formatDuration(drive.duration_seconds, locale.value)])
    rows.push(['avgSpeed', t('insights.avgSpeed'), number(drive.avg_speed, 0, 'km/h')])
    rows.push(['maxSpeed', t('insights.maxSpeed'), number(drive.max_speed, 0, 'km/h')])
    rows.push(['energy', t('insights.energyUsed'), number(drive.energy_kwh, 1, 'kWh')])
  } else if (current.charge) {
    const charge = current.charge
    rows.push(['energy', t('insights.energyAdded'), number(charge.energy_kwh, 1, 'kWh')])
    rows.push(['duration', t('insights.duration'), formatDuration(charge.duration_seconds, locale.value)])
    rows.push(['soc', t('insights.socSpan'), charge.soc_start === undefined || charge.soc_end === undefined ? null : `${Math.round(charge.soc_start)}% → ${Math.round(charge.soc_end)}%`])
    rows.push(['peak', t('insights.peakPower'), number(charge.peak_power, 1, 'kW')])
  }
  return rows.flatMap(([key, label, value]) => value === null ? [] : [{ key, label, value }])
})

async function load(): Promise<void> {
  const current = ++request
  segments.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadSegments(id, props.widget.time_range_days ?? 7)
  if (current === request) segments.value = result
}
watch([() => vehicle.value?.id, () => props.widget.time_range_days], load, { immediate: true })
</script>

<template>
  <article class="widget-card segment-stats">
    <div class="widget-head">
      <h2>{{ widget.title || t('insights.segmentStats') }}</h2>
      <small v-if="segment">{{ t(`insights.kind.${segment.kind}`) }} · {{ new Date(segment.start).toLocaleString() }}</small>
    </div>
    <dl v-if="stats.length" class="stat-grid">
      <div v-for="stat in stats" :key="stat.key"><dt>{{ stat.label }}</dt><dd>{{ stat.value }}</dd></div>
    </dl>
    <DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&segments===null" :message="t('insights.noSegment')" />
  </article>
</template>

<style scoped>
.segment-stats{padding:12px 14px}
.stat-grid{min-height:0;flex:1;display:grid;grid-template-columns:repeat(auto-fit,minmax(104px,1fr));align-content:center;gap:12px 16px;margin:0}
.stat-grid>div{min-width:0}
.stat-grid dt{color:var(--muted);font-size:var(--font-caption)}
.stat-grid dd{margin:3px 0 0;overflow:hidden;font-size:var(--font-value);font-weight:500;letter-spacing:-.02em;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}
@media(max-width:700px){.stat-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.stat-grid dd{font-size:var(--font-section)}}
</style>
