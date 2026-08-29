<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { loadHistory, rangeStart } from '../api/segments'
import type { DashboardWidget, History } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import { historyValue, metricDefinition, metricLabel } from '../vehicleDisplay'
import { useDashboardRuntime, useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const runtime = useDashboardRuntime()
const vehicle = useDashboardVehicle(props.widget)
const history = ref<History|null>(null)
let request=0
// One series per key: a stored duplicate would otherwise draw the same line
// twice and repeat its name in the legend.
const chosen = computed(() => [...new Set(props.widget.metrics ?? [])])
const title = computed(() => props.widget.title || chosen.value.map((metric) => metricLabel(metricDefinition(metric), t)).join(' · ') || t('dashboards.multiSeries'))
const series = computed(() => chosen.value.map((metric) => ({name:metricLabel(metricDefinition(metric),t),unit:metricDefinition(metric).unit,data:(history.value?.points??[]).flatMap((point) => {const value=historyValue(point,metric);return value!==null?[[point.recorded_at,value] as [string,number]]:[]})})))
const hasData = computed(() => series.value.some((row) => row.data.length > 0))
async function loadSeries():Promise<void>{const current=++request;history.value=null;const id=vehicle.value?.id;if(!id)return;const result=await loadHistory(id, { start: rangeStart(props.widget.time_range_days ?? 1), maxPoints: 500 });if(current===request)history.value=result}
watch([() => vehicle.value?.id, () => props.widget.time_range_days, runtime.dataVersion],loadSeries,{immediate:true})
</script>
<template>
  <article class="widget-card">
    <div class="widget-head"><h2>{{ title }}</h2><small>{{ vehicle?.name }}</small></div>
    <div v-if="hasData" class="chart"><TimeSeriesChart :series="series" height="100%" /></div>
    <DashboardWidgetEmpty v-else icon="history" :loading="Boolean(vehicle)&&history===null" />
  </article>
</template>

<style scoped>
.chart{min-width:0;min-height:110px;flex:1}
</style>
