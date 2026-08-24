<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import type { DashboardWidget } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'
import { useDashboardVehicle } from './dashboardContext'

const props = defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const vehicle = useDashboardVehicle(props.widget)
const label = (key: string): string => key.replaceAll('_', ' ')
const health = computed(() => Object.entries(vehicle.value?.state?.device ?? {}).filter(
  ([, value]) => value !== null && value !== undefined && value !== '',
))
</script>

<template><article class="widget-card device-widget"><header><span class="eyebrow">{{ widget.title||t('dashboards.deviceHealth') }}</span><small>{{ vehicle?.name }}</small></header><dl v-if="health.length" class="health"><template v-for="([key,value]) in health" :key="key"><dt>{{ label(key) }}</dt><dd>{{ value }}</dd></template></dl><DashboardWidgetEmpty v-else icon="devices" /></article></template>
<style scoped>.device-widget header{display:flex;align-items:center;justify-content:space-between;gap:12px}.device-widget header .eyebrow{margin:0}.device-widget header small{color:var(--muted);font-size:8px}.health{display:grid;grid-template-columns:1fr auto;gap:8px;margin:13px 0 0}.health div{display:contents}.health dt{color:var(--muted);font-size:10px;text-transform:capitalize}.health dd{margin:0;font:500 10px 'IBM Plex Mono',monospace}</style>
