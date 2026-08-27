<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
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

async function loadHistory(id?: string): Promise<void> {
  const current = ++request
  history.value = null
  if (!id) return
  const start = new Date(Date.now()-86_400_000)
  const result = await api<History>(`/vehicles/${id}/history?start=${encodeURIComponent(start.toISOString())}&max_points=300`)
  if (current===request) history.value=result
}
watch(() => vehicle.value?.id, loadHistory, { immediate:true })
</script>

<template>
  <article class="widget-card map-widget">
    <header>
      <div><h2>{{ widget.title||t('dashboard.mapAndRoute') }}</h2><span class="mono">{{ positionLabel }}</span></div>
      <small v-if="history">{{ t('dashboard.sampleCount',{count:history.original_count}) }}</small>
    </header>
    <div v-if="hasMapData" class="map-stage"><VehicleMap :position="position" :route="route" /></div>
    <DashboardWidgetEmpty v-else icon="location" :loading="Boolean(vehicle)&&history===null" />
  </article>
</template>

<style scoped>
.map-widget{padding:0}
.map-widget>header{min-height:46px;display:flex;align-items:center;justify-content:space-between;gap:14px;padding:12px 14px 10px;border-bottom:1px solid var(--line)}
.map-widget>header>div{min-width:0}
.map-widget h2{margin:0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);font-weight:500;letter-spacing:.01em;text-overflow:ellipsis;white-space:nowrap}
.map-widget>header span{display:block;margin-top:2px;overflow:hidden;color:var(--text);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.map-widget>header small{flex:none;color:var(--muted-2);font-size:var(--font-caption);white-space:nowrap}
.map-stage{position:relative;min-height:0;flex:1}
.map-stage :deep(.map-frame),.map-stage :deep(.vehicle-map){height:100%;min-height:0}
</style>
