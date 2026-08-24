<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const showForm = ref(false)
const error = ref('')
const form = ref({ name: '', manufacturer: 'Citroën', model: 'C-Zero', year: new Date().getFullYear(), propulsion_type: 'electric', battery_nominal_capacity_kwh: 16, vehicle_profile: 'citroen-c-zero-v1', color: '#65e0ad' })
async function load() { vehicles.value = await api<Vehicle[]>('/vehicles') }
async function create() {
  error.value = ''
  try { await api('/vehicles', { method: 'POST', body: JSON.stringify(form.value) }); showForm.value = false; await load() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('vehicles.garage') }}</span><h1>{{ t('vehicles.title') }}</h1></div><button class="button" @click="showForm = !showForm">{{ showForm ? t('common.close') : t('vehicles.add') }}</button></header>
    <form v-if="showForm" class="panel panel-pad vehicle-form" @submit.prevent="create">
      <div class="form-grid">
        <div class="field"><label>{{ t('vehicles.name') }}</label><input v-model="form.name" class="input" required /></div>
        <div class="field"><label>{{ t('vehicles.manufacturer') }}</label><input v-model="form.manufacturer" class="input" /></div>
        <div class="field"><label>{{ t('vehicles.model') }}</label><input v-model="form.model" class="input" /></div>
        <div class="field"><label>{{ t('vehicles.year') }}</label><input v-model="form.year" class="input" type="number" min="1886" max="2200" /></div>
        <div class="field"><label>{{ t('vehicles.propulsion') }}</label><select v-model="form.propulsion_type" class="select"><option>electric</option><option>hybrid</option><option>petrol</option><option>diesel</option><option>unknown</option></select></div>
        <div class="field"><label>{{ t('vehicles.capacity') }}</label><input v-model="form.battery_nominal_capacity_kwh" class="input" type="number" step=".1" min="1" /></div>
        <div class="field"><label>{{ t('vehicles.profile') }}</label><select v-model="form.vehicle_profile" class="select"><option value="citroen-c-zero-v1">{{ t('vehicles.profileExperimental') }}</option><option :value="null">{{ t('vehicles.none') }}</option></select></div>
        <div class="field"><label>{{ t('vehicles.color') }}</label><input v-model="form.color" class="input" type="color" /></div>
      </div><p v-if="error" class="error">{{ error }}</p><div class="form-actions"><button class="button">{{ t('vehicles.create') }}</button></div>
    </form>
    <div class="vehicle-list">
      <article v-for="vehicle in vehicles" :key="vehicle.id" class="panel vehicle-card">
        <div class="vehicle-icon" :style="{ color: vehicle.color, borderColor: vehicle.color }">◇</div>
        <div><div class="vehicle-card-title"><h2>{{ vehicle.name }}</h2><span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t('common.online') : t('common.parked') }}</span></div><p>{{ vehicle.manufacturer }} {{ vehicle.model }} · {{ vehicle.year ?? t('vehicles.yearUnknown') }}</p><div class="card-metrics"><span><small>SOC</small>{{ vehicle.state?.metrics['battery.soc'] ?? '—' }}%</span><span><small>{{ t('vehicles.speed') }}</small>{{ vehicle.state?.position?.speed ?? '—' }} km/h</span><span><small>{{ t('common.updated') }}</small>{{ vehicle.state ? new Date(vehicle.state.updated_at).toLocaleString() : t('common.never') }}</span></div></div>
        <div class="card-actions"><RouterLink class="button secondary" :to="`/vehicles/${vehicle.id}/history`">{{ t('vehicles.history') }}</RouterLink><RouterLink class="button" to="/devices">{{ t('vehicles.tracker') }}</RouterLink></div>
      </article>
      <div v-if="!vehicles.length && !showForm" class="panel empty"><h2>{{ t('vehicles.noVehicles') }}</h2><p>{{ t('vehicles.noVehiclesHint') }}</p></div>
    </div>
  </div>
</template>

<style scoped>
.vehicle-form{margin-bottom:20px}.vehicle-list{display:grid;gap:14px}.vehicle-card{padding:20px;display:grid;grid-template-columns:70px 1fr auto;gap:18px;align-items:center}.vehicle-icon{width:64px;height:64px;border:1px solid;border-radius:18px;display:grid;place-items:center;font-size:34px;background:rgba(101,224,173,.04)}.vehicle-card-title{display:flex;align-items:center;gap:15px}.vehicle-card h2{margin:0;font-size:18px}.vehicle-card p{margin:4px 0 14px;color:var(--muted);font-size:12px}.card-metrics{display:flex;gap:28px;font:500 12px 'DM Mono',monospace}.card-metrics small{display:block;color:var(--muted);font:600 9px Inter,sans-serif;text-transform:uppercase;margin-bottom:4px}.card-actions{display:flex;gap:8px}.card-actions a{text-decoration:none;font-size:11px}@media(max-width:700px){.vehicle-card{grid-template-columns:50px 1fr}.vehicle-icon{width:48px;height:48px}.card-actions{grid-column:1/-1}.card-metrics{gap:13px;flex-wrap:wrap}}
</style>
