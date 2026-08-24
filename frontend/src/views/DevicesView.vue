<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'

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
function openEnrollment() {
  installCommand.value = ''
  copied.value = false
  if (!vehicles.value.some((vehicle) => vehicle.id === selectedVehicle.value)) {
    selectedVehicle.value = vehicles.value[0]?.id ?? ''
  }
  enrolling.value = true
}
async function createEnrollment() {
  if (!selectedVehicle.value) return
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
    <header class="page-header"><div><span class="eyebrow">{{ t('devices.eyebrow') }}</span><h1>{{ t('devices.title') }}</h1><p>{{ t('devices.summary',{count:devices.length,online:onlineCount,versions:versionCount}) }}</p></div><button class="button" :disabled="!vehicles.length" @click="openEnrollment"><AppIcon name="plus" :size="15" />{{ t('devices.add') }}</button></header>
    <p v-if="error" class="error">{{ error }}</p>
    <AppModal :open="enrolling" :title="t('devices.enrollTitle')" @close="enrolling=false">
      <template #eyebrow><span class="eyebrow">{{ t('devices.add') }}</span></template>
      <form class="enrollment-panel" @submit.prevent="createEnrollment">
        <div class="enrollment-fields">
          <label class="field"><span>{{ t('devices.vehicle') }}</span><AppSelect v-model="selectedVehicle" searchable :search-placeholder="t('vehicles.search')" :no-results-text="t('vehicles.noMatch')"><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
          <label class="field"><span>{{ t('devices.name') }}</span><input v-model="trackerName" class="input" /></label>
        </div>
        <button v-if="!installCommand" class="button" :disabled="!selectedVehicle">{{ t('devices.add') }}</button>
        <div v-else class="command-reveal">
          <p>{{ t('devices.commandHint') }}</p>
          <div class="copy-surface"><pre class="mono">{{ installCommand }}</pre><button class="copy-button" type="button" :title="t('devices.copy')" :aria-label="t('devices.copy')" @click="copy"><AppIcon :name="copied ? 'check' : 'copy'" :size="17" /></button></div>
          <span v-if="copied" class="copy-feedback" role="status">{{ t('devices.copied') }}</span>
        </div>
      </form>
    </AppModal>
    <section class="panel device-roster">
      <header class="roster-heading"><h2>{{ t('devices.roster') }}</h2><span>{{ devices.length }}</span></header>
      <article v-for="device in devices" :key="device.id" class="device-row">
        <div class="device-identity"><span class="device-icon"><AppIcon name="devices" /></span><div><h2>{{ device.name }}</h2><p>{{ vehicleNames[device.vehicle_id] }}</p></div><span :class="['status',{online:device.online&&!device.revoked_at}]">{{ device.revoked_at ? t('devices.revoked') : device.online ? t('common.online') : device.last_seen_at ? t('common.stale') : t('common.never') }}</span></div>
        <dl><div><dt>{{ t('devices.version') }}</dt><dd class="mono">{{ device.agent_version ?? '—' }}</dd></div><div><dt>{{ t('devices.hardware') }}</dt><dd>{{ device.hostname ?? '—' }}</dd></div><div><dt>{{ t('devices.lastSeen') }}</dt><dd>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</dd></div></dl>
        <div v-if="rotatedCredential?.id===device.id" class="credential-reveal"><div><strong>{{ t('devices.credentialReady') }}</strong><button class="icon-button" :aria-label="t('common.close')" @click="rotatedCredential=null"><AppIcon name="close" :size="16" /></button></div><div class="copy-surface"><code>{{ rotatedCredential.credential }}</code><button class="copy-button" :title="t('devices.copyCredential')" :aria-label="t('devices.copyCredential')" @click="copyCredential"><AppIcon :name="copied ? 'check' : 'copy'" :size="17" /></button></div><small>{{ t('devices.credentialHint') }}</small></div>
        <footer><button class="button secondary" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button><button class="icon-button revoke-button" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button></footer>
      </article>
      <div v-if="!devices.length" class="empty">{{ t('devices.noDevices') }}</div>
    </section>
  </div>
</template>

<style scoped>
.enrollment-panel{display:grid;gap:18px}.enrollment-fields{display:grid;gap:14px}.command-reveal{display:grid;gap:10px;padding-top:4px}.command-reveal>p{margin:0;color:var(--muted);font-size:10px;line-height:1.55}.copy-surface{position:relative;min-width:0;display:flex;align-items:center;background:var(--input);border:1px solid var(--line);border-radius:9px}.copy-surface pre,.copy-surface code{min-width:0;display:block;flex:1;overflow:auto;margin:0;padding:14px 50px 14px 14px;color:var(--text);font-size:10px;white-space:pre}.copy-button{position:absolute;top:8px;right:8px;width:34px;height:34px;display:grid;place-items:center;color:var(--muted);background:var(--panel);border:1px solid var(--line-strong);border-radius:7px;cursor:pointer}.copy-button:hover{color:var(--accent);border-color:var(--accent)}.copy-feedback{justify-self:end;color:var(--success);font-size:9px}.device-roster{overflow:hidden}.roster-heading{min-height:60px;display:flex;align-items:center;justify-content:space-between;gap:12px;padding:13px 17px;border-bottom:1px solid var(--line)}.roster-heading h2{margin:0;font-size:16px;font-weight:600}.roster-heading span{color:var(--muted);font-size:10px}.device-row{display:grid;grid-template-columns:minmax(220px,.9fr) minmax(390px,1.5fr) auto;align-items:center;gap:22px;padding:18px 17px;border-bottom:1px solid var(--line)}.device-row:last-child{border-bottom:0}.device-row:hover{background:color-mix(in srgb,var(--panel-2) 38%,transparent)}.device-identity{display:grid;grid-template-columns:38px 1fr auto;align-items:center;gap:10px}.device-icon{width:37px;height:37px;display:grid;place-items:center;color:var(--accent);border:1px solid var(--line);border-radius:7px}.device-identity h2{margin:0;font-size:13px}.device-identity p{margin:3px 0 0;color:var(--muted);font-size:10px}.device-row dl{display:grid;grid-template-columns:repeat(3,1fr);margin:0}.device-row dl>div{min-width:0;padding:2px 15px;border-left:1px solid var(--line)}.device-row dt{color:var(--muted);font-size:9px}.device-row dd{margin:5px 0 0;overflow:hidden;font-size:10px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.device-row footer{display:flex;align-items:center;gap:8px}.device-row footer .button{min-height:35px;font-size:9px}.revoke-button{color:var(--danger);font-size:9px}.credential-reveal{grid-column:1/-1;padding:12px;background:color-mix(in srgb,var(--warning) 7%,var(--panel));border:1px solid color-mix(in srgb,var(--warning) 30%,var(--line));border-radius:7px}.credential-reveal>div:first-child{display:flex;align-items:center;justify-content:space-between}.credential-reveal strong,.credential-reveal small,.credential-reveal code{display:block}.credential-reveal strong{color:var(--warning);font-size:9px}.credential-reveal .copy-surface{margin:8px 0}.credential-reveal code{padding-block:11px;font-size:9px}.credential-reveal small{color:var(--muted);font-size:9px}
@media(max-width:1100px){.device-row{grid-template-columns:1fr auto}.device-row dl{grid-column:1/-1;grid-row:2}.device-row dl>div:first-child{border-left:0}.device-row footer{grid-column:2;grid-row:1}}
@media(max-width:700px){.device-row{display:block}.device-row dl{margin:16px 0}.device-row footer{justify-content:flex-end}.device-identity{grid-template-columns:38px 1fr auto}.device-row dl>div{padding-inline:9px}}
</style>
