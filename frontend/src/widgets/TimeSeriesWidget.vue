<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, History } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { metricDefinition, metricLabel, preferredHistoryMetric } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const history = ref<History|null>(null)
let request = 0
const metric = computed(() => props.widget.metric || preferredHistoryMetric(vehicle.value, history.value?.available_metrics ?? [], (history.value?.points ?? []).some((point) => typeof point.speed==='number')))
const definition = computed(() => metricDefinition(metric.value))
const series = computed(() => [{name:props.widget.title||metricLabel(definition.value,t),unit:props.widget.unit??definition.value.unit,data:(history.value?.points??[]).flatMap((point) => {const value=metric.value==='vehicle.speed'?point.speed:point.metrics[metric.value];return typeof value==='number'?[[point.recorded_at,value] as [string,number]]:[]})}])
const hasData = computed(() => series.value.some((row) => row.data.length > 0))

async function loadHistory(): Promise<void> {
  const current=++request
  history.value=null
  const id=vehicle.value?.id
  if(!id)return
  const start=new Date(Date.now()-(props.widget.time_range_days??1)*86_400_000)
  const result=await api<History>(`/vehicles/${id}/history?start=${encodeURIComponent(start.toISOString())}&max_points=300`)
  if(current===request)history.value=result
}
watch([() => vehicle.value?.id, () => props.widget.time_range_days], loadHistory, { immediate:true })
</script>
<template><article class="widget-card history-widget"><header><div><span class="eyebrow">{{ t('dashboard.pastDay') }}</span><strong>{{ widget.title||metricLabel(definition,t) }}</strong></div><small>{{ vehicle?.name }}</small></header><div v-if="hasData" class="chart"><TimeSeriesChart :series="series" height="100%" /></div><DashboardWidgetEmpty v-else :icon="definition.icon" :loading="Boolean(vehicle)&&history===null" /></article></template>
<style scoped>.history-widget{padding:14px 16px 4px}.history-widget header{display:flex;align-items:center;justify-content:space-between;gap:12px}.history-widget header .eyebrow{margin-bottom:3px}.history-widget header strong{font-size:14px}.history-widget header small{color:var(--muted);font-size:8px}.chart{min-width:0;min-height:120px;flex:1}</style>
