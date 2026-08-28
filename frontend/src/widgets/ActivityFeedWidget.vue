<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, SegmentKind, Segments } from '../api/types'
import { formatDuration } from '../agentCadence'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, loadSegments } from '../api/segments'
import { formatInstant } from '../vehicleDisplay'
import { isSelected, mergeSegments, segmentKey, type FeedSegment } from './segments'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const segments = ref<Segments | null>(null)
const filter = ref<SegmentKind | 'all'>('all')
let request = 0

const feed = computed(() => mergeSegments(segments.value ?? EMPTY_SEGMENTS))
const rows = computed(() => filter.value === 'all' ? feed.value : feed.value.filter((segment) => segment.kind === filter.value))

function headline(segment: FeedSegment): string {
  if (segment.kind === 'drive') {
    const distance = segment.drive?.distance_km
    return distance === undefined ? t('insights.drive') : t('insights.driveDistance', { distance: distance.toFixed(1) })
  }
  const energy = segment.charge?.energy_kwh
  return energy === undefined ? t('insights.charge') : t('insights.chargeEnergy', { energy: energy.toFixed(1) })
}

function detail(segment: FeedSegment): string {
  const parts = [formatInstant(segment.start), formatDuration(segment.duration_seconds, locale.value)]
  const soc = segment.kind === 'drive' ? segment.drive : segment.charge
  if (soc?.soc_start !== undefined && soc?.soc_end !== undefined) parts.push(`${Math.round(soc.soc_start)}% → ${Math.round(soc.soc_end)}%`)
  return parts.join(' · ')
}

function choose(segment: FeedSegment): void {
  const selected = isSelected(runtime.selectedSegment.value, segment)
  runtime.selectSegment(selected ? null : { kind: segment.kind, start: segment.start, end: segment.end })
}

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
  <article class="widget-card activity-feed-widget">
    <div class="widget-head">
      <h2>{{ widget.title || t('dashboards.activityFeed') }}</h2>
      <div class="feed-filter" role="group" :aria-label="t('insights.filter')">
        <button v-for="option in (['all','drive','charge'] as const)" :key="option" type="button" :class="{ active: filter===option }" :aria-pressed="filter===option" @click="filter=option">{{ t(`insights.filterOption.${option}`) }}</button>
      </div>
    </div>
    <ul v-if="rows.length" class="feed-list">
      <li v-for="segment in rows" :key="segmentKey(segment)">
        <button type="button" :class="['feed-row', segment.kind, { selected: isSelected(runtime.selectedSegment.value, segment) }]" :aria-pressed="isSelected(runtime.selectedSegment.value, segment)" @click="choose(segment)">
          <span class="feed-kind">{{ t(`insights.kind.${segment.kind}`) }}</span>
          <span class="feed-headline">{{ headline(segment) }}</span>
          <small>{{ detail(segment) }}</small>
        </button>
      </li>
    </ul>
    <DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&segments===null" :message="t('insights.noActivity')" />
  </article>
</template>

<style scoped>
.activity-feed-widget{padding:12px 14px 8px}
.widget-head{align-items:center}
.feed-filter{flex:none;display:flex;gap:2px;padding:2px;background:var(--panel-2);border-radius:var(--radius)}
.feed-filter button{padding:3px 8px;color:var(--muted);background:transparent;border:0;border-radius:var(--radius-sm);font-size:var(--font-micro);cursor:pointer}
.feed-filter button.active{color:var(--text);background:var(--panel)}
.feed-list{min-height:0;flex:1;overflow-y:auto;display:grid;align-content:start;gap:4px;margin:0;padding:0;list-style:none}
.feed-row{width:100%;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:baseline;gap:2px 10px;padding:7px 9px;background:transparent;border:1px solid transparent;border-radius:var(--radius);text-align:left;cursor:pointer}
.feed-row:hover{background:var(--panel-2)}
.feed-row.selected{background:var(--accent-soft);border-color:var(--accent)}
.feed-kind{padding:1px 6px;border-radius:var(--radius-sm);font-size:var(--font-micro);line-height:1.5}
.feed-row.drive .feed-kind{color:var(--accent);background:var(--accent-soft)}
.feed-row.charge .feed-kind{color:var(--success);background:var(--success-soft)}
.feed-headline{min-width:0;overflow:hidden;color:var(--text);font-size:var(--font-caption);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.feed-row small{grid-column:2;overflow:hidden;color:var(--muted);font-size:var(--font-micro);text-overflow:ellipsis;white-space:nowrap}
@media(max-width:700px){.feed-row{grid-template-columns:1fr}.feed-row small,.feed-headline{grid-column:1}}
</style>
