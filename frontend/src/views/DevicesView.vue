<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'

interface Device { id:string; vehicle_id:string; name:string; credential_version:number; agent_version:string|null; hostname:string|null; hardware:Record<string,unknown>; online:boolean; last_seen_at:string|null; revoked_at:string|null; created_at:string }
const { t } = useI18n()
const devices = ref<Device[]>([])
const vehicles = ref<Vehicle[]>([])
const enrolling = ref(false)
const selectedVehicle = ref('')
const trackerName = ref('Vehicle tracker')
const installCommand = ref('')
const copied = ref(false)
const rotatedCredential = ref<{id:string;credential:string}|null>(null)
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
async function rotate(id:string) { const response = await api<{credential:string}>(`/devices/${id}/rotate`, {method:'POST'}); rotatedCredential.value={id,credential:response.credential} }
async function copyCredential() { if(!rotatedCredential.value)return;await navigator.clipboard.writeText(rotatedCredential.value.credential);copied.value=true;window.setTimeout(()=>copied.value=false,1500) }
const onlineCount = computed(() => devices.value.filter((device) => device.online && !device.revoked_at).length)
const versionCount = computed(() => new Set(devices.value.flatMap((device) => device.agent_version ? [device.agent_version] : [])).size)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('devices.eyebrow') }}</span><h1>{{ t('devices.title') }}</h1></div><button class="button" :disabled="!vehicles.length" @click="enrolling=!enrolling">{{ t('devices.add') }}</button></header>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="enrolling" class="panel enrollment-panel"><header><div><span class="eyebrow">{{ t('devices.add') }}</span><h2>{{ t('devices.enrollTitle') }}</h2></div><button class="icon-button" :aria-label="t('common.close')" @click="enrolling=false">×</button></header><div class="form-grid"><label class="field"><span>{{ t('devices.vehicle') }}</span><select v-model="selectedVehicle" class="select"><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></select></label><label class="field"><span>{{ t('devices.name') }}</span><input v-model="trackerName" class="input" /></label></div><button class="button mt-4" @click="createEnrollment">{{ t('devices.add') }}</button><div v-if="installCommand" class="mt-5"><p class="muted text-xs">{{ t('devices.commandHint') }}</p><pre class="mono overflow-auto rounded-xl p-4 text-xs" style="background:var(--input);border:1px solid var(--line)">{{ installCommand }}</pre><button class="button secondary" @click="copy">{{ copied ? t('devices.copied') : t('devices.copy') }}</button></div></section>
    <section class="device-register"><div><small>{{ t('devices.total') }}</small><strong>{{ devices.length }}</strong></div><div><small>{{ t('devices.connected') }}</small><strong>{{ onlineCount }}</strong></div><div><small>{{ t('devices.versions') }}</small><strong>{{ versionCount }}</strong></div><p>{{ t('devices.commandHint') }}</p></section>
    <section class="device-grid">
      <article v-for="device in devices" :key="device.id" class="panel device-card"><header><span class="device-icon"><AppIcon name="devices" /></span><div><h2>{{ device.name }}</h2><p>{{ vehicleNames[device.vehicle_id] }}</p></div><span :class="['status',{online:device.online&&!device.revoked_at}]">{{ device.revoked_at ? t('devices.revoked') : device.online ? t('common.online') : device.last_seen_at ? t('common.stale') : t('common.never') }}</span></header><dl><div><dt>{{ t('devices.version') }}</dt><dd class="mono">{{ device.agent_version ?? '—' }}</dd></div><div><dt>{{ t('devices.hardware') }}</dt><dd>{{ device.hostname ?? '—' }}</dd></div><div><dt>{{ t('devices.lastSeen') }}</dt><dd>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</dd></div></dl><div v-if="rotatedCredential?.id===device.id" class="credential-reveal"><div><strong>{{ t('devices.credentialReady') }}</strong><button class="icon-button" @click="rotatedCredential=null">×</button></div><code>{{ rotatedCredential.credential }}</code><small>{{ t('devices.credentialHint') }}</small><button class="button secondary" @click="copyCredential">{{ copied?t('devices.copied'):t('devices.copy') }}</button></div><footer><button class="button secondary" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button><button class="icon-button revoke-button" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button></footer></article>
      <div v-if="!devices.length" class="panel empty device-empty">{{ t('devices.noDevices') }}</div>
    </section>
  </div>
</template>

<style scoped>
.enrollment-panel{padding:19px;margin-bottom:17px}.enrollment-panel>header,.device-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.enrollment-panel>header{margin-bottom:17px}.enrollment-panel h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:25px;text-transform:uppercase}.device-register{min-height:71px;display:grid;grid-template-columns:125px 125px 125px 1fr;align-items:center;margin-bottom:14px;border-block:1px solid var(--line-strong)}.device-register>div{padding:10px 18px;border-right:1px solid var(--line)}.device-register small,.device-register strong{display:block}.device-register small{color:var(--muted);font:500 7px "IBM Plex Mono",monospace;text-transform:uppercase}.device-register strong{margin-top:3px;font:500 27px "Barlow Condensed",sans-serif}.device-register p{justify-self:end;max-width:470px;margin:0;color:var(--muted);font:400 7px/1.5 "IBM Plex Mono",monospace;text-align:right;text-transform:uppercase}.device-grid{display:grid;grid-template-columns:repeat(3,minmax(280px,1fr));gap:11px}.device-card{padding:15px;border-radius:5px}.device-card>header{display:grid;grid-template-columns:38px 1fr auto;padding-bottom:13px;border-bottom:1px solid var(--line)}.device-icon{width:37px;height:37px;display:grid;place-items:center;color:var(--petrol);background:var(--petrol-soft);border-left:3px solid var(--signal)}.device-card h2{margin:0;font:600 17px "Barlow Condensed",sans-serif;text-transform:uppercase}.device-card header p{margin:4px 0 0;color:var(--muted);font:400 7px "IBM Plex Mono",monospace}.device-card dl{margin:0}.device-card dl>div{display:grid;grid-template-columns:95px minmax(0,1fr);gap:8px;padding:10px 1px;border-bottom:1px solid var(--line);font-size:9px}.device-card dt{color:var(--muted);font:400 7px "IBM Plex Mono",monospace;text-transform:uppercase}.device-card dd{margin:0;overflow:hidden;text-align:right;text-overflow:ellipsis;white-space:nowrap}.device-card footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:13px}.device-card footer .button{min-height:34px;font-size:7px}.revoke-button{color:var(--danger);font-size:8px}.credential-reveal{margin-top:12px;padding:11px;border:1px solid color-mix(in srgb,var(--warning) 30%,var(--line));border-radius:3px;background:color-mix(in srgb,var(--warning) 7%,var(--panel))}.credential-reveal>div{display:flex;align-items:center;justify-content:space-between}.credential-reveal strong,.credential-reveal small,.credential-reveal code{display:block}.credential-reveal strong{color:var(--warning);font-size:9px}.credential-reveal code{overflow:auto;margin:8px 0;padding:7px;background:var(--input);font-size:8px}.credential-reveal small{color:var(--muted);font-size:8px}.credential-reveal .button{min-height:30px;margin-top:8px;font-size:7px}.device-empty{grid-column:1/-1}
@media(max-width:1250px){.device-grid{grid-template-columns:repeat(2,minmax(280px,1fr))}}
@media(max-width:700px){.device-register{grid-template-columns:repeat(3,1fr)}.device-register p{display:none}.device-grid{grid-template-columns:1fr}}
</style>
