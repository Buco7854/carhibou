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

<template><article class="widget-card map-widget"><header><div><span>{{ widget.title||t('dashboard.mapAndRoute') }}</span><strong>{{ positionLabel }}</strong></div><small v-if="history">{{ t('dashboard.sampleCount',{count:history.original_count}) }}</small></header><div v-if="hasMapData" class="map-stage"><VehicleMap :position="position" :route="route" /><div v-if="vehicle" class="map-caption"><i :style="{background:vehicle.color||'#315fcf'}" /><strong>{{ vehicle.name }}</strong><small>{{ t('dashboard.latestPosition') }}</small></div></div><DashboardWidgetEmpty v-else icon="location" :loading="Boolean(vehicle)&&history===null" /></article></template>
<style scoped>.map-widget{padding:0}.map-widget>header{min-height:60px;display:flex;align-items:center;justify-content:space-between;gap:15px;padding:11px 15px;border-bottom:1px solid var(--line)}.map-widget>header span,.map-widget>header strong{display:block}.map-widget>header span{color:var(--muted);font-size:9px}.map-widget>header strong{max-width:520px;margin-top:4px;overflow:hidden;font-family:'IBM Plex Mono',monospace;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.map-widget>header small{color:var(--muted);font-size:8px;white-space:nowrap}.map-stage{position:relative;min-height:0;flex:1}.map-stage :deep(.map-frame),.map-stage :deep(.vehicle-map){height:100%;min-height:0}.map-caption{position:absolute;z-index:500;left:13px;bottom:13px;display:grid;grid-template-columns:7px auto;align-items:center;column-gap:7px;padding:8px 10px;background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:7px;box-shadow:var(--shadow-soft);backdrop-filter:blur(8px)}.map-caption i{width:7px;height:7px;grid-row:1/3;border-radius:50%}.map-caption strong{font-size:10px}.map-caption small{margin-top:2px;color:var(--muted);font-size:8px}</style>
