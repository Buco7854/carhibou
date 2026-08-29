<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { energySummary, energyTone, formatAge, isStale, metricLabel, observedAt } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t, locale } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const energy = computed(() => energySummary(vehicle.value))
</script>

<template>
  <article class="widget-card energy-widget">
    <div class="widget-head"><h2>{{ widget.title || metricLabel(energy,t) }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="energy.value!==null">
      <div class="gauge" :class="{ 'is-stale': isStale(energy) }"><strong class="energy-value">{{ Math.round(energy.value) }}</strong><em>{{ energy.unit }}</em></div>
      <i class="level-bar" :class="{ 'is-stale': isStale(energy) }"><b :class="energyTone(energy.value)" :style="{ width:`${energy.progress}%` }" /></i>
      <small v-if="isStale(energy)" class="stale-age">{{ formatAge(observedAt(energy), locale) }}</small>
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
.gauge.is-stale strong{color:var(--muted)}
.level-bar.is-stale{opacity:.55}
.stale-age{margin-top:5px;color:var(--muted-2);font-size:var(--font-micro)}
</style>
