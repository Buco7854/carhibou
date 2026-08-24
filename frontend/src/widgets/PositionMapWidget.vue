<script setup lang="ts">
import { onMounted, ref } from 'vue';import { api } from '../api/client';import type { DashboardWidget,Vehicle } from '../api/types';import VehicleMap from '../components/VehicleMap.vue';const props=defineProps<{widget:DashboardWidget}>();const vehicle=ref<Vehicle|null>(null);onMounted(async()=>{if(props.widget.vehicle_id)vehicle.value=await api<Vehicle>(`/vehicles/${props.widget.vehicle_id}`)})
</script>
<template><article class="widget-card !p-0 overflow-hidden"><div class="absolute z-500 m-3 rounded-lg px-3 py-2 text-xs font-bold" style="background:var(--panel)">{{ widget.title||vehicle?.name }}</div><VehicleMap :position="vehicle?.state?.position" /></article></template>
