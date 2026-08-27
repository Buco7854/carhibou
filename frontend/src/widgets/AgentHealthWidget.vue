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
const health = computed(() => Object.entries(vehicle.value?.state?.agent ?? {}).filter(
  ([, value]) => value !== null && value !== undefined && value !== '',
))
</script>

<template>
  <article class="widget-card agent-widget">
    <div class="widget-head"><h2>{{ widget.title||t('dashboards.agentHealth') }}</h2><small>{{ vehicle?.name }}</small></div>
    <dl v-if="health.length" class="health"><template v-for="([key,value]) in health" :key="key"><dt>{{ label(key) }}</dt><dd class="mono">{{ value }}</dd></template></dl>
    <DashboardWidgetEmpty v-else icon="agent" />
  </article>
</template>

<style scoped>
.agent-widget .widget-head{margin-bottom:6px}
.health{display:grid;grid-template-columns:minmax(0,1fr) auto;align-content:start;gap:3px 12px;margin:0;min-height:0;overflow:auto}
.health dt{overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap;text-transform:capitalize}
.health dd{margin:0;font-size:var(--font-caption);text-align:right;font-variant-numeric:tabular-nums}
</style>
