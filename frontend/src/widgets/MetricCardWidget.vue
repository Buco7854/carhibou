<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { api } from '../api/client'
import type { DashboardWidget, Vehicle } from '../api/types'
const props = defineProps<{widget:DashboardWidget}>()
const vehicle = ref<Vehicle|null>(null)
const value = computed(() => props.widget.metric ? vehicle.value?.state?.metrics[props.widget.metric] : '—')
onMounted(async()=>{if(props.widget.vehicle_id)vehicle.value=await api<Vehicle>(`/vehicles/${props.widget.vehicle_id}`)})
</script>
<template><article class="widget-card"><span class="eyebrow">{{ widget.title || widget.metric }}</span><div class="metric-value">{{ typeof value==='number' ? Math.round(value*10)/10 : value ?? '—' }}<span class="metric-unit">{{ widget.unit }}</span></div><small class="muted">{{ vehicle?.name }}</small></article></template>
