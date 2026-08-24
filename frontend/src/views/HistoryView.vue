<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'
import { api } from '../api/client'
import type { History, Position, Vehicle } from '../api/types'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMap from '../components/VehicleMap.vue'

const { t } = useI18n()
const route = useRoute()
const vehicle = ref<Vehicle | null>(null)
const history = ref<History | null>(null)
const metric = ref('battery.soc')
const days = ref(1)
const error = ref('')
const vehicleId = String(route.params.id)
const routePoints = computed<Array<[number, number]>>(() => (history.value?.points ?? []).flatMap((point) => point.latitude !== null && point.longitude !== null ? [[point.latitude, point.longitude]] : []))
const lastPosition = computed<Position | null>(() => {
  const point = [...(history.value?.points ?? [])].reverse().find((row) => row.latitude !== null && row.longitude !== null)
  return point ? { latitude: point.latitude!, longitude: point.longitude!, altitude: null, speed: point.speed, heading: point.heading, accuracy: null } : null
})
const series = computed(() => [{
  name: metric.value,
  data: (history.value?.points ?? []).flatMap((point) => {
    const value = metric.value === 'vehicle.speed' ? point.speed : point.metrics[metric.value]
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])

async function load() {
  error.value = ''
  const end = new Date()
  const start = new Date(end.getTime() - days.value * 86_400_000)
  try {
    ;[vehicle.value, history.value] = await Promise.all([
      api<Vehicle>(`/vehicles/${vehicleId}`),
      api<History>(`/vehicles/${vehicleId}/history?start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}&max_points=1500`),
    ])
    if (history.value.available_metrics.length && !history.value.available_metrics.includes(metric.value)) metric.value = history.value.available_metrics[0] ?? 'vehicle.speed'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
watch(days, load)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('history.eyebrow') }}</span><h1>{{ vehicle?.name }} · {{ t('history.title') }}</h1></div><RouterLink class="button secondary no-underline" to="/">← {{ t('nav.dashboard') }}</RouterLink></header>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="mb-4 flex flex-wrap gap-3">
      <label class="field min-w-56"><span>{{ t('history.metric') }}</span><select v-model="metric" class="select"><option value="vehicle.speed">vehicle.speed</option><option v-for="name in history?.available_metrics" :key="name">{{ name }}</option></select></label>
      <label class="field min-w-40"><span>{{ t('history.range') }}</span><select v-model="days" class="select"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></select></label>
      <span v-if="history" class="muted self-end pb-3 text-xs">{{ t('history.samples', { count: history.original_count }) }}</span>
    </div>
    <div v-if="history?.points.length" class="grid gap-4 xl:grid-cols-2">
      <section class="panel overflow-hidden"><div class="border-b p-4" style="border-color:var(--line)"><span class="eyebrow">{{ t('history.route') }}</span></div><div class="h-96"><VehicleMap :position="lastPosition" :route="routePoints" /></div></section>
      <section class="panel p-5"><span class="eyebrow">{{ metric }}</span><TimeSeriesChart :series="series" :height="355" /></section>
    </div>
    <div v-else class="panel empty">{{ t('history.noData') }}</div>
  </div>
</template>
