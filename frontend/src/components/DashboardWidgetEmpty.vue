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
    <AppIcon :name="icon" :size="18" />
    <span>{{ loading ? t('common.loading') : (message || t('dashboards.noData')) }}</span>
  </div>
</template>

<style scoped>
.dashboard-widget-empty{min-width:0;min-height:0;flex:1;display:flex;align-items:center;justify-content:center;gap:8px;padding:14px;color:var(--muted-2);text-align:center}
.dashboard-widget-empty .app-icon{flex:none}
.dashboard-widget-empty span{overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}
</style>
