<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget, Segments } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardVehicle } from './dashboardContext'
import { EMPTY_SEGMENTS, loadSegmentsBetween } from '../api/segments'

interface PeriodTotals {
  distance: number
  drives: number
  charges: number
  charged: number
  efficiency: number | null
}

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const current = ref<Segments | null>(null)
const previous = ref<Segments | null>(null)
let request = 0

const days = computed(() => props.widget.time_range_days ?? 7)

function totals(segments: Segments): PeriodTotals {
  const distance = segments.drives.reduce((sum, drive) => sum + (drive.distance_km ?? 0), 0)
  const charged = segments.charges.reduce((sum, charge) => sum + (charge.energy_kwh ?? 0), 0)
  const used = segments.drives.reduce((sum, drive) => sum + (drive.energy_kwh ?? 0), 0)
  return { distance, drives: segments.drives.length, charges: segments.charges.length, charged, efficiency: distance > 0 && used > 0 ? (used / distance) * 100 : null }
}

const now = computed(() => totals(current.value ?? EMPTY_SEGMENTS))
const before = computed(() => totals(previous.value ?? EMPTY_SEGMENTS))
const loaded = computed(() => current.value !== null)
const hasData = computed(() => now.value.drives > 0 || now.value.charged > 0)

function delta(value: number, baseline: number): string | null {
  if (!baseline) return null
  const change = ((value - baseline) / baseline) * 100
  if (!Number.isFinite(change) || Math.abs(change) < 1) return null
  return `${change > 0 ? '+' : ''}${change.toFixed(0)}%`
}

const stats = computed(() => [
  { key: 'distance', label: t('insights.distance'), value: `${now.value.distance.toFixed(0)} km`, delta: delta(now.value.distance, before.value.distance) },
  { key: 'drives', label: t('insights.drives'), value: String(now.value.drives), delta: delta(now.value.drives, before.value.drives) },
  { key: 'charged', label: t('insights.energyCharged'), value: now.value.charges === 0 ? '' : `${now.value.charged.toFixed(1)} kWh`, delta: delta(now.value.charged, before.value.charged) },
  { key: 'efficiency', label: t('insights.efficiency'), value: now.value.efficiency === null ? '' : `${now.value.efficiency.toFixed(1)} kWh/100km`, delta: now.value.efficiency === null || before.value.efficiency === null ? null : delta(now.value.efficiency, before.value.efficiency) },
].filter((stat) => stat.value !== ''))

async function load(): Promise<void> {
  const request_id = ++request
  current.value = null
  previous.value = null
  const id = vehicle.value?.id
  if (!id) return
  const span = days.value * 86_400_000
  const end = Date.now()
  const [latest, earlier] = await Promise.all([
    loadSegmentsBetween(id, new Date(end - span), new Date(end)),
    loadSegmentsBetween(id, new Date(end - span * 2), new Date(end - span)),
  ])
  if (request_id !== request) return
  current.value = latest
  previous.value = earlier
}
watch([() => vehicle.value?.id, days], load, { immediate: true })
</script>

<template>
  <article class="widget-card period-stats-widget">
    <div class="widget-head">
      <h2>{{ widget.title || t('dashboards.periodStats') }}</h2>
      <small>{{ t('insights.lastDays', { days }) }}</small>
    </div>
    <dl v-if="hasData" class="stat-grid">
      <div v-for="stat in stats" :key="stat.key">
        <dt>{{ stat.label }}</dt>
        <dd>{{ stat.value }}<span v-if="stat.delta" :class="['delta', stat.delta.startsWith('+') ? 'up' : 'down']">{{ stat.delta }}</span></dd>
      </div>
    </dl>
    <DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&!loaded" :message="t('insights.noPeriod')" />
  </article>
</template>

<style scoped>
.period-stats-widget{padding:12px 14px}
.delta{font-size:var(--font-caption);font-weight:500;letter-spacing:0}
.delta.up{color:var(--success)}
.delta.down{color:var(--muted)}
</style>
