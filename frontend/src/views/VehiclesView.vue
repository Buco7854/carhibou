<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import VehicleMedia from '../components/VehicleMedia.vue'
import { energySummary, metricLabel, metricNumber } from '../vehicleDisplay'

type VehicleFilter = 'all' | 'online' | 'parked'
type PropulsionType = 'electric' | 'hybrid' | 'petrol' | 'diesel' | 'unknown'

interface VehicleForm {
  name: string
  manufacturer: string
  model: string
  year: number
  propulsion_type: PropulsionType
  battery_nominal_capacity_kwh: number | null
  vehicle_profile: string | null
  color: string
}

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const showForm = ref(false)
const error = ref('')
const photoBusyId = ref('')
const photoNotice = ref<{ kind: 'error' | 'success'; message: string } | null>(null)
const search = ref('')
const filter = ref<VehicleFilter>('all')
const form = ref<VehicleForm>({ name: '', manufacturer: 'Citroën', model: 'C-Zero', year: new Date().getFullYear(), propulsion_type: 'electric', battery_nominal_capacity_kwh: 16, vehicle_profile: 'citroen-c-zero-v1', color: '#315fcf' })
const photoTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
const maxPhotoBytes = 25 * 1024 * 1024
const propulsionTypes: PropulsionType[] = ['electric', 'hybrid', 'petrol', 'diesel', 'unknown']

const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const averageEnergy = computed(() => {
  const values = vehicles.value.flatMap((vehicle) => {
    const value = energySummary(vehicle).value
    return typeof value === 'number' ? [value] : []
  })
  return values.length ? Math.round(values.reduce((total, value) => total + value, 0) / values.length) : null
})
const hasTractionBattery = computed(() => ['electric', 'hybrid'].includes(form.value.propulsion_type))
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
function propulsionIcon(type: string): string {
  if (type === 'electric') return 'charging'
  if (type === 'petrol' || type === 'diesel') return 'fuel'
  return type === 'hybrid' ? 'energy' : 'vehicle'
}
function propulsionLabel(type: string): string {
  return ['electric', 'hybrid', 'petrol', 'diesel', 'unknown'].includes(type)
    ? t(`vehicles.propulsionTypes.${type}`)
    : type
}

function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? new Date(vehicle.state.updated_at).toLocaleString() : t('common.never')
}

async function load(): Promise<void> { vehicles.value = await api<Vehicle[]>('/vehicles') }
async function create(): Promise<void> {
  error.value = ''
  try { await api('/vehicles', { method: 'POST', body: JSON.stringify(form.value) }); showForm.value = false; await load() }
  catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
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
watch(() => form.value.propulsion_type, (type) => {
  if (type === 'electric' || type === 'hybrid') return
  form.value.battery_nominal_capacity_kwh = null
  if (form.value.vehicle_profile === 'citroen-c-zero-v1') form.value.vehicle_profile = null
})
onMounted(load)
</script>

<template>
  <div class="page vehicles-page">
    <header class="page-header">
      <div><span class="eyebrow">{{ t('vehicles.garage') }}</span><h1>{{ t('vehicles.title') }}</h1><p>{{ t('vehicles.summary', { count: vehicles.length, online: onlineCount, energy: averageEnergy ?? '—' }) }}</p></div>
      <button class="button" @click="showForm = !showForm"><AppIcon name="plus" :size="15" />{{ showForm ? t('common.close') : t('vehicles.add') }}</button>
    </header>

    <form v-if="showForm" class="panel panel-pad vehicle-form" @submit.prevent="create">
      <div class="form-heading"><div><span class="eyebrow">{{ t('vehicles.add') }}</span><h2>{{ t('vehicles.create') }}</h2></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="showForm=false">×</button></div>
      <div class="form-grid">
        <label class="field"><span>{{ t('vehicles.name') }}</span><input v-model="form.name" class="input" required /></label>
        <label class="field"><span>{{ t('vehicles.manufacturer') }}</span><input v-model="form.manufacturer" class="input" /></label>
        <label class="field"><span>{{ t('vehicles.model') }}</span><input v-model="form.model" class="input" /></label>
        <label class="field"><span>{{ t('vehicles.year') }}</span><input v-model.number="form.year" class="input" type="number" min="1886" max="2200" /></label>
        <label class="field"><span>{{ t('vehicles.propulsion') }}</span><select v-model="form.propulsion_type" class="select"><option v-for="type in propulsionTypes" :key="type" :value="type">{{ t(`vehicles.propulsionTypes.${type}`) }}</option></select></label>
        <label v-if="hasTractionBattery" class="field"><span>{{ t('vehicles.capacity') }}</span><input v-model.number="form.battery_nominal_capacity_kwh" class="input" type="number" step=".1" min="1" /></label>
        <label class="field"><span>{{ t('vehicles.profile') }}</span><select v-model="form.vehicle_profile" class="select"><option value="citroen-c-zero-v1">{{ t('vehicles.profileExperimental') }}</option><option :value="null">{{ t('vehicles.none') }}</option></select></label>
        <label class="field"><span>{{ t('vehicles.color') }}</span><input v-model="form.color" class="input color-input" type="color" /></label>
      </div><p v-if="error" class="error" role="alert">{{ error }}</p><div class="form-actions"><button class="button">{{ t('vehicles.create') }}</button></div>
    </form>

    <section v-if="vehicles.length" class="garage-overview panel" aria-labelledby="garage-overview-title">
      <header class="overview-heading">
        <span class="eyebrow">{{ t('vehicles.garage') }}</span>
        <h2 id="garage-overview-title">{{ t('vehicles.overview') }}</h2>
        <p>{{ t('vehicles.overviewHint') }}</p>
      </header>
      <div class="overview-stat">
        <span class="stat-icon"><AppIcon name="vehicle" :size="18" /></span>
        <div><small>{{ t('vehicles.totalVehicles') }}</small><strong>{{ vehicles.length }}</strong></div>
      </div>
      <div class="overview-stat">
        <span class="stat-icon"><AppIcon name="signal" :size="18" /></span>
        <div><small>{{ t('vehicles.onlineVehicles') }}</small><strong>{{ onlineCount }}</strong></div>
      </div>
      <div class="overview-stat">
        <span class="stat-icon"><AppIcon name="energy" :size="18" /></span>
        <div><small>{{ t('vehicles.averageBattery') }}</small><strong>{{ averageEnergy ?? '—' }}<em v-if="averageEnergy !== null">%</em></strong></div>
      </div>
    </section>

    <section class="vehicle-catalog" aria-labelledby="vehicle-catalog-title">
      <header class="catalog-toolbar panel">
        <div class="catalog-heading">
          <div><h2 id="vehicle-catalog-title">{{ t('vehicles.listTitle') }}</h2><p>{{ t('vehicles.listHint') }}</p></div>
          <span>{{ filteredVehicles.length }} / {{ vehicles.length }}</span>
        </div>
        <div class="roster-controls">
          <label class="search-field"><AppIcon name="search" :size="17" /><span class="sr-only">{{ t('vehicles.search') }}</span><input v-model="search" :placeholder="t('vehicles.search')" /></label>
          <div class="filter-tabs"><button type="button" :class="{ active: filter === 'all' }" @click="filter='all'">{{ t('vehicles.all') }}</button><button type="button" :class="{ active: filter === 'online' }" @click="filter='online'">{{ t('vehicles.onlineOnly') }}</button><button type="button" :class="{ active: filter === 'parked' }" @click="filter='parked'">{{ t('vehicles.parkedOnly') }}</button></div>
        </div>
      </header>
      <p v-if="photoNotice" :class="['roster-notice', 'panel', photoNotice.kind]" :role="photoNotice.kind === 'error' ? 'alert' : 'status'">{{ photoNotice.message }}</p>

      <div class="vehicle-list">
        <article v-for="vehicle in filteredVehicles" :key="vehicle.id" class="vehicle-card panel" :style="{ '--vehicle-color': vehicle.color || '#315fcf' }">
          <div class="vehicle-visual"><VehicleMedia :vehicle="vehicle" editable :busy="photoBusyId === vehicle.id" @select="uploadPhoto(vehicle, $event)" @remove="removePhoto(vehicle)" /></div>

          <div class="vehicle-card-body">
            <header class="vehicle-identity">
              <div><h3>{{ vehicle.name }}</h3><p>{{ [vehicle.manufacturer, vehicle.model, vehicle.year ?? t('vehicles.yearUnknown')].filter(Boolean).join(' · ') }}</p></div>
              <span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t('common.online') : t('common.parked') }}</span>
            </header>

            <div class="vehicle-readings">
              <section class="charge-reading">
                <div><span><AppIcon :name="vehicleEnergy(vehicle).icon" :size="15" />{{ metricLabel(vehicleEnergy(vehicle), t) }}</span><strong :class="{ 'is-empty': vehicleEnergy(vehicle).value === null }">{{ vehicleEnergy(vehicle).value === null ? '—' : Math.round(vehicleEnergy(vehicle).value!) }}<em v-if="vehicleEnergy(vehicle).value !== null">{{ vehicleEnergy(vehicle).unit }}</em></strong></div>
                <i><b :style="{ width: `${vehicleEnergy(vehicle).progress}%` }" /></i>
              </section>
              <dl>
                <div><dt><AppIcon name="speed" :size="14" />{{ t('vehicles.currentSpeed') }}</dt><dd :class="{ 'is-empty': vehicleSpeed(vehicle) === null }">{{ vehicleSpeed(vehicle) === null ? '—' : Math.round(vehicleSpeed(vehicle)!) }} <small v-if="vehicleSpeed(vehicle) !== null">km/h</small></dd></div>
                <div><dt><AppIcon name="history" :size="14" />{{ t('vehicles.lastContact') }}</dt><dd class="contact-value">{{ lastContact(vehicle) }}</dd></div>
              </dl>
            </div>

            <div class="vehicle-profile"><AppIcon :name="propulsionIcon(vehicle.propulsion_type)" :size="14" /><span>{{ propulsionLabel(vehicle.propulsion_type) }}</span><i /> <span>{{ vehicle.vehicle_profile || t('vehicles.noProfile') }}</span></div>
          </div>

          <footer><RouterLink class="row-action" :to="`/vehicles/${vehicle.id}/history`"><AppIcon name="history" :size="15" />{{ t('vehicles.history') }}</RouterLink><RouterLink class="row-action primary" to="/devices"><AppIcon name="devices" :size="15" />{{ t('vehicles.tracker') }}</RouterLink></footer>
        </article>
        <div v-if="!filteredVehicles.length" class="empty panel"><h2>{{ vehicles.length ? t('vehicles.noMatch') : t('vehicles.noVehicles') }}</h2><p v-if="!vehicles.length">{{ t('vehicles.noVehiclesHint') }}</p></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.vehicle-form{margin-bottom:16px}.form-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:17px}.form-heading h2{margin:0;font-size:16px}.color-input{padding:5px}.garage-overview{display:grid;grid-template-columns:minmax(230px,1.35fr) repeat(3,minmax(145px,1fr));margin-bottom:14px;overflow:hidden}.overview-heading{padding:20px 21px;border-right:1px solid var(--line)}.overview-heading .eyebrow{margin-bottom:5px}.overview-heading h2{margin:0;font-size:16px}.overview-heading p{margin:6px 0 0;color:var(--muted);font-size:9px;line-height:1.45}.overview-stat{min-width:0;display:grid;grid-template-columns:38px 1fr;align-items:center;gap:11px;padding:18px;border-right:1px solid var(--line)}.overview-stat:last-child{border-right:0}.stat-icon{width:38px;height:38px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:8px}.overview-stat small,.overview-stat strong{display:block}.overview-stat small{overflow:hidden;color:var(--muted);font-size:9px;text-overflow:ellipsis;white-space:nowrap}.overview-stat strong{margin-top:5px;font-size:25px;font-weight:500;letter-spacing:-.04em}.overview-stat em{margin-left:2px;color:var(--muted);font-size:10px;font-style:normal}.vehicle-catalog{display:grid;gap:14px}.catalog-toolbar{min-height:74px;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:13px 15px 13px 18px}.catalog-heading{display:flex;align-items:center;gap:10px}.catalog-heading h2{margin:0;font-size:16px}.catalog-heading p{margin:4px 0 0;color:var(--muted);font-size:9px}.catalog-heading>span{align-self:flex-start;padding:3px 6px;color:var(--text);background:var(--panel-2);border-radius:5px;font:500 8px "IBM Plex Mono",monospace}.roster-controls{display:flex;align-items:center;gap:9px}.search-field{width:min(310px,28vw);height:40px;display:flex;align-items:center;gap:8px;padding:0 11px;color:var(--muted);background:var(--input);border:1px solid var(--line);border-radius:7px}.search-field:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}.search-field input{min-width:0;width:100%;color:var(--text);background:transparent;border:0;outline:0;font-size:11px}.filter-tabs{display:flex;gap:2px;padding:3px;background:var(--panel-2);border-radius:7px}.filter-tabs button{min-height:33px;padding:6px 11px;color:var(--text);background:transparent;border:0;border-radius:5px;font-size:9px;font-weight:600;cursor:pointer}.filter-tabs button.active{color:var(--text);background:var(--panel);box-shadow:var(--shadow-soft)}.roster-notice{margin:0;padding:10px 14px;font-size:10px}.roster-notice.success{color:var(--success);background:var(--success-soft)}.roster-notice.error{color:var(--danger);background:color-mix(in srgb,var(--danger) 8%,var(--panel))}.vehicle-list{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.vehicle-card{--vehicle-color:var(--accent);min-width:0;display:flex;overflow:hidden;flex-direction:column}.vehicle-visual{aspect-ratio:16/8.7;background:var(--panel-2);border-bottom:1px solid var(--line)}.vehicle-visual :deep(.vehicle-media){min-height:0;border:0;border-radius:0}.vehicle-card-body{display:flex;flex:1;flex-direction:column;padding:20px 19px 0}.vehicle-identity{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:12px}.vehicle-identity h3{margin:0;font-size:20px;font-weight:600;letter-spacing:-.035em}.vehicle-identity p{margin:5px 0 0;overflow:hidden;color:var(--muted);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.vehicle-card .status{color:var(--text)}.vehicle-readings{margin-top:24px}.charge-reading{max-width:310px}.charge-reading>div{position:relative;display:grid;grid-template-columns:minmax(0,1fr) 64px;align-items:end;gap:12px}.charge-reading span,.vehicle-readings dt{display:flex;align-items:center;gap:6px;color:var(--muted);font-size:9px}.charge-reading span .app-icon,.vehicle-readings dt .app-icon{color:var(--vehicle-color)}.charge-reading strong{text-align:right;font-size:30px;font-weight:500;letter-spacing:-.055em;line-height:1}.charge-reading strong.is-empty{position:absolute;left:50%;text-align:center;transform:translateX(-50%)}.charge-reading em{margin-left:3px;color:var(--vehicle-color);font-size:11px;font-style:normal}.charge-reading>i{height:5px;display:block;margin-top:12px;overflow:hidden;background:var(--panel-2);border-radius:4px}.charge-reading>i b{display:block;height:100%;background:var(--vehicle-color)}.vehicle-readings dl{display:flex;align-items:center;flex-wrap:wrap;gap:10px 24px;margin:16px 0 0}.vehicle-readings dl>div{min-width:0;display:flex;align-items:center;gap:7px}.vehicle-readings dd{margin:0;overflow:hidden;font-size:10px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.vehicle-readings dd.is-empty{min-width:40px;text-align:center}.vehicle-readings dd small{color:var(--muted);font-size:8px;font-weight:400}.vehicle-readings .contact-value{font-size:9px;line-height:1.5;white-space:normal}.vehicle-profile{min-height:32px;display:flex;align-items:center;gap:7px;margin-top:12px;overflow:hidden;color:var(--muted);font:500 8px "IBM Plex Mono",monospace}.vehicle-profile .app-icon{color:var(--vehicle-color)}.vehicle-profile span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vehicle-profile i{width:3px;height:3px;flex:none;background:var(--muted-2);border-radius:50%}.vehicle-card>footer{display:flex;justify-content:flex-end;gap:8px;padding:7px 19px 18px}.row-action{min-width:112px;min-height:37px;display:flex;align-items:center;justify-content:center;gap:7px;padding:7px 11px;color:var(--muted);border:1px solid var(--line);border-radius:7px;font-size:9px;font-weight:600;text-decoration:none}.row-action:hover{color:var(--text);border-color:var(--line-strong)}.row-action.primary{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 38%,var(--line))}.empty{grid-column:1/-1}
@media(max-width:1120px){.garage-overview{grid-template-columns:repeat(3,1fr)}.overview-heading{grid-column:1/-1;padding-block:16px;border-right:0;border-bottom:1px solid var(--line)}.vehicle-list{grid-template-columns:1fr}.vehicle-visual{aspect-ratio:16/7.5}}
@media(max-width:760px){.catalog-toolbar{align-items:stretch;flex-direction:column}.roster-controls{width:100%}.search-field{width:100%}.vehicle-visual{aspect-ratio:16/8.5}}
@media(max-width:560px){.garage-overview{grid-template-columns:1fr}.overview-heading{grid-column:auto}.overview-stat{grid-template-columns:34px 1fr;padding:13px 16px;border-right:0;border-bottom:1px solid var(--line)}.overview-stat:last-child{border-bottom:0}.stat-icon{width:34px;height:34px}.overview-stat div{display:flex;align-items:baseline;justify-content:space-between;gap:12px}.overview-stat strong{margin:0;font-size:20px}.roster-controls{flex-direction:column}.filter-tabs{display:grid;grid-template-columns:repeat(3,1fr)}.vehicle-visual{aspect-ratio:4/3}.vehicle-card-body{padding:18px 16px 0}.vehicle-readings{margin-top:22px}.charge-reading{max-width:none}.vehicle-readings dl{align-items:flex-start;flex-direction:column;gap:10px}.vehicle-card>footer{justify-content:stretch;padding:7px 16px 16px}.row-action{min-width:0;flex:1}.vehicle-identity{grid-template-columns:minmax(0,1fr)}.vehicle-identity>.status{grid-column:1;margin-top:3px}}
</style>
