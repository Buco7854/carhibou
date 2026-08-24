<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const vehicle = useDashboardVehicle(props.widget)
const { t } = useI18n()
</script>

<template><article class="widget-card status-widget"><span class="eyebrow">{{ widget.title||t('dashboard.connection') }}</span><template v-if="vehicle?.state"><strong>{{ vehicle.name }}</strong><div :class="['status',{online:vehicle.state.online}]">{{ vehicle.state.online?t('common.online'):t('common.parked') }}</div><small class="muted">{{ new Date(vehicle.state.updated_at).toLocaleString() }}</small></template><DashboardWidgetEmpty v-else icon="devices" /></article></template>
<style scoped>.status-widget{justify-content:space-between}.status-widget strong{font-size:13px}.status-widget>.status{margin-block:5px}</style>
