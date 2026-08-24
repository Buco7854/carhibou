<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, Vehicle } from '../api/types'
const props=defineProps<{widget:DashboardWidget}>();const{t}=useI18n();const vehicle=ref<Vehicle|null>(null);const soc=computed(()=>Number(vehicle.value?.state?.metrics[props.widget.metric??'battery.soc']??0));onMounted(async()=>{if(props.widget.vehicle_id)vehicle.value=await api<Vehicle>(`/vehicles/${props.widget.vehicle_id}`)})
</script>
<template><article class="widget-card items-center"><span class="eyebrow self-start">{{ widget.title||t('dashboard.battery') }}</span><div class="gauge" :style="{'--fill':`${soc*3.6}deg`}"><strong>{{ Math.round(soc) }}%</strong></div><small class="muted">{{ vehicle?.name }}</small></article></template>
<style scoped>.gauge{width:130px;height:130px;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--accent) var(--fill),var(--accent-soft) 0);position:relative}.gauge:after{content:'';position:absolute;inset:10px;border-radius:50%;background:var(--panel)}.gauge strong{z-index:1;font:500 25px 'DM Mono',monospace}</style>
