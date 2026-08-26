<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import CadenceFields from '../components/CadenceFields.vue'
import { CADENCE_PRESETS, type Cadence } from '../agentCadence'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'

interface Device { id:string; vehicle_id:string; name:string; credential_version:number; agent_version:string|null; hostname:string|null; hardware:Record<string,unknown>; sampling_seconds:number; upload_seconds:number; parked_sampling_seconds:number; parked_upload_seconds:number; online:boolean; last_seen_at:string|null; last_config_sync_at:string|null; config_version:number; revoked_at:string|null; created_at:string }

const { t } = useI18n()
const devices = ref<Device[]>([])
const vehicles = ref<Vehicle[]>([])
const enrolling = ref(false)
const selectedVehicle = ref('')
const agentName = ref('Vehicle agent')
const enrollmentCadence = ref<Cadence>({ ...CADENCE_PRESETS.find((preset) => preset.key === 'standard')! })
const profileSignals = ref<Record<string,number>>({})
const editing = ref<Device|null>(null)
const draftName = ref('')
const draftCadence = ref<Cadence>({ ...CADENCE_PRESETS.find((preset) => preset.key === 'standard')! })
const saving = ref(false)
const installCommand = ref('')
const copied = ref(false)
const rotatedCredential = ref<{id:string;credential:string}|null>(null)
const error = ref('')
const vehicleNames = computed(() => Object.fromEntries(vehicles.value.map((item) => [item.id, item.name])))
// A profile's signals travel in every sample, so the data estimate is only
// honest if it knows how many the chosen vehicle decodes.
function signalCount(vehicleId:string):number {
  const profile = vehicles.value.find((item) => item.id === vehicleId)?.vehicle_profile
  return profile ? profileSignals.value[profile] ?? 0 : 0
}

async function load() {
  try {
    const [loadedDevices, loadedVehicles, profiles] = await Promise.all([api<Device[]>('/devices'), api<Vehicle[]>('/vehicles'), api<VehicleProfile[]>('/vehicle-profiles')])
    devices.value = loadedDevices
    vehicles.value = loadedVehicles
    profileSignals.value = Object.fromEntries(profiles.map((profile) => [profile.id, profile.definition.signals.length]))
    if (!selectedVehicle.value && vehicles.value[0]) selectedVehicle.value = vehicles.value[0].id
  }
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
  const response = await api<{ install_command:string }>(`/vehicles/${selectedVehicle.value}/enrollments`, { method:'POST', body:JSON.stringify({ name:agentName.value, ...enrollmentCadence.value }) })
  installCommand.value = response.install_command
}
function openSettings(device:Device) {
  error.value = ''
  editing.value = device
  draftName.value = device.name
  draftCadence.value = {
    sampling_seconds:device.sampling_seconds,
    upload_seconds:device.upload_seconds,
    parked_sampling_seconds:device.parked_sampling_seconds,
    parked_upload_seconds:device.parked_upload_seconds,
  }
}
async function saveSettings() {
  if (!editing.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/devices/${editing.value.id}`, { method:'PUT', body:JSON.stringify({ name:draftName.value, ...draftCadence.value }) })
    editing.value = null
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { saving.value = false }
}
async function copy() { await navigator.clipboard.writeText(installCommand.value); copied.value = true; window.setTimeout(() => copied.value = false, 1500) }
async function revoke(id:string) { if (!confirm(t('devices.revokeConfirm'))) return; await api(`/devices/${id}/revoke`, { method:'POST' }); await load() }
async function remove(device:Device) {
  if (!confirm(t('devices.deleteConfirm', { name: device.name }))) return
  await api(`/devices/${device.id}`, { method:'DELETE' })
  await load()
}
async function rotate(id:string) { const response = await api<{credential:string}>(`/devices/${id}/rotate`, {method:'POST'}); rotatedCredential.value={id,credential:response.credential} }
async function copyCredential() { if(!rotatedCredential.value)return;await navigator.clipboard.writeText(rotatedCredential.value.credential);copied.value=true;window.setTimeout(()=>copied.value=false,1500) }
const onlineCount = computed(() => devices.value.filter((device) => device.online && !device.revoked_at).length)
const versionCount = computed(() => new Set(devices.value.flatMap((device) => device.agent_version ? [device.agent_version] : [])).size)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>{{ t('devices.title') }}</h1>
        <p>{{ t('devices.summary',{count:devices.length,online:onlineCount,versions:versionCount}) }}</p>
      </div>
      <div class="header-actions">
        <button class="button" :disabled="!vehicles.length" @click="openEnrollment"><AppIcon name="plus" :size="15" />{{ t('devices.add') }}</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <AppModal :open="enrolling" :title="t('devices.enrollTitle')" @close="enrolling=false">
      <form class="enrollment-panel" @submit.prevent="createEnrollment">
        <div class="enrollment-fields">
          <label class="field"><span>{{ t('devices.vehicle') }}</span><AppSelect v-model="selectedVehicle" searchable :search-placeholder="t('vehicles.search')" :no-results-text="t('vehicles.noMatch')"><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
          <label class="field"><span>{{ t('devices.name') }}</span><input v-model="agentName" class="input" /></label>
          <CadenceFields v-model="enrollmentCadence" :signal-count="signalCount(selectedVehicle)" />
          <p class="field-hint">{{ t('devices.cadenceHint') }}</p>
        </div>
        <button v-if="!installCommand" class="button" :disabled="!selectedVehicle">{{ t('devices.add') }}</button>
        <div v-else class="command-reveal">
          <p class="field-hint">{{ t('devices.commandHint') }}</p>
          <div class="copy-surface"><pre class="mono">{{ installCommand }}</pre><button class="copy-button" type="button" :title="t('devices.copy')" :aria-label="t('devices.copy')" @click="copy"><AppIcon :name="copied ? 'check' : 'copy'" :size="16" /></button></div>
          <span v-if="copied" class="copy-feedback" role="status">{{ t('devices.copied') }}</span>
        </div>
      </form>
    </AppModal>

    <AppModal :open="Boolean(editing)" :title="t('devices.settings')" @close="editing=null">
      <form v-if="editing" class="stack-form" @submit.prevent="saveSettings">
        <label class="field"><span>{{ t('devices.name') }}</span><input v-model="draftName" class="input" required autofocus /></label>
        <CadenceFields v-model="draftCadence" :signal-count="signalCount(editing.vehicle_id)" />
        <p class="field-hint">{{ t('devices.cadenceHint') }}</p>
        <p class="field-hint">{{ t('devices.cadenceApplyHint') }}</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="form-actions">
          <button class="button" :disabled="saving">{{ t('common.save') }}</button>
          <button class="button ghost" type="button" @click="editing=null">{{ t('common.cancel') }}</button>
        </div>
      </form>
    </AppModal>

    <div v-if="devices.length" class="device-list panel">
      <article v-for="device in devices" :key="device.id" class="device-row">
        <div class="device-identity">
          <h2>{{ device.name }}</h2>
          <p>{{ vehicleNames[device.vehicle_id] }}</p>
        </div>
        <span :class="['status',{online:device.online&&!device.revoked_at}]">{{ device.revoked_at ? t('devices.revoked') : device.online ? t('common.online') : device.last_seen_at ? t('common.stale') : t('common.never') }}</span>
        <dl class="device-facts">
          <div><dt>{{ t('devices.version') }}</dt><dd class="mono">{{ device.agent_version ?? '—' }}</dd></div>
          <div><dt>{{ t('devices.hardware') }}</dt><dd>{{ device.hostname ?? '—' }}</dd></div>
          <div><dt>{{ t('devices.lastSeen') }}</dt><dd>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</dd></div>
          <div><dt>{{ t('devices.cadence') }}</dt><dd>{{ t('devices.cadenceValue',{driving:device.sampling_seconds,parked:device.parked_sampling_seconds}) }}</dd></div>
        </dl>
        <div class="device-actions">
          <button class="button secondary" :disabled="!!device.revoked_at" @click="openSettings(device)">{{ t('devices.settings') }}</button>
          <button class="button secondary" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button>
          <button class="link-button danger" type="button" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button>
          <button class="link-button danger" type="button" @click="remove(device)">{{ t('common.delete') }}</button>
        </div>
        <div v-if="rotatedCredential?.id===device.id" class="credential-reveal">
          <div class="credential-heading"><strong>{{ t('devices.credentialReady') }}</strong><button class="icon-button" :aria-label="t('common.close')" @click="rotatedCredential=null"><AppIcon name="close" :size="15" /></button></div>
          <div class="copy-surface"><code class="mono">{{ rotatedCredential.credential }}</code><button class="copy-button" :title="t('devices.copyCredential')" :aria-label="t('devices.copyCredential')" @click="copyCredential"><AppIcon :name="copied ? 'check' : 'copy'" :size="16" /></button></div>
          <small class="field-hint">{{ t('devices.credentialHint') }}</small>
        </div>
      </article>
    </div>
    <div v-else class="empty panel">
      <h2>{{ t('devices.noDevices') }}</h2>
      <p>{{ vehicles.length ? t('devices.noDevicesHint') : t('hooks.createVehicleFirst') }}</p>
    </div>
  </div>
</template>

<style scoped>
.enrollment-panel{display:grid;gap:16px}
.enrollment-fields{display:grid;gap:14px}
.enrollment-panel>.button{justify-self:start}
.command-reveal{display:grid;gap:9px}
.command-reveal>p{margin:0}
.copy-surface{position:relative;min-width:0;display:flex;align-items:center;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius)}
.copy-surface pre,.copy-surface code{min-width:0;display:block;flex:1;overflow:auto;margin:0;padding:11px 44px 11px 12px;color:var(--text);font-size:12px;white-space:pre}
.copy-button{position:absolute;top:6px;right:6px;width:30px;height:30px;display:grid;place-items:center;color:var(--muted);background:var(--panel);border:1px solid var(--line-strong);border-radius:var(--radius);cursor:pointer}
.copy-button:hover{color:var(--text);border-color:var(--muted-2)}
.copy-feedback{color:var(--success);font-size:12px}

.device-list{overflow:hidden}
.device-row{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(420px,1.8fr) auto;align-items:center;gap:20px;padding:14px 16px;border-bottom:1px solid var(--line)}
.device-row:last-child{border-bottom:0}
.device-identity{min-width:0}
.device-identity h2{margin:0;overflow:hidden;font-size:14px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.device-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.stack-form{display:grid;gap:14px}
.stack-form .form-actions{justify-content:flex-end;margin-top:4px}
.device-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:16px;margin:0}
.device-facts>div{min-width:0}
.device-facts dt{color:var(--muted);font-size:12px}
.device-facts dd{margin:2px 0 0;overflow:hidden;font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.device-actions{display:flex;align-items:center;gap:12px}
.credential-reveal{grid-column:1/-1;display:grid;gap:7px;padding:12px;background:var(--warning-soft);border-radius:var(--radius)}
.credential-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.credential-heading strong{color:var(--warning);font-size:12px;font-weight:600}
.credential-reveal .copy-surface{background:var(--panel)}
.credential-reveal code{font-size:12px}

@media(max-width:1100px){
  .device-row{grid-template-columns:minmax(0,1fr) auto;row-gap:14px}
  .device-facts{grid-column:1/-1;grid-row:2}
  .device-actions{grid-column:1/-1;grid-row:3;justify-content:flex-end}
}
@media(max-width:620px){
  .device-facts{grid-template-columns:1fr;gap:6px}
  .device-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .device-facts dd{margin:0}
}
</style>
