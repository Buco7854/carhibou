<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { DashboardWidget, History } from '../api/types'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'

const props = defineProps<{widget:DashboardWidget}>()
const history = ref<History|null>(null)
const series = computed(() => (props.widget.metrics ?? []).map((metric) => ({
  name: metric,
  data: (history.value?.points ?? []).flatMap((point) => {
    const value = metric === 'vehicle.speed' ? point.speed : point.metrics[metric]
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
})))
onMounted(async () => {
  if (!props.widget.vehicle_id) return
  const start = new Date(Date.now() - (props.widget.time_range_days ?? 1) * 86_400_000)
  history.value = await api<History>(`/vehicles/${props.widget.vehicle_id}/history?start=${encodeURIComponent(start.toISOString())}&max_points=500`)
})
</script>

<template><article class="widget-card"><span class="eyebrow">{{ widget.title || widget.metrics?.join(' · ') }}</span><TimeSeriesChart :series="series" :height="190" /></article></template>
