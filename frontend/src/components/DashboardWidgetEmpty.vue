<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import AppIcon from './AppIcon.vue'

withDefaults(defineProps<{
  icon?: string
  loading?: boolean
  message?: string
}>(), {
  icon: 'history',
  loading: false,
  message: '',
})

const { t } = useI18n()
</script>

<template>
  <div class="dashboard-widget-empty" role="status">
    <span class="empty-icon"><AppIcon :name="icon" :size="20" /></span>
    <span>
      <strong>{{ loading ? t('common.loading') : (message || t('dashboards.noData')) }}</strong>
      <small v-if="!loading && !message">{{ t('dashboards.noDataHint') }}</small>
    </span>
  </div>
</template>

<style scoped>
.dashboard-widget-empty{min-width:0;min-height:0;flex:1;display:flex;align-items:center;justify-content:center;gap:11px;padding:14px;color:var(--muted);text-align:left}.empty-icon{width:35px;height:35px;display:grid;place-items:center;flex:none;color:var(--muted);background:var(--panel-2);border:1px solid var(--line);border-radius:8px}.dashboard-widget-empty>span:last-child{min-width:0}.dashboard-widget-empty strong,.dashboard-widget-empty small{display:block}.dashboard-widget-empty strong{color:var(--text);font-size:11px;font-weight:600}.dashboard-widget-empty small{max-width:310px;margin-top:3px;font-size:8px;line-height:1.35}
</style>
