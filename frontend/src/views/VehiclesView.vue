<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'
import VehicleMedia from '../components/VehicleMedia.vue'
import { chargingState, formatMetricNumber, headlineReading, isPercentage, metricLabel, metricNumber, trackerStatus, vehicleActivity } from '../vehicleDisplay'

type VehicleFilter = 'all' | 'online' | 'parked'

interface VehicleForm {
  name: string
  profileId: string | null
}

const vehicles = ref<Vehicle[]>([])
const profiles = ref<VehicleProfile[]>([])
const { locale, t } = useI18n()
const showForm = ref(false)
const deleteTarget = ref<Vehicle | null>(null)
const deleteBusy = ref(false)
const error = ref('')
const photoBusyId = ref('')
const photoNotice = ref<{ kind: 'error' | 'success'; message: string } | null>(null)
const search = ref('')
const filter = ref<VehicleFilter>('all')
const emptyForm = (): VehicleForm => ({ name: '', profileId: null })
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

function headline(vehicle: Vehicle) { return headlineReading(vehicle) }
function charging(vehicle: Vehicle) { return chargingState(vehicle) }
function headlineValue(vehicle: Vehicle): string {
  const reading = headlineReading(vehicle)
  if (!reading || reading.value === null) return ''
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value, reading)
}
function headlineProgress(vehicle: Vehicle): number | null {
  const reading = headlineReading(vehicle)
  if (!reading || !isPercentage(reading)) return null
  return Math.min(100, Math.max(0, Number(reading.value)))
}
function vehicleSpeed(vehicle: Vehicle): number | null { return metricNumber(vehicle, 'vehicle.speed') }
/** Relative time reads faster than a timestamp when the only question is "recently?". */
function lastContact(vehicle: Vehicle): string {
  if (!vehicle.state) return t('common.never')
  const elapsed = (Date.now() - new Date(vehicle.state.updated_at).getTime()) / 1000
  const format = new Intl.RelativeTimeFormat(locale.value, { numeric: 'auto' })
  const [amount, unit]: [number, Intl.RelativeTimeFormatUnit] =
    elapsed < 60 ? [elapsed, 'second']
    : elapsed < 3600 ? [elapsed / 60, 'minute']
    : elapsed < 86_400 ? [elapsed / 3600, 'hour']
    : [elapsed / 86_400, 'day']
  return format.format(-Math.round(amount), unit)
}

/**
 * The short facts worth reading at a glance, and only the ones this vehicle
 * reports. Units carry the meaning, so the labels that made every card read like
 * a specification table are gone.
 */
function vehicleFacts(vehicle: Vehicle): string[] {
  const facts: string[] = []
  const speed = vehicleSpeed(vehicle)
  if (speed !== null) facts.push(`${Math.round(speed)} km/h`)
  const state = chargingState(vehicle)
  if (state.active) facts.push(state.power === null ? t('vehicles.charging') : `${t('vehicles.charging')} ${state.power.toFixed(1)} kW`)
  else if (state.active === false) facts.push(t('vehicles.notCharging'))
  return facts
}

async function load(): Promise<void> {
  ;[vehicles.value, profiles.value] = await Promise.all([
    api<Vehicle[]>('/vehicles'),
    api<VehicleProfile[]>('/vehicle-profiles'),
  ])
}
async function create(): Promise<void> {
  error.value = ''
  const payload = { name: form.value.name.trim(), vehicle_profile: form.value.profileId }
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
        <label class="field"><span>{{ t('vehicles.profile') }}</span>
          <AppSelect v-model="form.profileId" :aria-label="t('vehicles.profile')">
            <option :value="null">{{ t('vehicles.noProfile') }}</option>
            <option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profile.name }}</option>
          </AppSelect>
          <small class="field-hint">{{ t('vehicles.profileHint') }}</small>
        </label>
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
            <span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t(`dashboard.activity.${vehicleActivity(vehicle)}`) : t(`dashboard.tracker.${trackerStatus(vehicle)}`) }}</span>
          </header>

          <section class="charge-reading">
            <template v-if="headline(vehicle)">
              <div class="reading-row">
                <span>{{ metricLabel(headline(vehicle)!, t) }}</span>
                <strong>{{ headlineValue(vehicle) }}<em v-if="headline(vehicle)!.unit">{{ headline(vehicle)!.unit }}</em></strong>
              </div>
              <i v-if="headlineProgress(vehicle) !== null"><b :class="{ 'is-charging':charging(vehicle).active }" :style="{ width: `${headlineProgress(vehicle)}%` }" /></i>
            </template>
            <p v-else class="awaiting">{{ t('vehicles.awaitingTelemetry') }}</p>
          </section>

          <p class="vehicle-facts">
            <span v-for="(fact, index) in vehicleFacts(vehicle)" :key="fact" :class="{ 'is-charging':index === 1 && charging(vehicle).active }">{{ fact }}</span>
            <small>{{ lastContact(vehicle) }}</small>
          </p>
        </div>

        <footer>
          <AppSelect class="card-profile-select" compact :model-value="vehicle.vehicle_profile" :aria-label="t('vehicles.profile')" @update:model-value="assignVehicleProfile(vehicle,$event)"><option :value="null">{{ t('vehicles.noProfile') }}</option><option v-for="profile in profiles" :key="profile.id" :value="profile.id">{{ profileNames[profile.id] }}</option></AppSelect>
          <RouterLink class="link-button" :to="`/vehicles/${vehicle.id}/history`">{{ t('vehicles.history') }}</RouterLink>
          <RouterLink class="link-button" to="/devices">{{ t('vehicles.tracker') }}</RouterLink>
          <button class="link-button danger" type="button" @click="deleteTarget=vehicle">{{ t('common.delete') }}</button>
        </footer>
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

/* Vehicle-status cards lead with the vehicle: image on top, then identity, then the
   one reading that matters, the way Tesla's app and the Home Assistant vehicle cards
   arrange it. A side thumbnail belongs to a list row, not a card. */
.vehicle-list{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:14px}
.vehicle-card{display:flex;flex-direction:column;overflow:hidden}

/* A fixed ratio keeps the card the same height before and after a photo is added. */
.vehicle-visual{aspect-ratio:16/9;min-width:0;flex:none;overflow:hidden;background:var(--panel-2);border-bottom:1px solid var(--line);contain:size layout paint}
.vehicle-visual :deep(.vehicle-media){width:100%;height:100%;min-height:0;border:0;border-radius:0}
.vehicle-visual :deep(.vehicle-media>img),.vehicle-visual :deep(.vehicle-photo-placeholder){width:100%;height:100%}

.vehicle-card-body{min-width:0;flex:1;padding:14px 16px 16px}
.vehicle-identity{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px}
.vehicle-identity h2{margin:0;overflow:hidden;font-size:16px;font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.vehicle-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}

.charge-reading{min-height:40px;margin-top:16px}
.reading-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.reading-row span{color:var(--muted);font-size:12px}
.reading-row strong{font-size:22px;font-weight:500;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.reading-row em{margin-left:2px;color:var(--muted);font-size:12px;font-style:normal;font-weight:400}
.charge-reading>i{height:4px;display:block;margin-top:8px;overflow:hidden;background:var(--panel-2);border-radius:2px}
.charge-reading>i b{display:block;height:100%;background:var(--muted);border-radius:2px}
.charge-reading>i b.is-charging{background:var(--success)}
.awaiting{margin:0;color:var(--muted-2);font-size:13px}

.vehicle-facts{display:flex;align-items:baseline;flex-wrap:wrap;gap:2px 8px;margin:12px 0 0;font-size:13px;font-variant-numeric:tabular-nums}
.vehicle-facts span+span::before{content:"·";margin-right:8px;color:var(--muted-2)}
.vehicle-facts .is-charging{color:var(--success)}
.vehicle-facts small{flex-basis:100%;color:var(--muted);font-size:12px}

.vehicle-card>footer{display:flex;align-items:center;gap:14px;padding:9px 16px;border-top:1px solid var(--line)}
.card-profile-select{margin-right:auto;max-width:150px}
.card-profile-select :deep(.app-select-trigger){min-height:26px;padding:3px 6px 3px 8px;background:transparent;border-color:transparent;color:var(--muted);font-size:12px}
.card-profile-select :deep(.app-select-trigger:hover){color:var(--text);border-color:var(--line-strong)}

.empty{grid-column:1/-1}

@media(max-width:560px){
  .catalog-toolbar{flex-wrap:wrap}
  .search-field{width:100%}
  .filter-tabs{flex:1}
  .filter-tabs button{flex:1}
  .vehicle-list{grid-template-columns:1fr}
  .vehicle-card>footer{gap:12px;padding:9px 13px}
  .vehicle-card-body{padding:13px 14px 15px}
}
</style>
