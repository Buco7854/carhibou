<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import AppHelp from '../components/AppHelp.vue'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { formatInstant, agentStatus, vehicleActivity } from '../vehicleDisplay'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const vehicle = useDashboardVehicle(props.widget)
const { t } = useI18n()

// Two facts, not one. An agent that has stopped reporting says nothing about
// where the vehicle is or what it is doing, and showing "parked" in that case was
// a claim about the vehicle drawn from evidence about the agent.
const agent = computed(() => agentStatus(vehicle.value))
const activity = computed(() => vehicleActivity(vehicle.value))

const reportedAt = computed(() => {
  const at = vehicle.value?.state?.updated_at
  return formatInstant(at)
})
</script>

<template>
  <article class="widget-card status-widget">
    <div class="widget-head">
      <h2>{{ widget.title||t('dashboard.connection') }}<AppHelp :label="t('dashboard.freshnessHelpLabel')"><span>{{ t('dashboard.freshnessHelp') }}</span></AppHelp></h2>
      <small>{{ vehicle?.name }}</small>
    </div>
    <template v-if="vehicle?.state">
      <dl class="states">
        <div>
          <dt>{{ t('dashboard.vehicleStatus') }}</dt>
          <dd><span :class="['status', { online: activity === 'driving' || activity === 'charging' }]">{{ t(`dashboard.activity.${activity}`) }}</span></dd>
        </div>
        <div>
          <dt>{{ t('dashboard.agentStatus') }}</dt>
          <dd><span :class="['status', { online: agent === 'online' }]">{{ t(`dashboard.agent.${agent}`) }}</span></dd>
        </div>
      </dl>
      <small class="status-time">{{ t('dashboard.lastReport', { at: reportedAt }) }}</small>
    </template>
    <DashboardWidgetEmpty v-else icon="agent" />
  </article>
</template>

<style scoped>
.states{display:grid;gap:10px;margin:auto 0 0}
.states>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.states dt{color:var(--muted);font-size:var(--font-caption)}
.states dd{margin:0}
.widget-head h2{display:flex;align-items:center;gap:4px}
.status-time{margin-top:10px;color:var(--muted-2);font-size:var(--font-caption)}
</style>
