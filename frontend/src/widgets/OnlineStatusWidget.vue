<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { trackerStatus, vehicleActivity } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const vehicle = useDashboardVehicle(props.widget)
const { t } = useI18n()

// Two facts, not one. A tracker that has stopped reporting says nothing about
// where the vehicle is or what it is doing, and showing "parked" in that case was
// a claim about the vehicle drawn from evidence about the tracker.
const tracker = computed(() => trackerStatus(vehicle.value))
const activity = computed(() => vehicleActivity(vehicle.value))

const reportedAt = computed(() => {
  const at = vehicle.value?.state?.updated_at
  return at ? new Date(at).toLocaleString() : ''
})
</script>

<template>
  <article class="widget-card status-widget">
    <div class="widget-head"><h2>{{ widget.title||t('dashboard.connection') }}</h2><small>{{ vehicle?.name }}</small></div>
    <template v-if="vehicle?.state">
      <dl class="states">
        <div>
          <dt>{{ t('dashboard.vehicleStatus') }}</dt>
          <dd><span :class="['status', { online: activity === 'driving' || activity === 'charging' }]">{{ t(`dashboard.activity.${activity}`) }}</span></dd>
        </div>
        <div>
          <dt>{{ t('dashboard.trackerStatus') }}</dt>
          <dd><span :class="['status', { online: tracker === 'online' }]">{{ t(`dashboard.tracker.${tracker}`) }}</span></dd>
        </div>
      </dl>
      <small class="status-time">{{ t('dashboard.lastReport', { at: reportedAt }) }}</small>
    </template>
    <DashboardWidgetEmpty v-else icon="devices" />
  </article>
</template>

<style scoped>
.states{display:grid;gap:10px;margin:auto 0 0}
.states>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.states dt{color:var(--muted);font-size:12px}
.states dd{margin:0}
.status-time{margin-top:10px;color:var(--muted);font-size:12px}
</style>
