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
    <div v-if="vehicle && !vehicle.photo_url" class="widget-head media-head"><h2>{{ widget.title || vehicle.name }}</h2><small>{{ [vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}</small></div>
    <VehicleMedia v-if="vehicle" :vehicle="vehicle" />
    <DashboardWidgetEmpty v-else icon="vehicle" :message="t('vehicles.noVehicles')" />
    <div v-if="vehicle?.photo_url" class="media-caption">
      <strong>{{ widget.title || vehicle.name }}</strong>
      <small>{{ [vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}</small>
    </div>
  </article>
</template>

<style scoped>
.media-widget{position:relative;padding:0}
.media-head{margin:0;padding:11px 14px 9px;border-bottom:1px solid var(--line)}
.media-widget :deep(.vehicle-media){min-height:0;border:0;border-radius:0}
.media-caption{position:absolute;right:10px;bottom:10px;left:10px;padding:7px 10px;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:var(--radius);backdrop-filter:blur(8px)}
.media-caption strong,.media-caption small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.media-caption strong{font-size:13px;font-weight:500}
.media-caption small{margin-top:1px;color:var(--muted);font-size:12px}
</style>
