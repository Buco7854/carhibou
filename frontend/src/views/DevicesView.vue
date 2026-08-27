<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import CadenceFields from '../components/CadenceFields.vue'
import { CADENCE_PRESETS, type Cadence } from '../agentCadence'
import { canOperate, isAdmin, operableVehicles } from '../access'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'

type SetupStepKind = 'command'|'value'|'link'|'manual'
interface AgentImplementation { id:string; name:string; hardware:string; protocol_version:number; setup_kind:'command'|'guided'; docs_url:string }
interface SetupStep { kind:SetupStepKind; text:string; command:string; value:string; url:string }
interface Enrollment { token:string; expires_at:string; setup_steps:SetupStep[] }
interface Device { id:string; vehicle_id:string; name:string; credential_version:number; implementation_id:string; protocol_version:number; agent_version:string; compatibility:'compatible'|'incompatible'; hostname:string|null; hardware:Record<string,unknown>; sampling_seconds:number; upload_seconds:number; parked_sampling_seconds:number; parked_upload_seconds:number; online:boolean; last_seen_at:string|null; last_config_sync_at:string|null; config_version:number; revoked_at:string|null; created_at:string }

const BUNDLED_IMPLEMENTATION = 'carhibou.go'
const CUSTOM_IMPLEMENTATION = 'custom'
// The protocol reference is served by the API itself, so the author of an
// independent agent can reach it from this origin before any token exists.
const PROTOCOL_DOCS_URL = '/api/docs'

// A preset carries its own key alongside the four intervals, and both the
// enrollment and settings schemas reject a field they do not declare.
function presetCadence(key:string):Cadence {
  const { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds } = CADENCE_PRESETS.find((preset) => preset.key === key)!
  return { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds }
}

const { t } = useI18n()
const devices = ref<Device[]>([])
const vehicles = ref<Vehicle[]>([])
const implementations = ref<AgentImplementation[]>([])
const enrolling = ref(false)
const selectedVehicle = ref('')
const selectedImplementation = ref('')
const agentName = ref('Vehicle agent')
const enrollmentCadence = ref<Cadence>(presetCadence('standard'))
const profileSignals = ref<Record<string,number>>({})
const editing = ref<Device|null>(null)
const draftName = ref('')
const draftCadence = ref<Cadence>(presetCadence('standard'))
const saving = ref(false)
const creating = ref(false)
const enrollment = ref<Enrollment|null>(null)
// The token is bound to the implementation it was minted for, so the reveal
// describes that choice rather than whatever the picker holds afterwards.
const mintedFor = ref<AgentImplementation|null>(null)
const enrollmentError = ref('')
const copiedKey = ref('')
const rotatedCredential = ref<{id:string;credential:string}|null>(null)
const error = ref('')
const vehicleNames = computed(() => Object.fromEntries(vehicles.value.map((item) => [item.id, item.name])))
// Enrollment creates a credential for the vehicle, so the choice is limited to
// vehicles the user may operate; a device row follows its vehicle's level.
const enrollableVehicles = computed(() => operableVehicles(vehicles.value))
const chosenImplementation = computed(() => implementations.value.find((item) => item.id === selectedImplementation.value))
const chosenOrigin = computed(() => selectedImplementation.value === BUNDLED_IMPLEMENTATION ? t('devices.bundledTag') : selectedImplementation.value === CUSTOM_IMPLEMENTATION ? t('devices.customTag') : '')
const chosenDocsUrl = computed(() => selectedImplementation.value === CUSTOM_IMPLEMENTATION ? PROTOCOL_DOCS_URL : chosenImplementation.value?.docs_url ?? '')
function canOperateDevice(device: Device): boolean {
  return canOperate(vehicles.value.find((item) => item.id === device.vehicle_id))
}
function implementationName(id:string):string {
  return implementations.value.find((item) => item.id === id)?.name ?? id
}
// A manifest may leave a step's text empty when the payload speaks for itself,
// so every kind still needs a sentence a reader can act on.
function stepText(step:SetupStep):string { return step.text || t(`devices.stepDefaults.${step.kind}`) }
// A profile's signals travel in every sample, so the data estimate is only
// honest if it knows how many the chosen vehicle decodes.
function signalCount(vehicleId:string):number {
  const profile = vehicles.value.find((item) => item.id === vehicleId)?.vehicle_profile
  return profile ? profileSignals.value[profile] ?? 0 : 0
}

async function load() {
  try {
    const [loadedDevices, loadedVehicles, profiles, catalog] = await Promise.all([api<Device[]>('/devices'), api<Vehicle[]>('/vehicles'), api<VehicleProfile[]>('/vehicle-profiles'), api<AgentImplementation[]>('/agent-implementations')])
    devices.value = loadedDevices
    vehicles.value = loadedVehicles
    implementations.value = catalog
    profileSignals.value = Object.fromEntries(profiles.map((profile) => [profile.id, profile.definition.signals.length]))
    if (!selectedVehicle.value && enrollableVehicles.value[0]) selectedVehicle.value = enrollableVehicles.value[0].id
    if (!catalog.some((item) => item.id === selectedImplementation.value)) {
      selectedImplementation.value = catalog.find((item) => item.id === BUNDLED_IMPLEMENTATION)?.id ?? catalog[0]?.id ?? ''
    }
  }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
function openEnrollment() {
  enrollment.value = null
  mintedFor.value = null
  enrollmentError.value = ''
  copiedKey.value = ''
  if (!enrollableVehicles.value.some((vehicle) => vehicle.id === selectedVehicle.value)) {
    selectedVehicle.value = enrollableVehicles.value[0]?.id ?? ''
  }
  if (!implementations.value.some((item) => item.id === selectedImplementation.value)) {
    selectedImplementation.value = implementations.value.find((item) => item.id === BUNDLED_IMPLEMENTATION)?.id ?? implementations.value[0]?.id ?? ''
  }
  enrolling.value = true
}
async function createEnrollment() {
  if (!selectedVehicle.value || !selectedImplementation.value || enrollment.value || creating.value) return
  creating.value = true
  enrollmentError.value = ''
  try {
    enrollment.value = await api<Enrollment>(`/vehicles/${selectedVehicle.value}/enrollments`, { method:'POST', body:JSON.stringify({ implementation_id:selectedImplementation.value, name:agentName.value, ...enrollmentCadence.value }) })
    mintedFor.value = chosenImplementation.value ?? null
  } catch (reason) { enrollmentError.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { creating.value = false }
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
async function copy(key:string, value:string) {
  if (!value) return
  await navigator.clipboard.writeText(value)
  copiedKey.value = key
  window.setTimeout(() => { if (copiedKey.value === key) copiedKey.value = '' }, 1500)
}
async function revoke(id:string) { if (!confirm(t('devices.revokeConfirm'))) return; await api(`/devices/${id}/revoke`, { method:'POST' }); await load() }
async function remove(device:Device) {
  if (!confirm(t('devices.deleteConfirm', { name: device.name }))) return
  await api(`/devices/${device.id}`, { method:'DELETE' })
  await load()
}
async function rotate(id:string) { const response = await api<{credential:string}>(`/devices/${id}/rotate`, {method:'POST'}); rotatedCredential.value={id,credential:response.credential} }
const onlineCount = computed(() => devices.value.filter((device) => device.online && !device.revoked_at).length)
// Agent versions belong to their own implementations and are never comparable
// across them, so the roster counts protocol incompatibility instead.
const incompatibleCount = computed(() => devices.value.filter((device) => device.compatibility === 'incompatible').length)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>{{ t('devices.title') }}</h1>
        <p>{{ t('devices.summary',{count:devices.length,online:onlineCount}) }}<span v-if="incompatibleCount" class="summary-flag">{{ t('devices.summaryIncompatible',{count:incompatibleCount}) }}</span></p>
      </div>
      <div class="header-actions">
        <button v-if="enrollableVehicles.length" class="button" @click="openEnrollment"><AppIcon name="plus" :size="15" />{{ t('devices.add') }}</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <AppModal :open="enrolling" :title="t('devices.enrollTitle')" @close="enrolling=false">
      <form class="enrollment-panel" @submit.prevent="createEnrollment">
        <div v-if="!enrollment" class="enrollment-fields">
          <label class="field"><span>{{ t('devices.implementation') }}</span><AppSelect v-model="selectedImplementation" :aria-label="t('devices.implementation')"><option v-for="item in implementations" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></label>
          <p class="field-hint">{{ t('devices.implementationHint') }}</p>
          <div v-if="chosenImplementation" class="implementation-card">
            <div class="implementation-heading"><strong>{{ chosenImplementation.name }}</strong><span v-if="chosenOrigin" class="origin-tag">{{ chosenOrigin }}</span></div>
            <dl class="implementation-facts">
              <div><dt>{{ t('devices.hardware') }}</dt><dd>{{ chosenImplementation.hardware }}</dd></div>
              <div><dt>{{ t('devices.setupStyle') }}</dt><dd>{{ t(`devices.setupKind.${chosenImplementation.setup_kind}`) }}</dd></div>
              <div><dt>{{ t('devices.protocol') }}</dt><dd class="mono">{{ chosenImplementation.protocol_version }}</dd></div>
            </dl>
            <p v-if="selectedImplementation===CUSTOM_IMPLEMENTATION" class="field-hint">{{ t('devices.customHint') }}</p>
            <a v-if="chosenDocsUrl" class="implementation-docs" :href="chosenDocsUrl" target="_blank" rel="noreferrer">{{ selectedImplementation===CUSTOM_IMPLEMENTATION ? t('devices.protocolDocs') : t('devices.implementationDocs') }}</a>
          </div>
          <label class="field"><span>{{ t('devices.vehicle') }}</span><AppSelect v-model="selectedVehicle" searchable :search-placeholder="t('vehicles.search')" :no-results-text="t('vehicles.noMatch')"><option v-for="vehicle in enrollableVehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
          <label class="field"><span>{{ t('devices.name') }}</span><input v-model="agentName" class="input" /></label>
          <CadenceFields v-model="enrollmentCadence" :signal-count="signalCount(selectedVehicle)" />
          <p class="field-hint">{{ t('devices.cadenceHint') }}</p>
          <p v-if="enrollmentError" class="error" role="alert">{{ enrollmentError }}</p>
        </div>
        <button v-if="!enrollment" class="button" :disabled="!selectedVehicle||!selectedImplementation||creating">{{ t('devices.add') }}</button>
        <div v-else class="setup-reveal">
          <p class="field-hint">{{ t('devices.setupHint',{name:mintedFor?.name ?? selectedImplementation}) }}</p>
          <ol class="setup-steps">
            <li v-for="(step,index) in enrollment.setup_steps" :key="index" :class="`step-${step.kind}`">
              <p v-if="step.kind!=='link'" class="step-text">{{ stepText(step) }}</p>
              <div v-if="step.kind==='command'" class="copy-surface"><pre class="mono" tabindex="0">{{ step.command }}</pre><button class="copy-button" type="button" :title="t('devices.copy')" :aria-label="t('devices.copy')" @click="copy(`step-${index}`,step.command)"><AppIcon :name="copiedKey===`step-${index}` ? 'check' : 'copy'" :size="16" /></button></div>
              <div v-else-if="step.kind==='value'" class="copy-surface"><code class="mono" tabindex="0">{{ step.value }}</code><button class="copy-button" type="button" :title="t('devices.copyNamed',{name:stepText(step)})" :aria-label="t('devices.copyNamed',{name:stepText(step)})" @click="copy(`step-${index}`,step.value)"><AppIcon :name="copiedKey===`step-${index}` ? 'check' : 'copy'" :size="16" /></button></div>
              <p v-else-if="step.kind==='link'" class="step-link"><a :href="step.url" target="_blank" rel="noreferrer">{{ stepText(step) }}</a></p>
            </li>
          </ol>
          <p class="field-hint">{{ t('devices.tokenExpires',{time:new Date(enrollment.expires_at).toLocaleString()}) }}</p>
          <span v-if="copiedKey" class="copy-feedback" role="status">{{ t('devices.copied') }}</span>
          <button class="button ghost" type="button" @click="enrolling=false">{{ t('common.close') }}</button>
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
          <div><dt>{{ t('devices.implementation') }}</dt><dd class="mono" :title="implementationName(device.implementation_id)">{{ device.implementation_id }}</dd></div>
          <div><dt>{{ t('devices.version') }}</dt><dd class="mono">{{ device.agent_version }}</dd></div>
          <div><dt>{{ t('devices.protocol') }}</dt><dd class="mono">{{ device.protocol_version }}</dd></div>
          <!-- Protocol compatibility is a property of the agent's build, not of
               whether it is currently reporting; the status pill owns that. -->
          <div><dt>{{ t('devices.compatibility') }}</dt><dd><span :class="['compat',device.compatibility]">{{ t(`devices.compat.${device.compatibility}`) }}</span></dd></div>
          <div><dt>{{ t('devices.hardware') }}</dt><dd>{{ device.hostname ?? '—' }}</dd></div>
          <div><dt>{{ t('devices.lastSeen') }}</dt><dd>{{ device.last_seen_at ? new Date(device.last_seen_at).toLocaleString() : t('common.never') }}</dd></div>
          <div><dt>{{ t('devices.cadence') }}</dt><dd>{{ t('devices.cadenceValue',{driving:device.sampling_seconds,parked:device.parked_sampling_seconds}) }}</dd></div>
        </dl>
        <div v-if="canOperateDevice(device)" class="device-actions">
          <button class="button secondary" :disabled="!!device.revoked_at" @click="openSettings(device)">{{ t('devices.settings') }}</button>
          <button class="button secondary" :disabled="!!device.revoked_at" @click="rotate(device.id)">{{ t('devices.rotate') }}</button>
          <button class="link-button danger" type="button" :disabled="!!device.revoked_at" @click="revoke(device.id)">{{ t('devices.revoke') }}</button>
          <button class="link-button danger" type="button" @click="remove(device)">{{ t('common.delete') }}</button>
        </div>
        <div v-if="rotatedCredential?.id===device.id" class="credential-reveal">
          <div class="credential-heading"><strong>{{ t('devices.credentialReady') }}</strong><button class="icon-button" :aria-label="t('common.close')" @click="rotatedCredential=null"><AppIcon name="close" :size="15" /></button></div>
          <div class="copy-surface"><code class="mono">{{ rotatedCredential.credential }}</code><button class="copy-button" :title="t('devices.copyCredential')" :aria-label="t('devices.copyCredential')" @click="copy('credential',rotatedCredential.credential)"><AppIcon :name="copiedKey==='credential' ? 'check' : 'copy'" :size="16" /></button></div>
          <small class="field-hint">{{ t('devices.credentialHint') }}</small>
        </div>
      </article>
    </div>
    <div v-else class="empty panel">
      <h2>{{ t('devices.noDevices') }}</h2>
      <!-- Each hint names an action, so each shows only to someone who can take it. -->
      <p v-if="enrollableVehicles.length">{{ t('devices.noDevicesHint') }}</p>
      <p v-else-if="isAdmin">{{ t('hooks.createVehicleFirst') }}</p>
    </div>
  </div>
</template>

<style scoped>
.summary-flag{margin-left:5px;color:var(--danger)}
.enrollment-panel{display:grid;grid-template-columns:minmax(0,1fr);gap:16px}
.enrollment-fields{display:grid;grid-template-columns:minmax(0,1fr);gap:14px}
.enrollment-fields>.field-hint{margin:-6px 0 0}
.enrollment-panel>.button{justify-self:start}
.implementation-card{display:grid;grid-template-columns:minmax(0,1fr);gap:10px;padding:12px;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius)}
.implementation-heading{display:flex;align-items:center;gap:8px}
.implementation-heading strong{font-size:var(--font-body);font-weight:600}
.origin-tag{flex:none;padding:2px 6px;color:var(--muted);background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-sm);font-size:var(--font-micro)}
.implementation-facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0}
.implementation-facts>div{min-width:0}
.implementation-facts dt{color:var(--muted);font-size:var(--font-caption)}
.implementation-facts dd{margin:2px 0 0;font-size:var(--font-caption)}
.implementation-card .field-hint{margin:0}
.implementation-docs{font-size:var(--font-caption)}
/* An auto grid track sizes to max-content, and a command or token never wraps. */
.setup-reveal{display:grid;grid-template-columns:minmax(0,1fr);gap:10px}
.setup-reveal>.button{justify-self:start}
.setup-reveal>.field-hint{margin:0}
.setup-steps{margin:0;padding-left:20px;list-style:decimal}
.setup-steps li{min-width:0}
.setup-steps li+li{margin-top:12px}
.setup-steps li::marker{color:var(--muted);font-size:var(--font-caption)}
.setup-steps li>*+*{margin-top:7px}
/* One step is an instruction, not a sequence, so it carries no number. */
.setup-steps li:only-child{margin-left:-20px;list-style:none}
.step-text{margin:0;font-size:var(--font-caption)}
.step-value .step-text{color:var(--muted)}
.step-link{margin:0;font-size:var(--font-caption)}
.copy-surface{position:relative;min-width:0;display:flex;align-items:center;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius)}
.copy-surface pre,.copy-surface code{min-width:0;display:block;flex:1;overflow:auto;margin:0;padding:11px 44px 11px 12px;color:var(--text);font-size:var(--font-caption);white-space:pre}
.copy-surface pre:focus-visible,.copy-surface code:focus-visible{outline:none;box-shadow:var(--focus-ring)}
.copy-button{position:absolute;top:6px;right:6px;width:30px;height:30px;display:grid;place-items:center;color:var(--muted);background:var(--panel);border:1px solid var(--line-strong);border-radius:var(--radius);cursor:pointer;transition:color .12s,border-color .12s}
.copy-button:hover{color:var(--text);border-color:var(--muted-2)}
.copy-feedback{color:var(--success);font-size:var(--font-caption)}

.device-list{overflow:hidden}
.device-row{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(420px,1.8fr) auto;align-items:center;gap:20px;padding:14px 16px;border-bottom:1px solid var(--line)}
.device-row:last-child{border-bottom:0}
.device-identity{min-width:0}
.device-identity h2{margin:0;overflow:hidden;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.device-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.stack-form{display:grid;gap:14px}
.stack-form .form-actions{justify-content:flex-end;margin-top:4px}
.device-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px 16px;margin:0}
.device-facts>div{min-width:0}
.device-facts dt{color:var(--muted);font-size:var(--font-caption)}
.device-facts dd{margin:2px 0 0;overflow:hidden;font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.compat{display:inline-flex;padding:1px 6px;color:var(--muted);background:var(--panel-2);border-radius:var(--radius-sm);font-size:var(--font-micro);line-height:1.5}
.compat.incompatible{color:var(--danger);background:var(--danger-soft)}
.device-actions{display:flex;align-items:center;gap:12px}
.credential-reveal{grid-column:1/-1;display:grid;gap:7px;padding:12px;background:var(--warning-soft);border-radius:var(--radius)}
.credential-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.credential-heading strong{color:var(--warning);font-size:var(--font-caption);font-weight:600}
.credential-reveal .copy-surface{background:var(--panel)}
.credential-reveal code{font-size:var(--font-caption)}

@media(max-width:1100px){
  .device-row{grid-template-columns:minmax(0,1fr) auto;row-gap:14px}
  .device-facts{grid-column:1/-1;grid-row:2}
  .device-actions{grid-column:1/-1;grid-row:3;justify-content:flex-end}
}
@media(max-width:860px){
  .device-facts{grid-template-columns:repeat(2,minmax(0,1fr))}
  .implementation-facts{grid-template-columns:1fr;gap:8px}
  .implementation-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .implementation-facts dd{margin:0}
}
@media(max-width:620px){
  .device-facts{grid-template-columns:1fr;gap:6px}
  .device-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .device-facts dd{margin:0}
  .setup-steps{padding-left:18px}
}
</style>
