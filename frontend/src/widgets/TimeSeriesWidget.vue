<script setup lang="ts">
import { computed,onMounted,ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget,History } from '../api/types'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { metricDefinition,metricLabel } from '../vehicleDisplay'

const props=defineProps<{widget:DashboardWidget}>()
const { t }=useI18n()
const history=ref<History|null>(null)
const definition=computed(()=>metricDefinition(props.widget.metric??''))
const series=computed(()=>[{name:props.widget.title||metricLabel(definition.value,t),unit:props.widget.unit??definition.value.unit,data:(history.value?.points??[]).flatMap(p=>{const metric=props.widget.metric??'';const v=metric==='vehicle.speed'?p.speed:p.metrics[metric];return typeof v==='number'?[[p.recorded_at,v] as [string,number]]:[]})}])
onMounted(async()=>{if(props.widget.vehicle_id){const start=new Date(Date.now()-(props.widget.time_range_days??1)*86_400_000);history.value=await api<History>(`/vehicles/${props.widget.vehicle_id}/history?start=${encodeURIComponent(start.toISOString())}&max_points=300`)}})
</script>
<template><article class="widget-card"><span class="eyebrow">{{ widget.title||metricLabel(definition,t) }}</span><TimeSeriesChart :series="series" :height="190" /></article></template>
