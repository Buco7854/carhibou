<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const vehicle = useDashboardVehicle(props.widget)
const { t } = useI18n()
</script>

<template>
  <article class="widget-card status-widget">
    <div class="widget-head"><h2>{{ widget.title||t('dashboard.connection') }}</h2></div>
    <template v-if="vehicle?.state">
      <strong class="status-name">{{ vehicle.name }}</strong>
      <div :class="['status',{online:vehicle.state.online}]">{{ vehicle.state.online?t('common.online'):t('common.parked') }}</div>
      <small class="status-time">{{ new Date(vehicle.state.updated_at).toLocaleString() }}</small>
    </template>
    <DashboardWidgetEmpty v-else icon="devices" />
  </article>
</template>

<style scoped>
.status-name{margin-top:auto;font-size:14px;font-weight:500}
.status-widget>.status{margin:7px 0}
.status-time{color:var(--muted);font-size:12px}
</style>
