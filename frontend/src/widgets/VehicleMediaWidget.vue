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
.media-head{margin:0;padding:12px 14px 10px;border-bottom:1px solid var(--line)}
/* Here the heading is the vehicle's name, not a label over a reading, so it
   keeps the text colour the photo caption uses. */
.media-head h2{color:var(--text);font-size:var(--font-body);letter-spacing:0}
.media-widget :deep(.vehicle-media){min-height:0;border:0;border-radius:0}
.media-caption{position:absolute;right:10px;bottom:10px;left:10px;padding:7px 10px;background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:var(--radius);backdrop-filter:blur(8px)}
.media-caption strong,.media-caption small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.media-caption strong{font-size:var(--font-body);font-weight:500}
.media-caption small{margin-top:1px;color:var(--muted);font-size:var(--font-caption)}
</style>
