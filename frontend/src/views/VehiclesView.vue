<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'
import VehicleMedia from '../components/VehicleMedia.vue'
import { energySummary, metricLabel, metricNumber } from '../vehicleDisplay'

type VehicleFilter = 'all' | 'online' | 'parked'

interface VehicleForm {
  name: string
}

const vehicles = ref<Vehicle[]>([])
const profiles = ref<VehicleProfile[]>([])
const { t } = useI18n()
const showForm = ref(false)
const deleteTarget = ref<Vehicle | null>(null)
const deleteBusy = ref(false)
const error = ref('')
const photoBusyId = ref('')
const photoNotice = ref<{ kind: 'error' | 'success'; message: string } | null>(null)
const search = ref('')
const filter = ref<VehicleFilter>('all')
const emptyForm = (): VehicleForm => ({ name: '' })
const form = ref<VehicleForm>(emptyForm())
const photoTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
const maxPhotoBytes = 25 * 1024 * 1024

const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const profileNames = computed(() => Object.fromEntries(profiles.value.map((profile) => [profile.id, profile.name])))
const filteredVehicles = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return vehicles.value.filter((vehicle) => {
    if (filter.value === 'online' && !vehicle.state?.online) return false
    if (filter.value === 'parked' && vehicle.state?.online) return false
    return !query || [vehicle.name, vehicle.manufacturer, vehicle.model, vehicle.year].join(' ').toLocaleLowerCase().includes(query)
  })
})

function vehicleEnergy(vehicle: Vehicle) { return energySummary(vehicle) }
function vehicleSpeed(vehicle: Vehicle): number | null { return metricNumber(vehicle, 'vehicle.speed') }
function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? new Date(vehicle.state.updated_at).toLocaleString() : t('common.never')
}

async function load(): Promise<void> {
  ;[vehicles.value, profiles.value] = await Promise.all([
    api<Vehicle[]>('/vehicles'),
    api<VehicleProfile[]>('/vehicle-profiles'),
  ])
}
async function create(): Promise<void> {
  error.value = ''
  const payload = { name: form.value.name.trim() }
  try { await api('/vehicles', { method: 'POST', body: JSON.stringify(payload) }); showForm.value = false; form.value = emptyForm(); await load() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}

async function assignVehicleProfile(vehicle: Vehicle, value: string | number | null): Promise<void> {
  const profileId = typeof value === 'string' && value ? value : null
  try {
    await api(`/vehicles/${vehicle.id}/profile`, { method: 'PUT', body: JSON.stringify({ profile_id: profileId }) })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('common.error')
  }
}

async function uploadPhoto(vehicle: Vehicle, file: File): Promise<void> {
  photoNotice.value = null
  if (!photoTypes.has(file.type)) {
    photoNotice.value = { kind: 'error', message: t('vehicles.photoInvalidType') }
    return
  }
  if (file.size > maxPhotoBytes) {
    photoNotice.value = { kind: 'error', message: t('vehicles.photoTooLarge') }
    return
  }
  photoBusyId.value = vehicle.id
  try {
    await api<void>(`/vehicles/${vehicle.id}/photo`, { method: 'PUT', headers: { 'Content-Type': file.type }, body: file })
    await load()
    photoNotice.value = { kind: 'success', message: t('vehicles.photoAdded', { name: vehicle.name }) }
  } catch (reason) {
    photoNotice.value = { kind: 'error', message: reason instanceof Error ? reason.message : t('common.error') }
  } finally {
    photoBusyId.value = ''
  }
}

async function removePhoto(vehicle: Vehicle): Promise<void> {
  if (!window.confirm(t('vehicles.removePhotoConfirm', { name: vehicle.name }))) return
  photoNotice.value = null
  photoBusyId.value = vehicle.id
  try {
    await api<void>(`/vehicles/${vehicle.id}/photo`, { method: 'DELETE' })
    await load()
    photoNotice.value = { kind: 'success', message: t('vehicles.photoRemoved', { name: vehicle.name }) }
  } catch (reason) {
    photoNotice.value = { kind: 'error', message: reason instanceof Error ? reason.message : t('common.error') }
  } finally {
    photoBusyId.value = ''
  }
}

function closeDelete(): void {
  if (!deleteBusy.value) deleteTarget.value = null
}

async function deleteVehicle(): Promise<void> {
  const vehicle = deleteTarget.value
  if (!vehicle) return
  deleteBusy.value = true
  photoNotice.value = null
  try {
    await api<void>(`/vehicles/${vehicle.id}`, { method: 'DELETE' })
    deleteTarget.value = null
    await load()
    photoNotice.value = { kind: 'success', message: t('vehicles.deleted', { name: vehicle.name }) }
  } catch (reason) {
    photoNotice.value = { kind: 'error', message: reason instanceof Error ? reason.message : t('common.error') }
  } finally {
    deleteBusy.value = false
  }
}
onMounted(load)
</script>

<template>
  <div class="page vehicles-page">
    <header class="page-header">
      <div>
        <h1>{{ t('vehicles.title') }}</h1>
        <p>{{ t('vehicles.summary', { count: vehicles.length, online: onlineCount }) }}</p>
      </div>
      <div class="header-actions">
        <RouterLink class="button secondary" to="/profiles">{{ t('profiles.title') }}</RouterLink>
        <button class="button" @click="showForm = true"><AppIcon name="plus" :size="15" />{{ t('vehicles.add') }}</button>
      </div>
    </header>

    <AppModal :open="showForm" :title="t('vehicles.create')" @close="showForm=false">
      <form class="stack-form" @submit.prevent="create">
        <p class="field-hint">{{ t('vehicles.createHint') }}</p>
        <label class="field"><span>{{ t('vehicles.name') }}</span><input v-model="form.name" class="input" required autofocus /></label>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <div class="form-actions"><button class="button">{{ t('vehicles.create') }}</button><button class="button ghost" type="button" @click="showForm=false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>

    <AppModal :open="Boolean(deleteTarget)" :title="t('vehicles.deleteTitle')" @close="closeDelete">
      <div v-if="deleteTarget" class="stack-form delete-warning">
        <p class="delete-question">{{ t('vehicles.deleteQuestion', { name: deleteTarget.name }) }}</p>
        <p class="field-hint">{{ t('vehicles.deleteWarning') }}</p>
        <div class="form-actions delete-actions"><button class="button danger" type="button" :disabled="deleteBusy" @click="deleteVehicle">{{ deleteBusy ? t('vehicles.deleting') : t('vehicles.deleteVehicle') }}</button><button class="button ghost" type="button" :disabled="deleteBusy" @click="closeDelete">{{ t('common.cancel') }}</button></div>
      </div>
    </AppModal>

    <div class="catalog-toolbar">
      <label class="search-field"><AppIcon name="search" :size="16" /><span class="sr-only">{{ t('vehicles.search') }}</span><input v-model="search" :placeholder="t('vehicles.search')" /></label>
      <div class="filter-tabs">
        <button type="button" :class="{ active: filter === 'all' }" @click="filter='all'">{{ t('vehicles.all') }}</button>
        <button type="button" :class="{ active: filter === 'online' }" @click="filter='online'">{{ t('vehicles.onlineOnly') }}</button>
        <button type="button" :class="{ active: filter === 'parked' }" @click="filter='parked'">{{ t('vehicles.parkedOnly') }}</button>
      </div>
      <span v-if="vehicles.length" class="count">{{ filteredVehicles.length }} / {{ vehicles.length }}</span>
    </div>

    <p v-if="photoNotice" :class="['roster-notice', photoNotice.kind]" :role="photoNotice.kind === 'error' ? 'alert' : 'status'">{{ photoNotice.message }}</p>

    <div class="vehicle-list">
      <article v-for="vehicle in filteredVehicles" :key="vehicle.id" class="vehicle-card panel">
        <div class="vehicle-visual"><VehicleMedia :vehicle="vehicle" editable :busy="photoBusyId === vehicle.id" @select="uploadPhoto(vehicle, $event)" @remove="removePhoto(vehicle)" /></div>

        <div class="vehicle-card-body">
          <header class="vehicle-identity">
            <div>
              <h2>{{ vehicle.name }}</h2>
              <p v-if="[vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).length">{{ [vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}</p>
            </div>
            <span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t('common.online') : t('common.parked') }}</span>
          </header>

          <section class="charge-reading">
            <div>
              <span>{{ metricLabel(vehicleEnergy(vehicle), t) }}</span>
              <strong :class="{ 'is-empty': vehicleEnergy(vehicle).value === null }">{{ vehicleEnergy(vehicle).value === null ? '—' : Math.round(vehicleEnergy(vehicle).value!) }}<em v-if="vehicleEnergy(vehicle).value !== null">{{ vehicleEnergy(vehicle).unit }}</em></strong>
            </div>
            <i><b :style="{ width: `${vehicleEnergy(vehicle).progress}%` }" /></i>
          </section>

          <dl class="vehicle-meta">
            <div><dt>{{ t('vehicles.currentSpeed') }}</dt><dd :class="{ 'is-empty': vehicleSpeed(vehicle) === null }">{{ vehicleSpeed(vehicle) === null ? '—' : `${Math.round(vehicleSpeed(vehicle)!)} km/h` }}</dd></div>
            <div><dt>{{ t('vehicles.lastContact') }}</dt><dd>{{ lastContact(vehicle) }}</dd></div>
            <div class="profile-row">
              <dt>{{ t('vehicles.profile') }}</dt>
              <dd><AppSelect class="card-profile-select" compact :model-value="vehicle.vehicle_profile" :aria-label="t('vehicles.profile')" @update:model-value="assignVehicleProfile(vehicle,$event)"><option :value="null">{{ t('vehicles.noProfile') }}</option><option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profileNames[profile.id] }}</option></AppSelect></dd>
            </div>
          </dl>

          <footer>
            <RouterLink class="link-button" :to="`/vehicles/${vehicle.id}/history`">{{ t('vehicles.history') }}</RouterLink>
            <RouterLink class="link-button" to="/devices">{{ t('vehicles.tracker') }}</RouterLink>
            <button class="link-button danger" type="button" @click="deleteTarget=vehicle">{{ t('common.delete') }}</button>
          </footer>
        </div>
      </article>

      <div v-if="!filteredVehicles.length" class="empty panel">
        <h2>{{ vehicles.length ? t('vehicles.noMatch') : t('vehicles.noVehicles') }}</h2>
        <p v-if="!vehicles.length">{{ t('vehicles.noVehiclesHint') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stack-form{display:grid;gap:14px}
.stack-form .form-actions{justify-content:flex-end;margin-top:4px}
.delete-question{margin:0;font-size:14px;font-weight:500}

.catalog-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.search-field{width:min(280px,100%);height:32px;display:flex;align-items:center;gap:7px;padding:0 10px;color:var(--muted);background:var(--input);border:1px solid var(--line-strong);border-radius:var(--radius)}
.search-field:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}
.search-field input{min-width:0;width:100%;color:var(--text);background:transparent;border:0;outline:0;font-size:13px}
.filter-tabs{display:flex;gap:2px;padding:2px;background:var(--panel-2);border-radius:var(--radius)}
.filter-tabs button{height:26px;padding:0 10px;color:var(--muted);background:transparent;border:0;border-radius:4px;font-size:12px;cursor:pointer}
.filter-tabs button:hover{color:var(--text)}
.filter-tabs button.active{color:var(--text);background:var(--panel);font-weight:500;box-shadow:var(--shadow-soft)}
.catalog-toolbar .count{margin-left:auto;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}

.roster-notice{margin:0 0 14px;padding:8px 12px;border-radius:var(--radius);font-size:13px}
.roster-notice.success{color:var(--success);background:var(--success-soft)}
.roster-notice.error{color:var(--danger);background:var(--danger-soft)}

.vehicle-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(430px,1fr));gap:12px;align-items:start}
.vehicle-card{display:grid;grid-template-columns:150px minmax(0,1fr);overflow:hidden}
.vehicle-visual{min-width:0;overflow:hidden;background:var(--panel-2);border-right:1px solid var(--line);contain:size layout paint}
.vehicle-visual :deep(.vehicle-media){width:100%;height:100%;min-height:0;border:0;border-radius:0}
.vehicle-visual :deep(.vehicle-media>img),.vehicle-visual :deep(.vehicle-photo-placeholder){width:100%;height:100%}

.vehicle-card-body{min-width:0;display:flex;flex-direction:column;padding:14px 15px 10px}
.vehicle-identity{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px}
.vehicle-identity h2{margin:0;overflow:hidden;font-size:16px;font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.vehicle-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}

.charge-reading{margin-top:14px}
.charge-reading>div{position:relative;display:flex;align-items:baseline;justify-content:space-between;gap:10px}
.charge-reading span{color:var(--muted);font-size:12px}
.charge-reading strong{font-size:20px;font-weight:500;letter-spacing:-.02em;line-height:1.15;font-variant-numeric:tabular-nums}
.charge-reading strong.is-empty{position:absolute;left:50%;color:var(--muted-2);transform:translateX(-50%)}
.charge-reading em{margin-left:2px;color:var(--muted);font-size:12px;font-style:normal;font-weight:400}
.charge-reading>i{height:3px;display:block;margin-top:10px;overflow:hidden;background:var(--panel-2);border-radius:2px}
.charge-reading>i b{display:block;height:100%;background:var(--muted);border-radius:2px}

.vehicle-meta{display:grid;gap:5px;margin:14px 0 0}
.vehicle-meta>div{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:22px}
.vehicle-meta dt{color:var(--muted);font-size:12px}
.vehicle-meta dd{margin:0;overflow:hidden;font-size:12px;text-align:right;text-overflow:ellipsis;white-space:nowrap;font-variant-numeric:tabular-nums}
.profile-row dd{min-width:0}
.vehicle-meta dd.is-empty{color:var(--muted-2)}
.card-profile-select{max-width:190px;margin-left:auto}
.card-profile-select :deep(.app-select-trigger){min-height:26px;padding-block:3px;background:transparent;border-color:transparent;font-size:12px;font-weight:400}
.card-profile-select :deep(.app-select-trigger:hover){border-color:var(--line-strong)}

.vehicle-card>.vehicle-card-body>footer{display:flex;align-items:center;gap:14px;margin-top:auto;padding-top:12px}
.vehicle-card>.vehicle-card-body>footer .danger{margin-left:auto}

.empty{grid-column:1/-1}

@media(max-width:560px){
  .catalog-toolbar{flex-wrap:wrap}
  .search-field{width:100%}
  .filter-tabs{flex:1}
  .filter-tabs button{flex:1}
  .vehicle-list{grid-template-columns:1fr}
  .vehicle-card{grid-template-columns:104px minmax(0,1fr)}
  .vehicle-card-body{padding:12px 12px 8px}
}
</style>
