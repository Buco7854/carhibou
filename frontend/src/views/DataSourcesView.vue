<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorMessage } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import CadenceFields from '../components/CadenceFields.vue'
import { CADENCE_PRESETS, type Cadence } from '../agentCadence'
import { canOperate, isAdmin, operableVehicles } from '../access'
import { formatInstantOrNever, statusTone } from '../vehicleDisplay'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'

type SetupStepKind = 'command'|'value'|'link'|'manual'
interface AgentImplementation { id:string; name:string; hardware:string; protocol_version:number; setup_kind:'command'|'guided'; docs_url:string }
interface SetupStep { kind:SetupStepKind; text:string; command:string; value:string; url:string }
interface Enrollment { token:string; expires_at:string; setup_steps:SetupStep[] }
interface Agent { id:string; vehicle_id:string; name:string; vehicle_profile:string|null; credential_version:number; implementation_id:string; protocol_version:number; agent_version:string; compatibility:'compatible'|'incompatible'; hostname:string|null; hardware:Record<string,unknown>; sampling_seconds:number; upload_seconds:number; parked_sampling_seconds:number; parked_upload_seconds:number; online:boolean; last_seen_at:string|null; last_config_sync_at:string|null; config_version:number; revoked_at:string|null; created_at:string }
type ConnectorStatus = 'disabled'|'connecting'|'connected'|'error'
interface ConnectorKind { id:string; name:string; description:string; docs_url:string }
interface ConnectorConfig { host:string; port:number; tls:boolean; tls_accept_invalid_certs:boolean; username:string; namespace:string; car_id:number; sample_seconds:number }
interface Connector { id:string; vehicle_id:string; name:string; kind:string; enabled:boolean; mapping_profile:string; config:ConnectorConfig; masked:string; config_version:number; status:ConnectorStatus; last_connected_at:string|null; last_message_at:string|null; last_sample_at:string|null; last_error:string; created_at:string; updated_at:string }

const BUNDLED_IMPLEMENTATION = 'carhibou.go'
const CUSTOM_IMPLEMENTATION = 'custom'
// The protocol reference is served by the API itself, so the author of an
// independent agent can reach it from this origin before any token exists.
const PROTOCOL_DOCS_URL = '/api/docs'
// A connector owns a shadow agent so telemetry keeps its foreign key, but the
// data source is what an operator manages, so the agents list leaves it out.
const BUNDLED_MAPPING_PROFILE = 'teslamate-mqtt-v1'
const CONNECTOR_PREFIX = 'connector.'
const SAMPLE_SECONDS_MIN = 1
const SAMPLE_SECONDS_MAX = 3600
const DEFAULT_CONNECTOR_CONFIG: ConnectorConfig = { host:'', port:1883, tls:false, tls_accept_invalid_certs:false, username:'', namespace:'', car_id:1, sample_seconds:10 }

// A preset carries its own key alongside the four intervals, and both the
// enrollment and settings schemas reject a field they do not declare.
function presetCadence(key:string):Cadence {
  const { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds } = CADENCE_PRESETS.find((preset) => preset.key === key)!
  return { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds }
}

const { t } = useI18n()
const agents = ref<Agent[]>([])
const vehicles = ref<Vehicle[]>([])
const implementations = ref<AgentImplementation[]>([])
const enrolling = ref(false)
const selectedVehicle = ref('')
const selectedImplementation = ref('')
const agentName = ref('Vehicle agent')
const enrollmentCadence = ref<Cadence>(presetCadence('standard'))
const profiles = ref<VehicleProfile[]>([])
const enrollmentProfile = ref<string|null>(null)
const draftProfile = ref<string|null>(null)
const editing = ref<Agent|null>(null)
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
const connectors = ref<Connector[]>([])
const connectorKinds = ref<ConnectorKind[]>([])
const connectorOpen = ref(false)
const connectorEditing = ref<Connector|null>(null)
const connectorKind = ref('')
const connectorVehicle = ref('')
const connectorName = ref('')
const connectorConfig = ref<ConnectorConfig>({ ...DEFAULT_CONNECTOR_CONFIG })
const connectorMappingProfile = ref('')
const connectorPassword = ref('')
const connectorSaving = ref(false)
const connectorError = ref('')
const error = ref('')
const vehicleNames = computed(() => Object.fromEntries(vehicles.value.map((item) => [item.id, item.name])))
// Enrollment creates a credential for the vehicle, so the choice is limited to
// vehicles the user may operate; an agent row follows its vehicle's level.
const enrollableVehicles = computed(() => operableVehicles(vehicles.value))
const chosenImplementation = computed(() => implementations.value.find((item) => item.id === selectedImplementation.value))
const chosenOrigin = computed(() => selectedImplementation.value === BUNDLED_IMPLEMENTATION ? t('agents.bundledTag') : selectedImplementation.value === CUSTOM_IMPLEMENTATION ? t('agents.customTag') : '')
const chosenDocsUrl = computed(() => selectedImplementation.value === CUSTOM_IMPLEMENTATION ? PROTOCOL_DOCS_URL : chosenImplementation.value?.docs_url ?? '')
function canOperateAgent(agent: Agent): boolean {
  return canOperate(vehicles.value.find((item) => item.id === agent.vehicle_id))
}
function implementationName(id:string):string {
  return implementations.value.find((item) => item.id === id)?.name ?? id
}
const enrolledAgents = computed(() => agents.value.filter((agent) => !agent.implementation_id.startsWith(CONNECTOR_PREFIX)))
const chosenKind = computed(() => connectorKinds.value.find((item) => item.id === connectorKind.value))
function profileName(id:string):string {
  return profiles.value.find((item) => item.id === id)?.name ?? id
}
function connectorKindName(id:string):string {
  return connectorKinds.value.find((item) => item.id === id)?.name ?? id
}
function canOperateConnector(connector:Connector):boolean {
  return canOperate(vehicles.value.find((item) => item.id === connector.vehicle_id))
}
function moment(value:string|null):string {
  return formatInstantOrNever(value, t('common.never'))
}
// A manifest may leave a step's text empty when the payload speaks for itself,
// so every kind still needs a sentence a reader can act on.
function stepText(step:SetupStep):string { return step.text || t(`agents.stepDefaults.${step.kind}`) }
const canProfiles = computed(() => profiles.value.filter((profile) => profile.type === 'can'))
const mappingProfiles = computed(() => profiles.value.filter((profile) => profile.type === 'mapping'))
// The estimate follows the profile chosen in this form, not the stored one.
function signalCount(profileId:string|null):number {
  const profile = profiles.value.find((item) => item.id === profileId)
  return profile?.definition.signals?.length ?? 0
}

async function load() {
  try {
    // Connectors are an optional subsystem: a server without them still has a
    // working agents page, so their absence empties that section and no more.
    const [loadedAgents, loadedVehicles, loadedProfiles, catalog, loadedConnectors, kinds] = await Promise.all([
      api<Agent[]>('/agents'), api<Vehicle[]>('/vehicles'), api<VehicleProfile[]>('/vehicle-profiles'), api<AgentImplementation[]>('/agent-implementations'),
      api<Connector[]>('/connectors').catch(() => [] as Connector[]), api<ConnectorKind[]>('/connector-kinds').catch(() => [] as ConnectorKind[]),
    ])
    agents.value = loadedAgents
    vehicles.value = loadedVehicles
    implementations.value = catalog
    connectors.value = loadedConnectors
    connectorKinds.value = kinds
    profiles.value = loadedProfiles
    if (!selectedVehicle.value && enrollableVehicles.value[0]) selectedVehicle.value = enrollableVehicles.value[0].id
    if (!catalog.some((item) => item.id === selectedImplementation.value)) {
      selectedImplementation.value = catalog.find((item) => item.id === BUNDLED_IMPLEMENTATION)?.id ?? catalog[0]?.id ?? ''
    }
  }
  catch (reason) { error.value = errorMessage(reason, t('common.error')) }
}
function openEnrollment() {
  enrollment.value = null
  mintedFor.value = null
  enrollmentError.value = ''
  copiedKey.value = ''
  enrollmentProfile.value = null
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
    enrollment.value = await api<Enrollment>(`/vehicles/${selectedVehicle.value}/enrollments`, { method:'POST', body:JSON.stringify({ implementation_id:selectedImplementation.value, name:agentName.value, vehicle_profile:enrollmentProfile.value, ...enrollmentCadence.value }) })
    mintedFor.value = chosenImplementation.value ?? null
  } catch (reason) { enrollmentError.value = errorMessage(reason, t('common.error')) }
  finally { creating.value = false }
}
function openSettings(agent:Agent) {
  error.value = ''
  editing.value = agent
  draftName.value = agent.name
  draftProfile.value = agent.vehicle_profile
  draftCadence.value = {
    sampling_seconds:agent.sampling_seconds,
    upload_seconds:agent.upload_seconds,
    parked_sampling_seconds:agent.parked_sampling_seconds,
    parked_upload_seconds:agent.parked_upload_seconds,
  }
}
async function saveSettings() {
  if (!editing.value) return
  saving.value = true
  error.value = ''
  try {
    await api(`/agents/${editing.value.id}`, { method:'PUT', body:JSON.stringify({ name:draftName.value, vehicle_profile:draftProfile.value, ...draftCadence.value }) })
    editing.value = null
    await load()
  } catch (reason) { error.value = errorMessage(reason, t('common.error')) }
  finally { saving.value = false }
}
async function copy(key:string, value:string) {
  if (!value) return
  await navigator.clipboard.writeText(value)
  copiedKey.value = key
  window.setTimeout(() => { if (copiedKey.value === key) copiedKey.value = '' }, 1500)
}
async function revoke(id:string) { if (!window.confirm(t('agents.revokeConfirm'))) return; await api(`/agents/${id}/revoke`, { method:'POST' }); await load() }
async function remove(agent:Agent) {
  if (!window.confirm(t('agents.deleteConfirm', { name: agent.name }))) return
  await api(`/agents/${agent.id}`, { method:'DELETE' })
  await load()
}
async function rotate(id:string) { const response = await api<{credential:string}>(`/agents/${id}/rotate`, {method:'POST'}); rotatedCredential.value={id,credential:response.credential} }
function openConnector(connector:Connector|null) {
  connectorEditing.value = connector
  connectorError.value = ''
  // Never prefill the password: the server does not return it, and an empty
  // field is what tells the save to leave the stored one alone.
  connectorPassword.value = ''
  if (connector) {
    connectorKind.value = connector.kind
    connectorVehicle.value = connector.vehicle_id
    connectorName.value = connector.name
    connectorMappingProfile.value = connector.mapping_profile
    connectorConfig.value = { ...DEFAULT_CONNECTOR_CONFIG, ...connector.config }
  } else {
    connectorKind.value = connectorKinds.value[0]?.id ?? ''
    connectorVehicle.value = enrollableVehicles.value[0]?.id ?? ''
    connectorName.value = connectorKinds.value[0]?.name ?? 'Data source'
    connectorMappingProfile.value = BUNDLED_MAPPING_PROFILE
    connectorConfig.value = { ...DEFAULT_CONNECTOR_CONFIG }
  }
  connectorOpen.value = true
}
// The server rejects accepting an unverified certificate without TLS, so the
// sub-toggle never outlives the toggle it hangs from.
watch(() => connectorConfig.value.tls, (secure) => { if (!secure) connectorConfig.value.tls_accept_invalid_certs = false })
function connectorPayload():Record<string,unknown> {
  const body:Record<string,unknown> = { name:connectorName.value, mapping_profile:connectorMappingProfile.value, config:{ ...connectorConfig.value } }
  if (connectorPassword.value) body.password = connectorPassword.value
  return body
}
async function saveConnector() {
  if (!connectorKind.value || !connectorVehicle.value || connectorSaving.value) return
  connectorSaving.value = true
  connectorError.value = ''
  try {
    const existing = connectorEditing.value
    if (existing) await api(`/connectors/${existing.id}`, { method:'PUT', body:JSON.stringify({ ...connectorPayload(), enabled:existing.enabled }) })
    else await api(`/vehicles/${connectorVehicle.value}/connectors`, { method:'POST', body:JSON.stringify({ kind:connectorKind.value, ...connectorPayload() }) })
    connectorOpen.value = false
    await load()
  } catch (reason) { connectorError.value = errorMessage(reason, t('common.error')) }
  finally { connectorSaving.value = false }
}
// Enabling is a config write like any other, so it travels as the same full body
// the form sends rather than through a second, narrower endpoint.
async function setConnectorEnabled(connector:Connector, enabled:boolean) {
  await api(`/connectors/${connector.id}`, { method:'PUT', body:JSON.stringify({ name:connector.name, enabled, mapping_profile:connector.mapping_profile, config:{ ...connector.config } }) })
  await load()
}
async function removeConnector(connector:Connector) {
  if (!window.confirm(t('connectors.deleteConfirm', { name: connector.name }))) return
  await api(`/connectors/${connector.id}`, { method:'DELETE' })
  await load()
}
const onlineCount = computed(() => enrolledAgents.value.filter((agent) => agent.online && !agent.revoked_at).length)
// Agent versions belong to their own implementations and are never comparable
// across them, so the roster counts protocol incompatibility instead.
const incompatibleCount = computed(() => enrolledAgents.value.filter((agent) => agent.compatibility === 'incompatible').length)
onMounted(load)
</script>

<template>
  <div class="page">
    <header class="page-header">
      <div>
        <h1>{{ t('dataSources.title') }}</h1>
        <p>{{ t('dataSources.summary') }}</p>
      </div>
      <div class="header-actions">
        <button v-if="enrollableVehicles.length&&connectorKinds.length" class="button secondary" @click="openConnector(null)"><AppIcon name="plus" :size="15" />{{ t('connectors.add') }}</button>
        <button v-if="enrollableVehicles.length" class="button" @click="openEnrollment"><AppIcon name="plus" :size="15" />{{ t('agents.add') }}</button>
      </div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>

    <AppModal :open="enrolling" :title="t('agents.enrollTitle')" @close="enrolling=false">
      <form class="enrollment-panel" @submit.prevent="createEnrollment">
        <div v-if="!enrollment" class="enrollment-fields">
          <label class="field"><span>{{ t('agents.implementation') }}</span><AppSelect v-model="selectedImplementation" :aria-label="t('agents.implementation')"><option v-for="item in implementations" :key="item.id" :value="item.id">{{ item.name }}</option></AppSelect></label>
          <p class="field-hint">{{ t('agents.implementationHint') }}</p>
          <div v-if="chosenImplementation" class="implementation-card">
            <div class="implementation-heading"><strong>{{ chosenImplementation.name }}</strong><span v-if="chosenOrigin" class="origin-tag">{{ chosenOrigin }}</span></div>
            <dl class="implementation-facts">
              <div><dt>{{ t('agents.hardware') }}</dt><dd>{{ chosenImplementation.hardware }}</dd></div>
              <div><dt>{{ t('agents.setupStyle') }}</dt><dd>{{ t(`agents.setupKind.${chosenImplementation.setup_kind}`) }}</dd></div>
              <div><dt>{{ t('agents.protocol') }}</dt><dd class="mono">{{ chosenImplementation.protocol_version }}</dd></div>
            </dl>
            <p v-if="selectedImplementation===CUSTOM_IMPLEMENTATION" class="field-hint">{{ t('agents.customHint') }}</p>
            <a v-if="chosenDocsUrl" class="implementation-docs" :href="chosenDocsUrl" target="_blank" rel="noreferrer">{{ selectedImplementation===CUSTOM_IMPLEMENTATION ? t('agents.protocolDocs') : t('agents.implementationDocs') }}</a>
          </div>
          <label class="field"><span>{{ t('agents.vehicle') }}</span><AppSelect v-model="selectedVehicle" searchable :search-placeholder="t('vehicles.search')" :no-results-text="t('vehicles.noMatch')"><option v-for="vehicle in enrollableVehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
          <label class="field"><span>{{ t('agents.name') }}</span><input v-model="agentName" class="input" /></label>
          <label class="field"><span>{{ t('agents.profile') }}</span><AppSelect v-model="enrollmentProfile" :aria-label="t('agents.profile')"><option :value="null">{{ t('agents.noProfile') }}</option><option v-for="profile in canProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></AppSelect></label>
          <p class="field-hint">{{ t('agents.profileHint') }}</p>
          <CadenceFields v-model="enrollmentCadence" :signal-count="signalCount(enrollmentProfile)" />
          <p class="field-hint">{{ t('agents.cadenceHint') }}</p>
          <p v-if="enrollmentError" class="error" role="alert">{{ enrollmentError }}</p>
        </div>
        <button v-if="!enrollment" class="button" :disabled="!selectedVehicle||!selectedImplementation||creating">{{ t('agents.add') }}</button>
        <div v-else class="setup-reveal">
          <p class="field-hint">{{ t('agents.setupHint',{name:mintedFor?.name ?? selectedImplementation}) }}</p>
          <ol class="setup-steps">
            <li v-for="(step,index) in enrollment.setup_steps" :key="index" :class="`step-${step.kind}`">
              <p v-if="step.kind!=='link'" class="step-text">{{ stepText(step) }}</p>
              <div v-if="step.kind==='command'" class="copy-surface"><pre class="mono" tabindex="0">{{ step.command }}</pre><button class="copy-button" type="button" :title="t('agents.copy')" :aria-label="t('agents.copy')" @click="copy(`step-${index}`,step.command)"><AppIcon :name="copiedKey===`step-${index}` ? 'check' : 'copy'" :size="16" /></button></div>
              <div v-else-if="step.kind==='value'" class="copy-surface"><code class="mono" tabindex="0">{{ step.value }}</code><button class="copy-button" type="button" :title="t('agents.copyNamed',{name:stepText(step)})" :aria-label="t('agents.copyNamed',{name:stepText(step)})" @click="copy(`step-${index}`,step.value)"><AppIcon :name="copiedKey===`step-${index}` ? 'check' : 'copy'" :size="16" /></button></div>
              <p v-else-if="step.kind==='link'" class="step-link"><a :href="step.url" target="_blank" rel="noreferrer">{{ stepText(step) }}</a></p>
            </li>
          </ol>
          <p class="field-hint">{{ t('agents.tokenExpires',{time:moment(enrollment.expires_at)}) }}</p>
          <span v-if="copiedKey" class="copy-feedback" role="status">{{ t('agents.copied') }}</span>
          <button class="button ghost" type="button" @click="enrolling=false">{{ t('common.close') }}</button>
        </div>
      </form>
    </AppModal>

    <AppModal :open="Boolean(editing)" :title="t('agents.settings')" @close="editing=null">
      <form v-if="editing" class="stack-form" @submit.prevent="saveSettings">
        <label class="field"><span>{{ t('agents.name') }}</span><input v-model="draftName" class="input" required autofocus /></label>
        <label class="field"><span>{{ t('agents.profile') }}</span><AppSelect v-model="draftProfile" :aria-label="t('agents.profile')"><option :value="null">{{ t('agents.noProfile') }}</option><option v-for="profile in canProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></AppSelect></label>
        <p class="field-hint">{{ t('agents.profileHint') }}</p>
        <CadenceFields v-model="draftCadence" :signal-count="signalCount(draftProfile)" />
        <p class="field-hint">{{ t('agents.cadenceHint') }}</p>
        <p class="field-hint">{{ t('agents.cadenceApplyHint') }}</p>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="form-actions">
          <button class="button" :disabled="saving">{{ t('common.save') }}</button>
          <button class="button ghost" type="button" @click="editing=null">{{ t('common.cancel') }}</button>
        </div>
      </form>
    </AppModal>

    <div class="section-head">
      <h2>{{ t('dataSources.agentGroup') }}</h2>
      <span class="count">{{ enrolledAgents.length }}</span>
      <span v-if="enrolledAgents.length" class="group-note">{{ t('agents.summary',{count:enrolledAgents.length,online:onlineCount}) }}<span v-if="incompatibleCount" class="summary-flag">{{ t('agents.summaryIncompatible',{count:incompatibleCount}) }}</span></span>
    </div>
    <div v-if="enrolledAgents.length" class="source-list panel">
      <article v-for="agent in enrolledAgents" :key="agent.id" class="source-row">
        <div class="source-identity">
          <h2>{{ agent.name }}</h2>
          <p>{{ vehicleNames[agent.vehicle_id] }}</p>
        </div>
        <span :class="['status',{online:agent.online&&!agent.revoked_at}]">{{ agent.revoked_at ? t('agents.revoked') : agent.online ? t('common.online') : agent.last_seen_at ? t('common.stale') : t('common.never') }}</span>
        <dl class="source-facts">
          <div><dt>{{ t('agents.implementation') }}</dt><dd class="mono" :title="implementationName(agent.implementation_id)">{{ agent.implementation_id }}</dd></div>
          <div><dt>{{ t('agents.version') }}</dt><dd class="mono">{{ agent.agent_version }}</dd></div>
          <div><dt>{{ t('agents.protocol') }}</dt><dd class="mono">{{ agent.protocol_version }}</dd></div>
          <!-- Protocol compatibility is a property of the agent's build, not of
               whether it is currently reporting; the status pill owns that. -->
          <div><dt>{{ t('agents.compatibility') }}</dt><dd><span :class="['compat',agent.compatibility]">{{ t(`agents.compat.${agent.compatibility}`) }}</span></dd></div>
          <div><dt>{{ t('agents.hardware') }}</dt><dd>{{ agent.hostname ?? '—' }}</dd></div>
          <div><dt>{{ t('agents.lastSeen') }}</dt><dd>{{ moment(agent.last_seen_at) }}</dd></div>
          <div><dt>{{ t('agents.cadence') }}</dt><dd>{{ t('agents.cadenceValue',{driving:agent.sampling_seconds,parked:agent.parked_sampling_seconds}) }}</dd></div>
          <div><dt>{{ t('agents.profile') }}</dt><dd>{{ agent.vehicle_profile ? profileName(agent.vehicle_profile) : t('agents.noProfile') }}</dd></div>
        </dl>
        <div v-if="canOperateAgent(agent)" class="source-actions">
          <button class="button secondary" :disabled="!!agent.revoked_at" @click="openSettings(agent)">{{ t('agents.settings') }}</button>
          <button class="button secondary" :disabled="!!agent.revoked_at" @click="rotate(agent.id)">{{ t('agents.rotate') }}</button>
          <button class="link-button danger" type="button" :disabled="!!agent.revoked_at" @click="revoke(agent.id)">{{ t('agents.revoke') }}</button>
          <button class="link-button danger" type="button" @click="remove(agent)">{{ t('common.delete') }}</button>
        </div>
        <div v-if="rotatedCredential?.id===agent.id" class="credential-reveal">
          <div class="credential-heading"><strong>{{ t('agents.credentialReady') }}</strong><button class="icon-button" :aria-label="t('common.close')" @click="rotatedCredential=null"><AppIcon name="close" :size="15" /></button></div>
          <div class="copy-surface"><code class="mono">{{ rotatedCredential.credential }}</code><button class="copy-button" :title="t('agents.copyCredential')" :aria-label="t('agents.copyCredential')" @click="copy('credential',rotatedCredential.credential)"><AppIcon :name="copiedKey==='credential' ? 'check' : 'copy'" :size="16" /></button></div>
          <small class="field-hint">{{ t('agents.credentialHint') }}</small>
        </div>
      </article>
    </div>
    <div v-else class="empty panel">
      <h2>{{ t('agents.none') }}</h2>
      <!-- Each hint names an action, so each shows only to someone who can take it. -->
      <p v-if="enrollableVehicles.length">{{ t('agents.noneHint') }}</p>
      <p v-else-if="isAdmin">{{ t('hooks.createVehicleFirst') }}</p>
    </div>

    <section class="data-sources">
      <div class="section-head"><h2>{{ t('dataSources.connectorGroup') }}</h2><span class="count">{{ connectors.length }}</span></div>
      <div v-if="connectors.length" class="source-list panel">
        <article v-for="connector in connectors" :key="connector.id" class="source-row connector-row">
          <div class="source-identity">
            <h2>{{ connector.name }}</h2>
            <p>{{ vehicleNames[connector.vehicle_id] }}</p>
          </div>
          <!-- A data source reports its own session state; it has no agent to be
               online, so the connector status is the only health signal here. -->
          <span :class="['status', statusTone(connector.status)]">{{ t(`connectors.status.${connector.status}`) }}</span>
          <dl class="source-facts">
            <div><dt>{{ t('connectors.kind') }}</dt><dd :title="connector.kind">{{ connectorKindName(connector.kind) }}</dd></div>
            <div><dt>{{ t('connectors.broker') }}</dt><dd class="mono" :title="`${connector.config.host}:${connector.config.port}`">{{ connector.config.host }}:{{ connector.config.port }}</dd></div>
            <div><dt>{{ t('connectors.lastMessage') }}</dt><dd>{{ moment(connector.last_message_at) }}</dd></div>
            <div><dt>{{ t('connectors.interval') }}</dt><dd>{{ t('connectors.intervalValue',{seconds:connector.config.sample_seconds}) }}</dd></div>
          </dl>
          <div v-if="canOperateConnector(connector)" class="source-actions">
            <button class="button secondary" @click="openConnector(connector)">{{ t('agents.settings') }}</button>
            <button class="button secondary" @click="setConnectorEnabled(connector,!connector.enabled)">{{ connector.enabled ? t('connectors.disable') : t('connectors.enable') }}</button>
            <button class="link-button danger" type="button" @click="removeConnector(connector)">{{ t('common.delete') }}</button>
          </div>
          <p v-if="connector.last_error" class="connector-error" role="status">{{ connector.last_error }}</p>
        </article>
      </div>
      <div v-else class="empty panel">
        <h2>{{ t('connectors.none') }}</h2>
        <p v-if="enrollableVehicles.length&&connectorKinds.length">{{ t('connectors.noneHint') }}</p>
      </div>
    </section>

    <AppModal :open="connectorOpen" :title="connectorEditing ? t('connectors.editTitle') : t('connectors.addTitle')" @close="connectorOpen=false">
      <form class="stack-form connector-form" @submit.prevent="saveConnector">
        <label class="field"><span>{{ t('connectors.kind') }}</span><AppSelect v-model="connectorKind" :disabled="Boolean(connectorEditing)" :aria-label="t('connectors.kind')"><option v-for="kind in connectorKinds" :key="kind.id" :value="kind.id">{{ kind.name }}</option></AppSelect></label>
        <div v-if="chosenKind" class="implementation-card">
          <div class="implementation-heading"><strong>{{ chosenKind.name }}</strong></div>
          <p v-if="chosenKind.description" class="field-hint">{{ chosenKind.description }}</p>
          <a v-if="chosenKind.docs_url" class="implementation-docs" :href="chosenKind.docs_url" target="_blank" rel="noreferrer">{{ t('connectors.docs') }}</a>
        </div>
        <label class="field"><span>{{ t('agents.vehicle') }}</span><AppSelect v-model="connectorVehicle" :disabled="Boolean(connectorEditing)" searchable :search-placeholder="t('vehicles.search')" :no-results-text="t('vehicles.noMatch')"><option v-for="vehicle in enrollableVehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
        <label class="field"><span>{{ t('agents.name') }}</span><input v-model="connectorName" class="input" required /></label>
        <label class="field"><span>{{ t('connectors.mappingProfile') }}</span><AppSelect v-model="connectorMappingProfile" :aria-label="t('connectors.mappingProfile')"><option v-for="profile in mappingProfiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option></AppSelect></label>
        <p class="field-hint">{{ t('connectors.mappingProfileHint') }}</p>
        <p class="field-hint">{{ t('connectors.brokerHint') }}</p>
        <div class="form-grid">
          <label class="field"><span>{{ t('connectors.host') }}</span><input v-model="connectorConfig.host" class="input" required placeholder="homeassistant.local" /></label>
          <label class="field"><span>{{ t('connectors.port') }}</span><input v-model.number="connectorConfig.port" class="input" type="number" min="1" max="65535" required /></label>
        </div>
        <label class="check"><input v-model="connectorConfig.tls" type="checkbox" /><span>{{ t('connectors.tls') }}</span></label>
        <!-- Accepting an invalid certificate only means anything once TLS is on. -->
        <label v-if="connectorConfig.tls" class="check nested"><input v-model="connectorConfig.tls_accept_invalid_certs" type="checkbox" /><span>{{ t('connectors.acceptInvalidCerts') }}</span></label>
        <p v-if="connectorConfig.tls&&connectorConfig.tls_accept_invalid_certs" class="field-hint nested">{{ t('connectors.acceptInvalidCertsHint') }}</p>
        <div class="form-grid">
          <label class="field"><span>{{ t('connectors.username') }}</span><input v-model="connectorConfig.username" class="input" autocomplete="off" /></label>
          <label class="field"><span>{{ t('connectors.password') }}</span><input v-model="connectorPassword" class="input" type="password" autocomplete="new-password" :placeholder="connectorEditing?.masked ?? ''" /></label>
        </div>
        <p v-if="connectorEditing" class="field-hint">{{ t('connectors.passwordHint') }}</p>
        <div class="form-grid">
          <label class="field"><span>{{ t('connectors.namespace') }}</span><input v-model="connectorConfig.namespace" class="input" /></label>
          <label class="field"><span>{{ t('connectors.carId') }}</span><input v-model.number="connectorConfig.car_id" class="input" type="number" min="1" required /></label>
        </div>
        <label class="field"><span>{{ t('connectors.intervalField') }}</span><input v-model.number="connectorConfig.sample_seconds" class="input" type="number" :min="SAMPLE_SECONDS_MIN" :max="SAMPLE_SECONDS_MAX" required /></label>
        <p class="field-hint">{{ t('connectors.prefixHint') }}</p>
        <p v-if="connectorError" class="error" role="alert">{{ connectorError }}</p>
        <div class="form-actions">
          <button class="button" :disabled="connectorSaving||!connectorKind||!connectorVehicle">{{ t('common.save') }}</button>
          <button class="button ghost" type="button" @click="connectorOpen=false">{{ t('common.cancel') }}</button>
        </div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.summary-flag{margin-left:5px;color:var(--danger)}
.group-note{color:var(--muted);font-size:var(--font-caption)}
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

.source-list{overflow:hidden}
.source-row{display:grid;grid-template-columns:minmax(180px,1fr) auto minmax(420px,1.8fr) auto;align-items:center;gap:20px;padding:14px 16px;border-bottom:1px solid var(--line)}
.source-row:last-child{border-bottom:0}
.source-identity{min-width:0}
.source-identity h2{margin:0;overflow:hidden;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.source-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.stack-form{display:grid;gap:14px}
.stack-form .form-actions{justify-content:flex-end;margin-top:4px}
.source-facts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px 16px;margin:0}
.source-facts>div{min-width:0}
.source-facts dt{color:var(--muted);font-size:var(--font-caption)}
.source-facts dd{margin:2px 0 0;overflow:hidden;font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.compat{display:inline-flex;padding:1px 6px;color:var(--muted);background:var(--panel-2);border-radius:var(--radius-sm);font-size:var(--font-micro);line-height:1.5}
.compat.incompatible{color:var(--danger);background:var(--danger-soft)}
.data-sources{margin-top:26px}
.connector-error{grid-column:1/-1;margin:0;padding:9px 11px;color:var(--danger);background:var(--danger-soft);border-radius:var(--radius);font-size:var(--font-caption);overflow-wrap:anywhere}
.connector-form .check{display:flex;align-items:center;gap:8px;font-size:var(--font-body);cursor:pointer}
.connector-form .nested{margin-left:22px}
.connector-form .form-actions{justify-content:flex-end;margin-top:4px}
.source-actions{display:flex;align-items:center;gap:12px}
.credential-reveal{grid-column:1/-1;display:grid;gap:7px;padding:12px;background:var(--warning-soft);border-radius:var(--radius)}
.credential-heading{display:flex;align-items:center;justify-content:space-between;gap:12px}
.credential-heading strong{color:var(--warning);font-size:var(--font-caption);font-weight:600}
.credential-reveal .copy-surface{background:var(--panel)}
.credential-reveal code{font-size:var(--font-caption)}

@media(max-width:1100px){
  .source-row{grid-template-columns:minmax(0,1fr) auto;row-gap:14px}
  .source-facts{grid-column:1/-1;grid-row:2}
  .source-actions{grid-column:1/-1;grid-row:3;justify-content:flex-end}
}
@media(max-width:860px){
  .source-facts{grid-template-columns:repeat(2,minmax(0,1fr))}
  .implementation-facts{grid-template-columns:1fr;gap:8px}
  .implementation-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .implementation-facts dd{margin:0}
}
@media(max-width:620px){
  .source-facts{grid-template-columns:1fr;gap:6px}
  .source-facts>div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
  .source-facts dd{margin:0}
  .setup-steps{padding-left:18px}
}
</style>
