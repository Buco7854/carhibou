<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'

interface Device { id:string; vehicle_id:string; name:string; credential_version:number; agent_version:string|null; hostname:string|null; hardware:Record<string,unknown>; online:boolean; last_seen_at:string|null; revoked_at:string|null; created_at:string }
const { t } = useI18n()
const devices = ref<Device[]>([])
const vehicles = ref<Vehicle[]>([])
const enrolling = ref(false)
const selectedVehicle = ref('')
const trackerName = ref('Vehicle tracker')
const installCommand = ref('')
const copied = ref(false)
const error = ref('')
const vehicleNames = computed(() => Object.fromEntries(vehicles.value.map((item) => [item.id, item.name])))

async function load() {
  try { ;[devices.value, vehicles.value] = await Promise.all([api<Device[]>('/devices'), api<Vehicle[]>('/vehicles')]); if (!selectedVehicle.value && vehicles.value[0]) selectedVehicle.value = vehicles.value[0].id }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
async function createEnrollment() {
  const response = await api<{ install_command:string }>(`/vehicles/${selectedVehicle.value}/enrollments`, { method:'POST', body:JSON.stringify({ name:trackerName.value }) })
  installCommand.value = response.install_command
}
async function copy() { await navigator.clipboard.writeText(installCommand.value); copied.value = true; window.setTimeout(() => copied.value = false, 1500) }
async function revoke(id:string) { if (!confirm(t('devices.revoke') + '?')) return; await api(`/devices/${id}/revoke`, { method:'POST' }); await load() }
async function rotate(id:string) { const response = await api<{credential:string}>(`/devices/${id}/rotate`, {method:'POST'}); alert(`New one-time credential:\n${response.credential}`) }
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('devices.eyebrow') }}</span><h1>{{ t('devices.title') }}</h1></div><button class="button" :disabled="!vehicles.length" @click="enrolling=!enrolling">{{ t('devices.add') }}</button></header>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="enrolling" class="panel panel-pad mb-5"><h2 class="mt-0 text-lg">{{ t('devices.enrollTitle') }}</h2><div class="form-grid"><label class="field"><span>{{ t('devices.vehicle') }}</span><select v-model="selectedVehicle" class="select"><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></select></label><label class="field"><span>{{ t('devices.name') }}</span><input v-model="trackerName" class="input" /></label></div><button class="button mt-4" @click="createEnrollment">{{ t('devices.add') }}</button><div v-if="installCommand" class="mt-5"><p class="muted text-xs">{{ t('devices.commandHint') }}</p><pre class="mono overflow-auto rounded-xl p-4 text-xs" style="background:var(--input);border:1px solid var(--line)">{{ installCommand }}</pre><button class="button secondary" @click="copy">{{ copied ? t('devices.copied') : t('devices.copy') }}</button></div></section>
    <section class="panel table-wrap"><table class="table"><thead><tr><th>{{ t('devices.name') }}</th><th>{{ t('devices.vehicle') }}</th><th>{{ t('devices.status') }}</th><th>{{ t('devices.version') }}</th><th>{{ t('devices.lastSeen') }}</th><th>{{ t('devices.actions') }}</th></tr></thead><tbody><tr v-for="device in devices" :key="device.id"><td><strong>{{ device.name }}</strong><small class="muted block">{{ device.hostname }}</small></td><td>{{ vehicleNames[device.vehicle_id] }}</td><td><span :class="['status',{online:device.online}]">{{ device.revoked_at ? t('devices.revoked') : device.online ? t('common.online') : device.last_seen_at ? t('common.stale') : t('common.never') }}</span></td><td class="mono">{{ device.agent_version ?? '—' }}</td><td>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</td><td><button class="button secondary mr-2 text-xs" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button><button class="icon-button text-xs" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button></td></tr><tr v-if="!devices.length"><td colspan="6" class="empty">{{ t('devices.noDevices') }}</td></tr></tbody></table></section>
  </div>
</template>
