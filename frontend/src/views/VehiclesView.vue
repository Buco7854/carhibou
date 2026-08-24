<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import VehicleMedia from '../components/VehicleMedia.vue'

type VehicleFilter = 'all' | 'online' | 'parked'

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const showForm = ref(false)
const error = ref('')
const photoBusyId = ref('')
const photoNotice = ref<{ kind: 'error' | 'success'; message: string } | null>(null)
const search = ref('')
const filter = ref<VehicleFilter>('all')
const form = ref({ name: '', manufacturer: 'Citroën', model: 'C-Zero', year: new Date().getFullYear(), propulsion_type: 'electric', battery_nominal_capacity_kwh: 16, vehicle_profile: 'citroen-c-zero-v1', color: '#315fcf' })
const photoTypes = new Set(['image/jpeg', 'image/png', 'image/webp'])
const maxPhotoBytes = 25 * 1024 * 1024

const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const averageSoc = computed(() => {
  const values = vehicles.value.flatMap((vehicle) => typeof vehicle.state?.metrics['battery.soc'] === 'number' ? [vehicle.state.metrics['battery.soc'] as number] : [])
  return values.length ? Math.round(values.reduce((total, value) => total + value, 0) / values.length) : null
})
const filteredVehicles = computed(() => {
  const query = search.value.trim().toLocaleLowerCase()
  return vehicles.value.filter((vehicle) => {
    if (filter.value === 'online' && !vehicle.state?.online) return false
    if (filter.value === 'parked' && vehicle.state?.online) return false
    return !query || [vehicle.name, vehicle.manufacturer, vehicle.model, vehicle.year].join(' ').toLocaleLowerCase().includes(query)
  })
})

function soc(vehicle: Vehicle): number | null {
  const value = vehicle.state?.metrics['battery.soc']
  return typeof value === 'number' ? value : null
}

function speed(vehicle: Vehicle): number | null {
  const value = vehicle.state?.position?.speed ?? vehicle.state?.metrics['vehicle.speed']
  return typeof value === 'number' ? value : null
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
onMounted(load)
</script>

<template>
  <div class="page vehicles-page">
    <header class="page-header">
      <div><span class="eyebrow">{{ t('vehicles.garage') }}</span><h1>{{ t('vehicles.title') }}</h1><p>{{ t('vehicles.summary', { count: vehicles.length, online: onlineCount, soc: averageSoc ?? '—' }) }}</p></div>
      <button class="button" @click="showForm = !showForm"><AppIcon name="plus" :size="15" />{{ showForm ? t('common.close') : t('vehicles.add') }}</button>
    </header>

    <form v-if="showForm" class="panel panel-pad vehicle-form" @submit.prevent="create">
      <div class="form-heading"><div><span class="eyebrow">{{ t('vehicles.add') }}</span><h2>{{ t('vehicles.create') }}</h2></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="showForm=false">×</button></div>
      <div class="form-grid">
        <label class="field"><span>{{ t('vehicles.name') }}</span><input v-model="form.name" class="input" required /></label>
        <label class="field"><span>{{ t('vehicles.manufacturer') }}</span><input v-model="form.manufacturer" class="input" /></label>
        <label class="field"><span>{{ t('vehicles.model') }}</span><input v-model="form.model" class="input" /></label>
        <label class="field"><span>{{ t('vehicles.year') }}</span><input v-model="form.year" class="input" type="number" min="1886" max="2200" /></label>
        <label class="field"><span>{{ t('vehicles.propulsion') }}</span><select v-model="form.propulsion_type" class="select"><option>electric</option><option>hybrid</option><option>petrol</option><option>diesel</option><option>unknown</option></select></label>
        <label class="field"><span>{{ t('vehicles.capacity') }}</span><input v-model="form.battery_nominal_capacity_kwh" class="input" type="number" step=".1" min="1" /></label>
        <label class="field"><span>{{ t('vehicles.profile') }}</span><select v-model="form.vehicle_profile" class="select"><option value="citroen-c-zero-v1">{{ t('vehicles.profileExperimental') }}</option><option :value="null">{{ t('vehicles.none') }}</option></select></label>
        <label class="field"><span>{{ t('vehicles.color') }}</span><input v-model="form.color" class="input color-input" type="color" /></label>
      </div><p v-if="error" class="error" role="alert">{{ error }}</p><div class="form-actions"><button class="button">{{ t('vehicles.create') }}</button></div>
    </form>

    <section class="garage-roster panel">
      <header class="roster-toolbar">
        <div><h2>{{ t('vehicles.listTitle') }}</h2><span>{{ filteredVehicles.length }} / {{ vehicles.length }}</span></div>
        <div class="roster-controls">
          <label class="search-field"><AppIcon name="search" :size="17" /><input v-model="search" :placeholder="t('vehicles.search')" /></label>
          <div class="filter-tabs"><button :class="{ active: filter === 'all' }" @click="filter='all'">{{ t('vehicles.all') }}</button><button :class="{ active: filter === 'online' }" @click="filter='online'">{{ t('vehicles.onlineOnly') }}</button><button :class="{ active: filter === 'parked' }" @click="filter='parked'">{{ t('vehicles.parkedOnly') }}</button></div>
        </div>
      </header>
      <p v-if="photoNotice" :class="['roster-notice', photoNotice.kind]" :role="photoNotice.kind === 'error' ? 'alert' : 'status'">{{ photoNotice.message }}</p>

      <div class="vehicle-list">
        <article v-for="vehicle in filteredVehicles" :key="vehicle.id" class="vehicle-row" :style="{ '--vehicle-color': vehicle.color || '#315fcf' }">
          <div class="vehicle-identity">
            <div><h3>{{ vehicle.name }}</h3><span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t('common.online') : t('common.parked') }}</span></div>
            <p>{{ vehicle.manufacturer }} {{ vehicle.model }} · {{ vehicle.year ?? t('vehicles.yearUnknown') }}</p>
            <small><AppIcon :name="vehicle.propulsion_type === 'electric' ? 'charging' : 'vehicle'" :size="14" />{{ vehicle.propulsion_type }} · {{ vehicle.vehicle_profile || t('vehicles.noProfile') }}</small>
          </div>

          <div class="vehicle-visual"><VehicleMedia :vehicle="vehicle" editable :busy="photoBusyId === vehicle.id" @select="uploadPhoto(vehicle, $event)" @remove="removePhoto(vehicle)" /></div>

          <div class="vehicle-readings">
            <div class="charge-reading"><span>{{ t('vehicles.batteryLevel') }}</span><strong>{{ soc(vehicle) === null ? '—' : Math.round(soc(vehicle)!) }}<em>%</em></strong><i><b :style="{ width: `${soc(vehicle) ?? 0}%` }" /></i></div>
            <dl>
              <div><dt>{{ t('vehicles.currentSpeed') }}</dt><dd>{{ speed(vehicle) === null ? '—' : Math.round(speed(vehicle)!) }} <small>km/h</small></dd></div>
              <div><dt>{{ t('vehicles.lastContact') }}</dt><dd class="contact-value">{{ lastContact(vehicle) }}</dd></div>
            </dl>
          </div>

          <footer><RouterLink class="row-action" :to="`/vehicles/${vehicle.id}/history`"><AppIcon name="history" :size="15" />{{ t('vehicles.history') }}</RouterLink><RouterLink class="row-action primary" to="/devices"><AppIcon name="devices" :size="15" />{{ t('vehicles.tracker') }}</RouterLink></footer>
        </article>
        <div v-if="!filteredVehicles.length" class="empty"><h2>{{ vehicles.length ? t('vehicles.noMatch') : t('vehicles.noVehicles') }}</h2><p v-if="!vehicles.length">{{ t('vehicles.noVehiclesHint') }}</p></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.vehicle-form{margin-bottom:16px}.form-heading,.roster-toolbar{display:flex;align-items:center;justify-content:space-between;gap:16px}.form-heading{margin-bottom:17px}.form-heading h2,.roster-toolbar h2{margin:0;font-size:16px}.color-input{padding:5px}.garage-roster{overflow:hidden}.roster-toolbar{min-height:69px;padding:13px 16px;border-bottom:1px solid var(--line)}.roster-toolbar>div:first-child{display:flex;align-items:baseline;gap:9px}.roster-toolbar>div:first-child span{color:var(--muted);font-size:10px}.roster-controls{display:flex;align-items:center;gap:9px}.search-field{width:min(310px,30vw);height:39px;display:flex;align-items:center;gap:8px;padding:0 11px;color:var(--muted);background:var(--input);border:1px solid var(--line);border-radius:7px}.search-field:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}.search-field input{min-width:0;width:100%;color:var(--text);background:transparent;border:0;outline:0;font-size:11px}.filter-tabs{display:flex;gap:2px;padding:3px;background:var(--panel-2);border-radius:7px}.filter-tabs button{min-height:31px;padding:6px 10px;color:var(--muted);background:transparent;border:0;border-radius:5px;font-size:9px;font-weight:600;cursor:pointer}.filter-tabs button.active{color:var(--text);background:var(--panel);box-shadow:var(--shadow-soft)}
.roster-notice{margin:0;padding:9px 16px;border-bottom:1px solid var(--line);font-size:10px}.roster-notice.success{color:var(--success);background:var(--success-soft)}.roster-notice.error{color:var(--danger);background:color-mix(in srgb,var(--danger) 8%,var(--panel))}.vehicle-row{--vehicle-color:var(--accent);position:relative;min-height:204px;display:grid;grid-template-columns:minmax(185px,.8fr) minmax(235px,1fr) minmax(270px,1.15fr) 105px;align-items:center;gap:20px;padding:20px 17px 20px 20px;border-bottom:1px solid var(--line)}.vehicle-row:last-child{border-bottom:0}.vehicle-row::before{content:"";position:absolute;top:22px;bottom:22px;left:0;width:4px;background:var(--vehicle-color);border-radius:0 4px 4px 0}.vehicle-row:hover{background:color-mix(in srgb,var(--panel-2) 38%,transparent)}.vehicle-identity>div{display:flex;align-items:center;gap:9px}.vehicle-identity h3{margin:0;font-size:20px;font-weight:600;letter-spacing:-.035em}.vehicle-identity p{margin:8px 0;color:var(--muted);font-size:11px}.vehicle-identity small{display:flex;align-items:center;gap:6px;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:9px;line-height:1.45}.vehicle-identity small .app-icon{color:var(--vehicle-color)}.vehicle-visual{height:148px}.vehicle-readings{display:grid;grid-template-columns:125px 1fr;align-items:center;gap:22px}.charge-reading{padding-right:21px;border-right:1px solid var(--line)}.charge-reading>span{color:var(--muted);font-size:9px}.charge-reading strong{display:block;margin-top:6px;font-size:36px;font-weight:500;letter-spacing:-.06em}.charge-reading em{margin-left:3px;color:var(--vehicle-color);font-size:12px;font-style:normal}.charge-reading>i{height:5px;display:block;margin-top:12px;overflow:hidden;background:var(--panel-2);border-radius:4px}.charge-reading>i b{display:block;height:100%;background:var(--vehicle-color)}.vehicle-readings dl{margin:0}.vehicle-readings dl>div+div{margin-top:16px}.vehicle-readings dt{color:var(--muted);font-size:9px}.vehicle-readings dd{margin:5px 0 0;font-size:15px;font-weight:500}.vehicle-readings dd small{color:var(--muted);font-size:9px;font-weight:400}.vehicle-readings .contact-value{overflow:hidden;font-size:10px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}.vehicle-row footer{display:grid;gap:8px}.row-action{min-height:37px;display:flex;align-items:center;justify-content:flex-start;gap:7px;padding:8px 10px;color:var(--muted);border:1px solid var(--line);border-radius:6px;font-size:9px;font-weight:600;text-decoration:none}.row-action:hover{color:var(--text);border-color:var(--line-strong)}.row-action.primary{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 35%,var(--line))}
@media(max-width:1250px){.vehicle-row{grid-template-columns:minmax(180px,.8fr) minmax(225px,1fr) minmax(250px,1.2fr)}.vehicle-row footer{grid-column:1/-1;display:flex;justify-content:flex-end}.row-action{min-width:110px}}
@media(max-width:850px){.roster-toolbar{align-items:flex-start;flex-direction:column}.roster-controls{width:100%}.search-field{width:100%}.vehicle-row{grid-template-columns:1fr 1.15fr}.vehicle-visual{grid-column:2;grid-row:1}.vehicle-readings{grid-column:1/-1}.vehicle-row footer{grid-column:1/-1}}
@media(max-width:570px){.roster-controls{align-items:stretch;flex-direction:column}.filter-tabs{display:grid;grid-template-columns:repeat(3,1fr)}.vehicle-row{display:block;padding:20px 16px}.vehicle-visual{height:190px;margin-top:17px}.vehicle-readings{margin-top:20px}.vehicle-row footer{display:grid;grid-template-columns:1fr 1fr;margin-top:18px}.row-action{justify-content:center}.vehicle-identity small{overflow-wrap:anywhere}}
</style>
