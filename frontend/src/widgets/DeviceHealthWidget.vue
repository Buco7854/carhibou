<script setup lang="ts">
import { onMounted,ref } from 'vue';import { useI18n } from 'vue-i18n';import { api } from '../api/client';import type { DashboardWidget,Vehicle } from '../api/types';const props=defineProps<{widget:DashboardWidget}>();const{t}=useI18n();const vehicle=ref<Vehicle|null>(null);onMounted(async()=>{if(props.widget.vehicle_id)vehicle.value=await api<Vehicle>(`/vehicles/${props.widget.vehicle_id}`)})
</script>
<template><article class="widget-card"><span class="eyebrow">{{ widget.title||t('dashboards.deviceHealth') }}</span><dl class="health"><template v-for="(value,key) in vehicle?.state?.device" :key="key"><dt>{{ key }}</dt><dd>{{ value }}</dd></template></dl></article></template>
<style scoped>.health{display:grid;grid-template-columns:1fr auto;gap:8px;margin:10px 0}.health dt{color:var(--muted);font-size:11px}.health dd{margin:0;font:500 11px 'DM Mono',monospace}</style>
