<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import VehicleMedia from '../components/VehicleMedia.vue'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
</script>

<template>
  <article class="widget-card media-widget">
    <VehicleMedia v-if="vehicle" :vehicle="vehicle" />
    <DashboardWidgetEmpty v-else icon="vehicle" :message="t('vehicles.noVehicles')" />
    <div v-if="vehicle" class="media-caption"><strong>{{ widget.title || vehicle.name }}</strong><small>{{ [vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}</small></div>
  </article>
</template>

<style scoped>
.media-widget{position:relative;padding:0}.media-widget :deep(.vehicle-media){min-height:0;border:0;border-radius:0}.media-caption{position:absolute;right:12px;bottom:12px;left:12px;padding:9px 11px;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:7px;backdrop-filter:blur(8px)}.media-caption strong,.media-caption small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.media-caption strong{font-size:11px}.media-caption small{margin-top:3px;color:var(--muted);font-size:8px}
</style>
