<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, Hook, HookExecution } from '../api/types'
import DashboardWidgetEmpty from '../components/DashboardWidgetEmpty.vue'

defineProps<{ widget: DashboardWidget }>()
const { t } = useI18n()
const loaded = ref(false)
const latest = ref<Array<{hook:Hook;execution:HookExecution}>>([])

onMounted(async () => {
  const hooks = await api<Hook[]>('/hooks')
  latest.value = (await Promise.all(hooks.slice(0, 5).map(async (hook) => ({
    hook,
    execution:(await api<HookExecution[]>(`/hooks/${hook.id}/executions?limit=1`))[0],
  })))).filter((row):row is {hook:Hook;execution:HookExecution} => Boolean(row.execution))
  loaded.value = true
})
</script>

<template>
  <article class="widget-card">
    <div class="widget-head"><h2>{{ t('dashboards.hookActivity') }}</h2></div>
    <ul v-if="latest.length" class="activity">
      <li v-for="row in latest" :key="row.execution.id">
        <span :class="['status',{online:row.execution.status==='success'}]">{{ row.execution.status }}</span>
        <strong>{{ row.hook.name }}</strong>
        <small>{{ new Date(row.execution.created_at).toLocaleTimeString() }}</small>
      </li>
    </ul>
    <DashboardWidgetEmpty v-else icon="hooks" :loading="!loaded" :message="loaded?t('hooks.noExecutions'):''" />
  </article>
</template>

<style scoped>
.activity{list-style:none;padding:0;margin:0;display:grid;gap:7px;overflow:auto;min-height:0}
.activity li{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:9px;align-items:center;font-size:13px}
.activity strong{overflow:hidden;font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.activity small{color:var(--muted);font-size:12px}
</style>
