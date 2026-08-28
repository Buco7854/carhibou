<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { energySummary, energyTone, metricLabel } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const energy = computed(() => energySummary(vehicle.value))
</script>

<template>
  <article class="widget-card energy-widget">
    <div class="widget-head"><h2>{{ widget.title || metricLabel(energy,t) }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="energy.value!==null">
      <div class="gauge"><strong class="energy-value">{{ Math.round(energy.value) }}</strong><em>{{ energy.unit }}</em></div>
      <i class="level-bar"><b :class="energyTone(energy.value)" :style="{ width:`${energy.progress}%` }" /></i>
    </template>
    <DashboardWidgetEmpty v-else :icon="energy.icon" />
  </article>
</template>

<style scoped>
/* The reading is set at --font-value like every other card's, so the four cards
   of the status row share one type size and their numbers sit on one line. */
.gauge{display:flex;align-items:baseline;margin-top:auto;padding-bottom:9px}
.gauge strong{font-size:var(--font-value);font-weight:500;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.gauge em{margin-left:3px;color:var(--muted);font-size:var(--font-body);font-style:normal}
</style>
