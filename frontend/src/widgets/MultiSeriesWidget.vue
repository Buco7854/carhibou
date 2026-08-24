<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, History } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { metricDefinition, metricLabel } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const history = ref<History|null>(null)
let request=0
const title = computed(() => props.widget.title || (props.widget.metrics ?? []).map((metric) => metricLabel(metricDefinition(metric), t)).join(' · '))
const series = computed(() => (props.widget.metrics ?? []).map((metric) => ({name:metricLabel(metricDefinition(metric),t),unit:metricDefinition(metric).unit,data:(history.value?.points??[]).flatMap((point) => {const value=metric==='vehicle.speed'?point.speed:point.metrics[metric];return typeof value==='number'?[[point.recorded_at,value] as [string,number]]:[]})})))
const hasData = computed(() => series.value.some((row) => row.data.length > 0))
async function loadHistory():Promise<void>{const current=++request;history.value=null;const id=vehicle.value?.id;if(!id)return;const start=new Date(Date.now()-(props.widget.time_range_days??1)*86_400_000);const result=await api<History>(`/vehicles/${id}/history?start=${encodeURIComponent(start.toISOString())}&max_points=500`);if(current===request)history.value=result}
watch([() => vehicle.value?.id, () => props.widget.time_range_days],loadHistory,{immediate:true})
</script>
<template><article class="widget-card"><header class="series-header"><span class="eyebrow">{{ title }}</span><small>{{ vehicle?.name }}</small></header><div v-if="hasData" class="chart"><TimeSeriesChart :series="series" height="100%" /></div><DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&history===null" /></article></template>
<style scoped>.series-header{display:flex;align-items:center;justify-content:space-between;gap:12px}.series-header small{color:var(--muted);font-size:8px}.chart{min-width:0;min-height:120px;flex:1}</style>
