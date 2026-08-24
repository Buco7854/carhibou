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
    <section class="device-overview"><div class="section-heading"><h2>{{ t('devices.overview') }}</h2><span>{{ devices.length }}</span></div><div class="device-overview-grid"><article class="panel"><span><AppIcon name="devices" /></span><div><small>{{ t('devices.total') }}</small><strong>{{ devices.length }}</strong></div></article><article class="panel"><span class="green"><AppIcon name="signal" /></span><div><small>{{ t('devices.connected') }}</small><strong>{{ onlineCount }}</strong></div></article><article class="panel"><span class="blue"><AppIcon name="grid" /></span><div><small>{{ t('devices.versions') }}</small><strong>{{ versionCount }}</strong></div></article></div></section>
    <section class="device-grid">
      <article v-for="device in devices" :key="device.id" class="panel device-card"><header><span class="device-icon"><AppIcon name="devices" /></span><div><h2>{{ device.name }}</h2><p>{{ vehicleNames[device.vehicle_id] }}</p></div><span :class="['status',{online:device.online&&!device.revoked_at}]">{{ device.revoked_at ? t('devices.revoked') : device.online ? t('common.online') : device.last_seen_at ? t('common.stale') : t('common.never') }}</span></header><dl><div><dt>{{ t('devices.version') }}</dt><dd class="mono">{{ device.agent_version ?? '—' }}</dd></div><div><dt>{{ t('devices.hardware') }}</dt><dd>{{ device.hostname ?? '—' }}</dd></div><div><dt>{{ t('devices.lastSeen') }}</dt><dd>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</dd></div></dl><div v-if="rotatedCredential?.id===device.id" class="credential-reveal"><div><strong>{{ t('devices.credentialReady') }}</strong><button class="icon-button" @click="rotatedCredential=null">×</button></div><code>{{ rotatedCredential.credential }}</code><small>{{ t('devices.credentialHint') }}</small><button class="button secondary" @click="copyCredential">{{ copied?t('devices.copied'):t('devices.copy') }}</button></div><footer><button class="button secondary" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button><button class="icon-button revoke-button" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button></footer></article>
      <div v-if="!devices.length" class="panel empty device-empty">{{ t('devices.noDevices') }}</div>
    </section>
  </div>
</template>

<style scoped>
.enrollment-panel{padding:19px;margin-bottom:16px}.enrollment-panel>header,.section-heading,.device-card>header{display:flex;align-items:center;justify-content:space-between;gap:12px}.enrollment-panel>header{margin-bottom:16px}.enrollment-panel h2,.section-heading h2{margin:0;font-size:15px;font-weight:600}.device-overview{margin-bottom:14px}.section-heading{margin-bottom:10px}.section-heading>span{color:var(--muted);font-size:9px}.device-overview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.device-overview-grid article{min-height:96px;display:grid;grid-template-columns:42px 1fr;align-items:center;gap:11px;padding:14px}.device-overview-grid article>span{width:40px;height:40px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:10px}.device-overview-grid article>span.green{color:var(--success);background:var(--success-soft)}.device-overview-grid article>span.blue{color:var(--blue);background:var(--blue-soft)}.device-overview-grid small,.device-overview-grid strong{display:block}.device-overview-grid small{color:var(--muted);font-size:8px}.device-overview-grid strong{margin-top:4px;font-size:24px;font-weight:500}.device-grid{display:grid;grid-template-columns:repeat(3,minmax(280px,1fr));gap:10px}.device-card{padding:14px}.device-card>header{display:grid;grid-template-columns:37px 1fr auto;padding-bottom:12px;border-bottom:1px solid var(--line)}.device-icon{width:36px;height:36px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:9px}.device-card h2{margin:0;font-size:11px;font-weight:600}.device-card header p{margin:3px 0 0;color:var(--muted);font-size:8px}.device-card dl{margin:0}.device-card dl>div{display:grid;grid-template-columns:95px minmax(0,1fr);gap:8px;padding:9px 1px;border-bottom:1px solid var(--line);font-size:8px}.device-card dt{color:var(--muted)}.device-card dd{margin:0;overflow:hidden;text-align:right;text-overflow:ellipsis;white-space:nowrap}.device-card footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding-top:12px}.device-card footer .button{min-height:33px;font-size:8px}.revoke-button{color:var(--danger);font-size:8px}.credential-reveal{margin-top:11px;padding:10px;background:color-mix(in srgb,var(--warning) 7%,var(--panel));border:1px solid color-mix(in srgb,var(--warning) 30%,var(--line));border-radius:9px}.credential-reveal>div{display:flex;align-items:center;justify-content:space-between}.credential-reveal strong,.credential-reveal small,.credential-reveal code{display:block}.credential-reveal strong{color:var(--warning);font-size:8px}.credential-reveal code{overflow:auto;margin:8px 0;padding:7px;background:var(--input);border-radius:7px;font-size:8px}.credential-reveal small{color:var(--muted);font-size:8px}.credential-reveal .button{min-height:30px;margin-top:8px;font-size:8px}.device-empty{grid-column:1/-1}
@media(max-width:1250px){.device-grid{grid-template-columns:repeat(2,minmax(280px,1fr))}}
@media(max-width:700px){.device-overview-grid,.device-grid{grid-template-columns:1fr}}
</style>
