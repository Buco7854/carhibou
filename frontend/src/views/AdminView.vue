<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { auth } from '../api/auth'
import { isAdmin } from '../access'
import type { DefaultAccess, DefaultAccessGrant, Diagnostics, UserAccount, Vehicle, VehicleGrant } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'

const { t } = useI18n()
const diagnostics = ref<Diagnostics | null>(null)
const people = ref<UserAccount[]>([])
const peopleError = ref('')
const creating = ref(false)
const saving = ref(false)
const clearing = ref(false)
const dataMessage = ref('')
const dataError = ref('')
const emptyPerson = () => ({ email: '', display_name: '', password: '', is_admin: false })
const person = ref(emptyPerson())

const vehicles = ref<Vehicle[]>([])
const accessVehicleId = ref<string | number | null>(null)
const grants = ref<VehicleGrant[]>([])
const grantUserId = ref<string | number | null>(null)
const grantsSaving = ref(false)
const grantsSaved = ref(false)
const grantsError = ref('')
const defaults = ref<DefaultAccess | null>(null)
const defaultsSaving = ref(false)
const defaultsSaved = ref(false)
const defaultsError = ref('')

// Administrators already operate every vehicle, so granting them one is noise.
const grantCandidates = computed(() =>
  people.value.filter((account) => !account.is_admin && !grants.value.some((grant) => grant.user_id === account.id)))

async function loadPeople(): Promise<void> {
  if (!isAdmin.value) return
  try { people.value = await api<UserAccount[]>('/users') }
  catch (reason) { peopleError.value = reason instanceof Error ? reason.message : t('common.error') }
}

async function createPerson(): Promise<void> {
  saving.value = true
  peopleError.value = ''
  try {
    await api('/users', { method: 'POST', body: JSON.stringify(person.value) })
    creating.value = false
    person.value = emptyPerson()
    await loadPeople()
  } catch (reason) { peopleError.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { saving.value = false }
}

async function updatePerson(account: UserAccount, changes: Record<string, unknown>): Promise<void> {
  peopleError.value = ''
  try {
    await api(`/users/${account.id}`, { method: 'PATCH', body: JSON.stringify(changes) })
    await loadPeople()
  } catch (reason) { peopleError.value = reason instanceof Error ? reason.message : t('common.error') }
}

async function removePerson(account: UserAccount): Promise<void> {
  if (!confirm(t('settings.deleteUserConfirm', { name: account.display_name }))) return
  peopleError.value = ''
  try {
    await api(`/users/${account.id}`, { method: 'DELETE' })
    await loadPeople()
  } catch (reason) { peopleError.value = reason instanceof Error ? reason.message : t('common.error') }
}

async function loadGrants(): Promise<void> {
  grantsSaved.value = false
  grantsError.value = ''
  if (!accessVehicleId.value) { grants.value = []; return }
  try { grants.value = await api<VehicleGrant[]>(`/vehicles/${accessVehicleId.value}/access`) }
  catch (reason) { grantsError.value = reason instanceof Error ? reason.message : t('common.error') }
}
watch(accessVehicleId, loadGrants)

function addGrant(): void {
  const account = people.value.find((item) => item.id === grantUserId.value)
  if (!account) return
  grants.value.push({ user_id: account.id, email: account.email, display_name: account.display_name, level: 'view' })
  grantUserId.value = null
  grantsSaved.value = false
}

function setGrantLevel(grant: VehicleGrant, value: string | number | null): void {
  if (value === 'view' || value === 'operate') { grant.level = value; grantsSaved.value = false }
}

function removeGrant(grant: VehicleGrant): void {
  grants.value = grants.value.filter((item) => item !== grant)
  grantsSaved.value = false
}

async function saveGrants(): Promise<void> {
  grantsSaving.value = true
  grantsError.value = ''
  try {
    // Full replacement: the list on screen is exactly the list that will exist.
    grants.value = await api<VehicleGrant[]>(`/vehicles/${accessVehicleId.value}/access`, {
      method: 'PUT',
      body: JSON.stringify(grants.value.map(({ user_id, level }) => ({ user_id, level }))),
    })
    grantsSaved.value = true
  } catch (reason) { grantsError.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { grantsSaving.value = false }
}

function addDefaultGrant(): void {
  const remaining = vehicles.value.find((vehicle) => !defaults.value?.grants.some((grant) => grant.vehicle_id === vehicle.id))
  if (defaults.value && remaining) defaults.value.grants.push({ vehicle_id: remaining.id, level: 'view' })
  defaultsSaved.value = false
}

function setDefaultGrantVehicle(grant: DefaultAccessGrant, value: string | number | null): void {
  if (typeof value === 'string') { grant.vehicle_id = value; defaultsSaved.value = false }
}

function setDefaultGrantLevel(grant: DefaultAccessGrant, value: string | number | null): void {
  if (value === 'view' || value === 'operate') { grant.level = value; defaultsSaved.value = false }
}

function removeDefaultGrant(index: number): void {
  defaults.value?.grants.splice(index, 1)
  defaultsSaved.value = false
}

async function saveDefaults(): Promise<void> {
  if (!defaults.value) return
  defaultsSaving.value = true
  defaultsError.value = ''
  try {
    defaults.value = await api<DefaultAccess>('/admin/default-access', {
      method: 'PUT',
      body: JSON.stringify(defaults.value),
    })
    defaultsSaved.value = true
  } catch (reason) { defaultsError.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { defaultsSaving.value = false }
}

/**
 * Empty every vehicle of readings. The vehicles, agents, hooks and dashboards
 * are left standing; only what was recorded goes, which is what makes this usable
 * after a period of testing rather than a way to start over.
 */
async function clearAllTelemetry(): Promise<void> {
  if (!confirm(t('settings.clearAllConfirm'))) return
  clearing.value = true
  dataMessage.value = ''
  dataError.value = ''
  try {
    await api('/vehicles/telemetry', { method: 'DELETE' })
    dataMessage.value = t('settings.clearAllDone')
  } catch (reason) { dataError.value = reason instanceof Error ? reason.message : t('common.error') }
  finally { clearing.value = false }
}

onMounted(async () => {
  await loadPeople()
  if (isAdmin.value) {
    try {
      vehicles.value = await api<Vehicle[]>('/vehicles')
      accessVehicleId.value = vehicles.value[0]?.id ?? null
      defaults.value = await api<DefaultAccess>('/admin/default-access')
    } catch (reason) { defaultsError.value = reason instanceof Error ? reason.message : t('common.error') }
  }
  try { diagnostics.value = await api<Diagnostics>('/system/diagnostics') } catch { /* shown by its absence */ }
})
</script>

<template>
  <div class="page">
    <header class="page-header"><div><h1>{{ t('admin.title') }}</h1><p>{{ t('admin.hint') }}</p></div></header>

    <section v-if="isAdmin" class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.users') }}</h2><p>{{ t('settings.usersHint') }}</p></div>
      <div class="settings-body">
        <p v-if="peopleError" class="error" role="alert">{{ peopleError }}</p>
        <ul class="people-list">
          <li v-for="account in people" :key="account.id">
            <div class="person">
              <strong>{{ account.display_name }}<span v-if="account.id === auth.user?.id"> · {{ t('settings.you') }}</span></strong>
              <small>{{ account.email }}</small>
            </div>
            <span v-if="account.is_admin" class="person-tag">{{ t('settings.administrator') }}</span>
            <span :class="['status', { online: account.is_active }]">{{ account.is_active ? t('settings.activeAccount') : t('settings.inactiveAccount') }}</span>
            <div class="person-actions">
              <button class="link-button" type="button" @click="updatePerson(account, { is_admin: !account.is_admin })">{{ account.is_admin ? t('settings.revokeAdmin') : t('settings.makeAdmin') }}</button>
              <!-- An administrator can already create profiles, so the toggle would say nothing. -->
              <button v-if="!account.is_admin" class="link-button" type="button" @click="updatePerson(account, { can_create_profiles: !account.can_create_profiles })">{{ account.can_create_profiles ? t('admin.revokeProfiles') : t('admin.allowProfiles') }}</button>
              <button class="link-button" type="button" @click="updatePerson(account, { is_active: !account.is_active })">{{ account.is_active ? t('settings.suspend') : t('settings.restore') }}</button>
              <button class="link-button danger" type="button" @click="removePerson(account)">{{ t('common.delete') }}</button>
            </div>
          </li>
        </ul>
        <button class="button secondary" type="button" @click="creating = true"><AppIcon name="plus" :size="15" />{{ t('settings.addUser') }}</button>
      </div>
    </section>


    <AppModal :open="creating" :title="t('settings.addUser')" @close="creating = false">
      <form class="person-form" @submit.prevent="createPerson">
        <label class="field"><span>{{ t('auth.displayName') }}</span><input v-model="person.display_name" class="input" required autofocus /></label>
        <label class="field"><span>{{ t('auth.email') }}</span><input v-model="person.email" class="input" type="email" required /></label>
        <label class="field"><span>{{ t('auth.password') }}</span><input v-model="person.password" class="input" type="password" minlength="12" required /></label>
        <label class="check"><input v-model="person.is_admin" type="checkbox" /><span>{{ t('settings.administrator') }}</span></label>
        <p v-if="peopleError" class="error" role="alert">{{ peopleError }}</p>
        <div class="form-actions"><button class="button" :disabled="saving">{{ t('settings.createUser') }}</button><button class="button ghost" type="button" @click="creating = false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>


    <section v-if="isAdmin && vehicles.length" class="settings-block">
      <div class="settings-label"><h2>{{ t('admin.vehicleAccess') }}</h2><p>{{ t('admin.vehicleAccessHint') }}</p></div>
      <div class="settings-body">
        <label class="field grant-vehicle"><span>{{ t('common.vehicle') }}</span>
          <AppSelect v-model="accessVehicleId" :aria-label="t('common.vehicle')">
            <option v-for="item in vehicles" :key="item.id" :value="item.id">{{ item.name }}</option>
          </AppSelect>
        </label>
        <p v-if="grantsError" class="error" role="alert">{{ grantsError }}</p>
        <ul v-if="grants.length" class="grant-list">
          <li v-for="grant in grants" :key="grant.user_id">
            <div class="person">
              <strong>{{ grant.display_name }}</strong>
              <small>{{ grant.email }}</small>
            </div>
            <AppSelect compact :model-value="grant.level" :aria-label="t('admin.level')" @update:model-value="setGrantLevel(grant, $event)">
              <option value="view">{{ t('admin.levelView') }}</option>
              <option value="operate">{{ t('admin.levelOperate') }}</option>
            </AppSelect>
            <button class="link-button danger" type="button" @click="removeGrant(grant)">{{ t('admin.remove') }}</button>
          </li>
        </ul>
        <p v-else class="field-hint">{{ t('admin.noGrants') }}</p>
        <div v-if="grantCandidates.length" class="grant-add">
          <AppSelect v-model="grantUserId" :aria-label="t('settings.users')">
            <option :value="null">{{ t('admin.choosePerson') }}</option>
            <option v-for="account in grantCandidates" :key="account.id" :value="account.id">{{ account.display_name }}</option>
          </AppSelect>
          <button class="button secondary" type="button" :disabled="!grantUserId" @click="addGrant">{{ t('admin.addGrant') }}</button>
        </div>
        <div class="save-row">
          <button class="button" type="button" :disabled="grantsSaving" @click="saveGrants">{{ t('common.save') }}</button>
          <span v-if="grantsSaved" class="saved-note" role="status">{{ t('admin.accessSaved') }}</span>
        </div>
      </div>
    </section>


    <section v-if="isAdmin && defaults" class="settings-block">
      <div class="settings-label"><h2>{{ t('admin.defaultAccess') }}</h2><p>{{ t('admin.defaultAccessHint') }}</p></div>
      <div class="settings-body">
        <p v-if="defaultsError" class="error" role="alert">{{ defaultsError }}</p>
        <label class="check"><input v-model="defaults.profiles_create" type="checkbox" /><span>{{ t('admin.defaultProfilesCreate') }}</span></label>
        <ul v-if="defaults.grants.length" class="grant-list">
          <li v-for="(grant, index) in defaults.grants" :key="index">
            <AppSelect :model-value="grant.vehicle_id" :aria-label="t('common.vehicle')" @update:model-value="setDefaultGrantVehicle(grant, $event)">
              <option v-for="item in vehicles" :key="item.id" :value="item.id">{{ item.name }}</option>
            </AppSelect>
            <AppSelect compact :model-value="grant.level" :aria-label="t('admin.level')" @update:model-value="setDefaultGrantLevel(grant, $event)">
              <option value="view">{{ t('admin.levelView') }}</option>
              <option value="operate">{{ t('admin.levelOperate') }}</option>
            </AppSelect>
            <button class="link-button danger" type="button" @click="removeDefaultGrant(index)">{{ t('admin.remove') }}</button>
          </li>
        </ul>
        <button v-if="vehicles.length" class="button secondary" type="button" @click="addDefaultGrant"><AppIcon name="plus" :size="15" />{{ t('admin.addGrant') }}</button>
        <div class="save-row">
          <button class="button" type="button" :disabled="defaultsSaving" @click="saveDefaults">{{ t('common.save') }}</button>
          <span v-if="defaultsSaved" class="saved-note" role="status">{{ t('admin.accessSaved') }}</span>
        </div>
      </div>
    </section>


    <section class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.data') }}</h2></div>
      <div class="settings-body">
        <p class="field-hint">{{ t('settings.clearAllHint') }}</p>
        <p v-if="dataMessage" class="saved-note" role="status">{{ dataMessage }}</p>
        <p v-if="dataError" class="error" role="alert">{{ dataError }}</p>
        <button class="button danger" type="button" :disabled="clearing" @click="clearAllTelemetry">{{ t('settings.clearAll') }}</button>
      </div>
    </section>


    <section v-if="diagnostics" class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.diagnostics') }}</h2></div>
      <div class="settings-body">
        <dl class="diagnostics-grid">
          <div><dt>{{ t('settings.version') }}</dt><dd class="mono">{{ diagnostics.version }}</dd></div>
          <div><dt>{{ t('settings.database') }}</dt><dd class="mono">{{ diagnostics.database }}</dd></div>
          <div><dt>{{ t('settings.workers') }}</dt><dd class="mono">{{ diagnostics.workers.length }}</dd></div>
          <div><dt>{{ t('settings.pendingJobs') }}</dt><dd class="mono">{{ diagnostics.pending_jobs }}</dd></div>
          <div><dt>{{ t('settings.failedJobs') }}</dt><dd class="mono">{{ diagnostics.failed_jobs }}</dd></div>
          <div><dt>{{ t('settings.hookFailures') }}</dt><dd class="mono">{{ diagnostics.hook_failures }}</dd></div>
          <div><dt>{{ t('settings.staleAgents') }}</dt><dd class="mono">{{ diagnostics.stale_agents }}</dd></div>
        </dl>
      </div>
    </section>

  </div>
</template>

<style scoped>
.settings-page{max-width:900px;margin-left:0}
.settings-block{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr);gap:20px 40px;padding:22px 0;border-top:1px solid var(--line)}
.settings-block:first-of-type{border-top:0;padding-top:0}
.settings-label h2{margin:0;font-size:14px;font-weight:600}
.settings-label p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.5}
.settings-body{display:grid;gap:20px}
.settings-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}

.account-facts{display:grid;gap:7px;margin:0}
.account-facts>div{display:flex;align-items:baseline;gap:12px}
.account-facts dt{min-width:110px;color:var(--muted);font-size:12px}
.account-facts dd{margin:0;font-size:13px;font-weight:500}

.password-form{display:grid;gap:12px}
.password-actions{display:flex;align-items:center;gap:16px}

.session-list{list-style:none;margin:0;padding:0;display:grid}
.session-list li{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)}
.session-list li:first-child{padding-top:0}
.session-list li:last-child{border-bottom:0;padding-bottom:0}
.session-list strong{display:block;font-size:13px;font-weight:500}
.session-list small{display:block;margin-top:2px;color:var(--muted);font-size:12px}

.people-list{list-style:none;margin:0;padding:0;display:grid}
.people-list li{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 12px;padding:10px 0;border-bottom:1px solid var(--line)}
.people-list li:first-child{padding-top:0}
.person{min-width:0}
.person strong{display:block;overflow:hidden;font-size:13px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.person strong span{color:var(--muted);font-weight:400}
.person small{display:block;margin-top:2px;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.person-tag{padding:2px 7px;color:var(--accent);background:var(--accent-soft);border-radius:4px;font-size:11px}
.person-actions{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:14px}
.settings-body>.button{justify-self:start}
.person-form{display:grid;gap:14px}
.person-form .form-actions{justify-content:flex-end;margin-top:2px}
.check{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}
.check input{width:14px;height:14px;accent-color:var(--accent)}
.grant-vehicle{max-width:320px}
.grant-list{list-style:none;margin:0;padding:0;display:grid}
.grant-list li{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 12px;padding:10px 0;border-bottom:1px solid var(--line)}
.grant-list li:first-child{padding-top:0}
.grant-add{display:flex;align-items:center;gap:10px}
.grant-add>:first-child{width:min(260px,100%)}
.save-row{display:flex;align-items:center;gap:12px}
.diagnostics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:14px;margin:0}
.diagnostics-grid dt{color:var(--muted);font-size:12px}
.diagnostics-grid dd{margin:3px 0 0;font-size:15px;font-weight:500}

@media(max-width:760px){
  .settings-block{grid-template-columns:1fr;gap:14px}
  .settings-pair{grid-template-columns:1fr}
}
</style>
