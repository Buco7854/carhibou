<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, Segments } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatFixedNumber } from '../numberFormat'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, loadSegments } from '../api/segments'
import { formatInstant, formatSpan } from '../vehicleDisplay'
import { followSelection, mergeSegments } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const segments = ref<Segments | null>(null)
let request = 0

const follow = computed(() => followSelection(mergeSegments(segments.value ?? EMPTY_SEGMENTS), runtime.selectedSegment.value))
const segment = computed(() => follow.value.state === 'segment' ? follow.value.segment : null)

interface Stat { key: string; label: string; value: string }

function number(value: number | undefined, digits: number, unit: string): string | null {
  return value === undefined ? null : `${formatFixedNumber(value, locale.value, digits)} ${unit}`
}

/**
 * One segment, told the way somebody reads it.
 *
 * A drive is a distance and a charge is an energy added; that number leads. The
 * rest support it at reading size rather than competing as five equal display
 * numbers in an auto-fit grid, which is what left them cramped and clipped. The
 * charge span is a range, so it is drawn as one rather than squeezed into a slot
 * sized for a single figure.
 */
const lead = computed<Stat | null>(() => {
  const current = segment.value
  if (!current) return null
  if (current.kind === 'drive' && current.drive) {
    const value = number(current.drive.distance_km, 1, 'km')
    return value ? { key: 'distance', label: t('insights.distance'), value } : null
  }
  if (current.charge) {
    const value = number(current.charge.energy_kwh, 1, 'kWh')
    return value ? { key: 'energy', label: t('insights.energyAdded'), value } : null
  }
  return null
})

const span = computed<string | null>(() => {
  const charge = segment.value?.kind === 'charge' ? segment.value.charge : undefined
  if (!charge || charge.soc_start === undefined || charge.soc_end === undefined) return null
  return `${formatFixedNumber(charge.soc_start, locale.value, 0)}% → ${formatFixedNumber(charge.soc_end, locale.value, 0)}%`
})

const facts = computed<Stat[]>(() => {
  const current = segment.value
  if (!current) return []
  const rows: Array<[string, string, string | null]> = []
  if (current.kind === 'drive' && current.drive) {
    const drive = current.drive
    rows.push(['duration', t('insights.duration'), formatSpan(drive.duration_seconds, locale.value)])
    rows.push(['avgSpeed', t('insights.avgSpeed'), number(drive.avg_speed, 0, 'km/h')])
    rows.push(['maxSpeed', t('insights.maxSpeed'), number(drive.max_speed, 0, 'km/h')])
    rows.push(['energy', t('insights.energyUsed'), number(drive.energy_kwh, 1, 'kWh')])
  } else if (current.charge) {
    const charge = current.charge
    rows.push(['duration', t('insights.duration'), formatSpan(charge.duration_seconds, locale.value)])
    rows.push(['peak', t('insights.peakPower'), number(charge.peak_power, 1, 'kW')])
  }
  return rows.flatMap(([key, label, value]) => value === null ? [] : [{ key, label, value }])
})

const hasSegment = computed(() => Boolean(lead.value || span.value || facts.value.length))

async function load(): Promise<void> {
  const current = ++request
  segments.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadSegments(id, props.widget.time_range_days ?? 7)
  if (current === request) segments.value = result
}
watch([() => vehicle.value?.id, () => props.widget.time_range_days, runtime.dataVersion], load, { immediate: true })
</script>

<template>
  <article class="widget-card segment-stats-widget">
    <div class="widget-head">
      <h2>{{ widget.title || t('dashboards.segmentStats') }}</h2>
      <small v-if="segment">{{ t(`insights.kind.${segment.kind}`) }} · {{ formatInstant(segment.start) }}</small>
    </div>
    <div v-if="hasSegment" class="segment-body">
      <p v-if="lead" class="segment-lead"><strong>{{ lead.value }}</strong><span>{{ lead.label }}</span></p>
      <p v-if="span" class="segment-span">{{ span }}</p>
      <dl v-if="facts.length" class="segment-facts">
        <div v-for="fact in facts" :key="fact.key"><dt>{{ fact.label }}</dt><dd>{{ fact.value }}</dd></div>
      </dl>
    </div>
    <DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&segments===null" :message="follow.state==='out-of-range' ? t('insights.notInRange') : t('insights.noSegment')" />
  </article>
</template>

<style scoped>
.segment-stats-widget{padding:12px 14px}
.segment-body{min-height:0;flex:1;display:flex;flex-direction:column;justify-content:center;gap:10px}
.segment-lead{display:flex;align-items:baseline;flex-wrap:wrap;gap:4px 8px;margin:0}
.segment-lead strong{font-size:var(--font-value);font-weight:500;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.segment-lead span{color:var(--muted);font-size:var(--font-caption)}
/* A range, drawn as one: two figures and the arrow between them, at reading
   size so neither end is ever the thing that gets cut. */
.segment-span{width:max-content;max-width:100%;margin:0;padding:3px 9px;color:var(--text);background:var(--panel-2);border-radius:var(--radius);font-size:var(--font-body);font-weight:500;font-variant-numeric:tabular-nums}
.segment-facts{display:flex;flex-wrap:wrap;gap:6px 18px;margin:0}
.segment-facts>div{min-width:0;display:flex;align-items:baseline;gap:6px}
.segment-facts dt{color:var(--muted);font-size:var(--font-caption)}
.segment-facts dd{margin:0;font-size:var(--font-body);font-weight:500;font-variant-numeric:tabular-nums;overflow-wrap:anywhere}
</style>
