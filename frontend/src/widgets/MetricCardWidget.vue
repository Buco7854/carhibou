<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { DashboardWidget, Vehicle } from '../api/types'
import { formatMetricNumber, metricLabel, metricReading } from '../vehicleDisplay'
const props = defineProps<{widget:DashboardWidget}>()
const { t } = useI18n()
const vehicle = ref<Vehicle|null>(null)
const reading = computed(() => metricReading(vehicle.value, props.widget.metric ?? ''))
const value = computed(() => {
  if (reading.value.value === null) return '—'
  if (typeof reading.value.value === 'boolean') return t(reading.value.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value.value, reading.value)
})
const unit = computed(() => props.widget.unit ?? reading.value.unit)
onMounted(async()=>{if(props.widget.vehicle_id)vehicle.value=await api<Vehicle>(`/vehicles/${props.widget.vehicle_id}`)})
</script>
<template><article class="widget-card"><span class="eyebrow">{{ widget.title || metricLabel(reading,t) }}</span><div class="metric-value">{{ value }}<span v-if="reading.value!==null&&reading.kind==='number'&&unit" class="metric-unit">{{ unit }}</span></div><small class="muted">{{ vehicle?.name }}</small></article></template>
