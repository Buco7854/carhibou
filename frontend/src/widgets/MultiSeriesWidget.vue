<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, History } from '../api/types'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { metricDefinition, metricLabel } from '../vehicleDisplay'

const props = defineProps<{widget:DashboardWidget}>()
const { t } = useI18n()
const history = ref<History|null>(null)
const title = computed(() => props.widget.title || (props.widget.metrics ?? []).map((metric) => metricLabel(metricDefinition(metric), t)).join(' · '))
const series = computed(() => (props.widget.metrics ?? []).map((metric) => ({
  name: metricLabel(metricDefinition(metric), t),
  unit: metricDefinition(metric).unit,
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

<template><article class="widget-card"><span class="eyebrow">{{ title }}</span><TimeSeriesChart :series="series" :height="190" /></article></template>
