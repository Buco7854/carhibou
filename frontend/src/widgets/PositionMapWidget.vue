<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { loadHistory, rangeStart } from '../api/segments'
import type { DashboardWidget, History } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import VehicleMap from '../components/VehicleMap.vue'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const history = ref<History|null>(null)
let request = 0
const route = computed<Array<[number,number]>>(() => (history.value?.points ?? []).flatMap((point) => point.latitude!==null&&point.longitude!==null ? [[point.latitude,point.longitude] as [number,number]] : []))
const position = computed(() => vehicle.value?.state?.position)
const hasMapData = computed(() => Boolean(position.value) || route.value.length > 0)
const positionLabel = computed(() => position.value ? `${position.value.latitude.toFixed(5)}, ${position.value.longitude.toFixed(5)}` : t('dashboard.noPosition'))

async function loadRoute(): Promise<void> {
  const current = ++request
  history.value = null
  const id = vehicle.value?.id
  if (!id) return
  const result = await loadHistory(id, { start: rangeStart(props.widget.time_range_days ?? 1) })
  if (current===request) history.value=result
}
watch([() => vehicle.value?.id, () => props.widget.time_range_days], loadRoute, { immediate:true })
</script>

<template>
  <article class="widget-card map-widget">
    <div class="widget-head">
      <div><h2>{{ widget.title||t('dashboard.mapAndRoute') }}</h2><span class="mono">{{ positionLabel }}</span></div>
      <small v-if="history">{{ t('dashboard.sampleCount',{count:history.original_count}) }}</small>
    </div>
    <div v-if="hasMapData" class="map-stage"><VehicleMap :position="position" :route="route" /></div>
    <DashboardWidgetEmpty v-else icon="location" :loading="Boolean(vehicle)&&history===null" />
  </article>
</template>

<style scoped>
.map-widget{padding:0}
.map-widget .widget-head{min-height:46px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px 10px;border-bottom:1px solid var(--line)}
.map-widget .widget-head>div{min-width:0}
.map-widget h2{margin:0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);font-weight:500;letter-spacing:.01em;text-overflow:ellipsis;white-space:nowrap}
.map-widget .widget-head span{display:block;margin-top:2px;overflow:hidden;color:var(--text);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.map-widget .widget-head small{flex:none;color:var(--muted-2);font-size:var(--font-caption);white-space:nowrap}
.map-stage{position:relative;min-height:0;flex:1}
.map-stage :deep(.map-frame),.map-stage :deep(.vehicle-map){height:100%;min-height:0}
</style>
