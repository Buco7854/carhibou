<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import VehicleSilhouette from '../components/VehicleSilhouette.vue'

type VehicleFilter = 'all' | 'online' | 'parked'

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const selectedId = ref('')
const showForm = ref(false)
const error = ref('')
const search = ref('')
const filter = ref<VehicleFilter>('all')
const form = ref({ name: '', manufacturer: 'Citroën', model: 'C-Zero', year: new Date().getFullYear(), propulsion_type: 'electric', battery_nominal_capacity_kwh: 16, vehicle_profile: 'citroen-c-zero-v1', color: '#137d78' })

const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const averageSoc = computed(() => {
  const values = vehicles.value.flatMap((vehicle) => typeof vehicle.state?.metrics['battery.soc'] === 'number' ? [vehicle.state.metrics['battery.soc'] as number] : [])
  return values.length ? Math.round(values.reduce((total, value) => total + value, 0) / values.length) : null
})
const selected = computed(() => vehicles.value.find((vehicle) => vehicle.id === selectedId.value) ?? vehicles.value[0])
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

async function load(): Promise<void> {
  vehicles.value = await api<Vehicle[]>('/vehicles')
  if (!selectedId.value && vehicles.value[0]) selectedId.value = vehicles.value[0].id
}

async function create(): Promise<void> {
  error.value = ''
  try {
    const created = await api<Vehicle>('/vehicles', { method: 'POST', body: JSON.stringify(form.value) })
    selectedId.value = created.id
    showForm.value = false
    await load()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('common.error') }
}
onMounted(load)
</script>

<template>
  <div class="page vehicles-page">
    <header class="page-header">
      <div><span class="eyebrow">02 / {{ t('vehicles.garage') }}</span><h1>{{ t('vehicles.title') }}</h1></div>
      <button class="button" @click="showForm = !showForm">{{ showForm ? t('common.close') : t('vehicles.add') }}</button>
    </header>

    <form v-if="showForm" class="panel panel-pad vehicle-form" @submit.prevent="create">
      <div class="form-heading"><div><span class="eyebrow">{{ t('vehicles.newRecord') }}</span><h2>{{ t('vehicles.create') }}</h2></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="showForm=false">×</button></div>
      <div class="form-grid">
        <div class="field"><label>{{ t('vehicles.name') }}</label><input v-model="form.name" class="input" required /></div>
        <div class="field"><label>{{ t('vehicles.manufacturer') }}</label><input v-model="form.manufacturer" class="input" /></div>
        <div class="field"><label>{{ t('vehicles.model') }}</label><input v-model="form.model" class="input" /></div>
        <div class="field"><label>{{ t('vehicles.year') }}</label><input v-model="form.year" class="input" type="number" min="1886" max="2200" /></div>
        <div class="field"><label>{{ t('vehicles.propulsion') }}</label><select v-model="form.propulsion_type" class="select"><option>electric</option><option>hybrid</option><option>petrol</option><option>diesel</option><option>unknown</option></select></div>
        <div class="field"><label>{{ t('vehicles.capacity') }}</label><input v-model="form.battery_nominal_capacity_kwh" class="input" type="number" step=".1" min="1" /></div>
        <div class="field"><label>{{ t('vehicles.profile') }}</label><select v-model="form.vehicle_profile" class="select"><option value="citroen-c-zero-v1">{{ t('vehicles.profileExperimental') }}</option><option :value="null">{{ t('vehicles.none') }}</option></select></div>
        <div class="field"><label>{{ t('vehicles.color') }}</label><input v-model="form.color" class="input color-input" type="color" /></div>
      </div><p v-if="error" class="error">{{ error }}</p><div class="form-actions"><button class="button">{{ t('vehicles.create') }}</button></div>
    </form>

    <section v-if="vehicles.length" class="garage-register">
      <div><span>{{ t('vehicles.registered') }}</span><strong>{{ vehicles.length }}</strong></div>
      <div><span>{{ t('vehicles.transmitting') }}</span><strong>{{ onlineCount }}</strong></div>
      <div><span>{{ t('vehicles.fleetCharge') }}</span><strong>{{ averageSoc ?? '—' }}<em>%</em></strong></div>
      <p>{{ t('vehicles.registerHint') }}</p>
    </section>

    <section v-if="vehicles.length" class="manifest-shell panel">
      <header class="manifest-toolbar">
        <div><span class="eyebrow">{{ t('vehicles.manifest') }}</span><h2>{{ t('vehicles.listTitle') }}</h2></div>
        <div class="catalog-controls"><label class="search-field"><AppIcon name="search" :size="16" /><input v-model="search" :placeholder="t('vehicles.search')" /></label><div class="filter-tabs"><button :class="{ active: filter === 'all' }" @click="filter='all'">{{ t('vehicles.all') }}</button><button :class="{ active: filter === 'online' }" @click="filter='online'">{{ t('vehicles.onlineOnly') }}</button><button :class="{ active: filter === 'parked' }" @click="filter='parked'">{{ t('vehicles.parkedOnly') }}</button></div></div>
      </header>
      <div class="manifest-layout">
        <div class="vehicle-manifest vehicle-grid">
          <button v-for="(vehicle, index) in filteredVehicles" :key="vehicle.id" :class="['manifest-row', { active: vehicle.id === selected?.id }]" @click="selectedId = vehicle.id">
            <span class="manifest-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="row-vehicle"><strong>{{ vehicle.name }}</strong><small>{{ vehicle.manufacturer }} {{ vehicle.model }} · {{ vehicle.year ?? t('vehicles.yearUnknown') }}</small></span>
            <span class="row-soc"><small>{{ t('dashboard.soc') }}</small><strong>{{ soc(vehicle) === null ? '—' : Math.round(soc(vehicle)!) }}%</strong><i><b :style="{ width: `${soc(vehicle) ?? 0}%` }" /></i></span>
            <span :class="['row-state', { online: vehicle.state?.online }]" />
          </button>
          <div v-if="!filteredVehicles.length" class="empty catalog-empty"><h2>{{ t('vehicles.noMatch') }}</h2></div>
        </div>

        <article v-if="selected" class="vehicle-dossier">
          <header><div><span class="eyebrow">{{ t('vehicles.selectedRecord') }}</span><h2>{{ selected.name }}</h2><p>{{ selected.manufacturer }} {{ selected.model }} / {{ selected.propulsion_type }}</p></div><span :class="['status',{online:selected.state?.online}]">{{ selected.state?.online ? t('common.online') : t('common.parked') }}</span></header>
          <div class="dossier-visual"><VehicleSilhouette :color="selected.color || '#137d78'" /><span class="profile-stamp">{{ selected.vehicle_profile ?? t('vehicles.noProfile') }}</span></div>
          <div class="dossier-snapshot">
            <div class="dossier-battery"><span>{{ t('vehicles.batteryLevel') }}</span><strong>{{ soc(selected) === null ? '—' : Math.round(soc(selected)!) }}<em>%</em></strong><i><b :style="{ width: `${soc(selected) ?? 0}%` }" /></i></div>
            <dl>
              <div><dt>{{ t('vehicles.currentSpeed') }}</dt><dd>{{ speed(selected) === null ? '—' : Math.round(speed(selected)!) }} <em>km/h</em></dd></div>
              <div><dt>{{ t('vehicles.lastContact') }}</dt><dd class="contact-value">{{ lastContact(selected) }}</dd></div>
              <div><dt>{{ t('vehicles.capacity') }}</dt><dd>{{ selected.battery_nominal_capacity_kwh ?? '—' }} <em>kWh</em></dd></div>
            </dl>
          </div>
          <footer><RouterLink class="button secondary" :to="`/vehicles/${selected.id}/history`"><AppIcon name="history" :size="14" />{{ t('vehicles.history') }}</RouterLink><RouterLink class="button" to="/devices"><AppIcon name="devices" :size="14" />{{ t('vehicles.tracker') }}</RouterLink></footer>
        </article>
      </div>
    </section>

    <section v-else class="panel empty"><h2>{{ t('vehicles.noVehicles') }}</h2><p>{{ t('vehicles.noVehiclesHint') }}</p></section>
  </div>
</template>

<style scoped>
.vehicle-form{margin-bottom:17px}.form-heading{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:18px}.form-heading h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:26px;text-transform:uppercase}.color-input{padding:5px}
.garage-register{min-height:72px;display:grid;grid-template-columns:130px 130px 150px 1fr;align-items:center;margin-bottom:13px;border-block:1px solid var(--line-strong)}.garage-register>div{padding:10px 20px;border-right:1px solid var(--line)}.garage-register span,.garage-register strong{display:block}.garage-register span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;letter-spacing:.05em;text-transform:uppercase}.garage-register strong{margin-top:3px;font-family:"Barlow Condensed",sans-serif;font-size:27px;font-weight:500}.garage-register strong em{margin-left:2px;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:8px;font-style:normal}.garage-register p{justify-self:end;margin:0;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}
.manifest-shell{overflow:hidden}.manifest-toolbar{min-height:76px;display:flex;align-items:center;justify-content:space-between;gap:20px;padding:14px 17px;border-bottom:1px solid var(--line)}.manifest-toolbar h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:22px;line-height:1;text-transform:uppercase}.catalog-controls{display:flex;align-items:center;gap:9px}.search-field{width:min(280px,28vw);height:37px;display:flex;align-items:center;gap:8px;padding:0 10px;color:var(--muted);border:1px solid var(--line);background:var(--input)}.search-field:focus-within{border-color:var(--petrol);box-shadow:0 0 0 3px var(--petrol-soft)}.search-field input{min-width:0;width:100%;color:var(--text);background:transparent;border:0;outline:0;font-size:10px}.filter-tabs{display:flex;border:1px solid var(--line);background:var(--panel-2)}.filter-tabs button{padding:8px 10px;color:var(--muted);background:transparent;border:0;border-right:1px solid var(--line);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase;cursor:pointer}.filter-tabs button:last-child{border-right:0}.filter-tabs button.active{color:var(--ink-inverse);background:var(--text)}
.manifest-layout{display:grid;grid-template-columns:minmax(400px,.85fr) minmax(420px,1.15fr);min-height:570px}.vehicle-manifest{border-right:1px solid var(--line);background:var(--panel-2)}.manifest-row{position:relative;width:100%;min-height:89px;display:grid;grid-template-columns:30px minmax(130px,1fr) 96px 8px;align-items:center;gap:11px;padding:12px 16px;color:var(--muted);background:transparent;border:0;border-bottom:1px solid var(--line);text-align:left;cursor:pointer}.manifest-row:hover{color:var(--text);background:color-mix(in srgb,var(--panel) 55%,transparent)}.manifest-row.active{color:var(--text);background:var(--panel)}.manifest-row.active::before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--signal)}.manifest-index{font-family:"IBM Plex Mono",monospace;font-size:8px}.row-vehicle strong,.row-vehicle small{display:block}.row-vehicle strong{font-family:"Barlow Condensed",sans-serif;font-size:18px;letter-spacing:.02em;text-transform:uppercase}.row-vehicle small{margin-top:4px;color:var(--muted);font-size:8px}.row-soc small,.row-soc strong{display:block;font-family:"IBM Plex Mono",monospace}.row-soc small{color:var(--muted);font-size:6px;text-transform:uppercase}.row-soc strong{margin-top:3px;font-size:10px}.row-soc>i{height:3px;display:block;margin-top:6px;background:var(--line)}.row-soc>i b{display:block;height:100%;background:var(--petrol)}.row-state{width:6px;height:6px;background:var(--muted-2)}.row-state.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}.catalog-empty{background:var(--panel)}
.vehicle-dossier{min-width:0;display:flex;flex-direction:column;padding:23px 27px;background:var(--panel)}.vehicle-dossier>header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px}.vehicle-dossier h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:44px;font-weight:600;line-height:.82;text-transform:uppercase}.vehicle-dossier header p{margin:11px 0 0;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:8px;text-transform:uppercase}.dossier-visual{position:relative;min-height:235px;display:grid;place-items:center;border-bottom:1px solid var(--line)}.dossier-visual .vehicle-silhouette{width:min(100%,390px)}.profile-stamp{position:absolute;right:0;bottom:14px;padding:5px 7px;color:var(--petrol);border:1px solid var(--petrol);font-family:"IBM Plex Mono",monospace;font-size:6px;text-transform:uppercase}.dossier-snapshot{display:grid;grid-template-columns:180px 1fr;margin-top:19px;border-block:1px solid var(--line)}.dossier-battery{padding:18px 22px 18px 0;border-right:1px solid var(--line)}.dossier-battery span,.dossier-battery strong{display:block}.dossier-battery span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.dossier-battery strong{margin-top:5px;font-family:"Barlow Condensed",sans-serif;font-size:58px;font-weight:500;line-height:.9}.dossier-battery strong em{margin-left:3px;color:var(--petrol);font-size:16px;font-style:normal}.dossier-battery>i{height:7px;display:block;margin-top:13px;background:var(--line)}.dossier-battery>i b{display:block;height:100%;background:var(--signal)}.dossier-snapshot dl{margin:0;padding-left:19px}.dossier-snapshot dl>div{min-height:46px;display:flex;align-items:center;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line)}.dossier-snapshot dl>div:last-child{border-bottom:0}.dossier-snapshot dt{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.dossier-snapshot dd{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:19px}.dossier-snapshot dd em{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;font-style:normal}.dossier-snapshot .contact-value{font-family:"IBM Plex Mono",monospace;font-size:8px}.vehicle-dossier footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding-top:20px}
@media(max-width:1080px){.garage-register{grid-template-columns:repeat(3,1fr)}.garage-register p{display:none}.manifest-layout{grid-template-columns:360px 1fr}.dossier-snapshot{grid-template-columns:150px 1fr}}
@media(max-width:850px){.manifest-toolbar{align-items:flex-start;flex-direction:column}.catalog-controls{width:100%}.search-field{width:100%}.manifest-layout{grid-template-columns:1fr}.vehicle-manifest{max-height:310px;overflow:auto;border-right:0;border-bottom:1px solid var(--line)}.vehicle-dossier{min-height:540px}.dossier-visual{min-height:200px}}
@media(max-width:560px){.garage-register{grid-template-columns:repeat(3,1fr)}.garage-register>div{padding-inline:10px}.catalog-controls{align-items:stretch;flex-direction:column}.filter-tabs{display:grid;grid-template-columns:repeat(3,1fr)}.manifest-row{grid-template-columns:24px 1fr 72px 6px;padding-inline:11px}.row-vehicle small{max-width:130px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vehicle-dossier{min-height:510px;padding:19px 16px}.dossier-visual{min-height:170px}.dossier-snapshot{grid-template-columns:1fr}.dossier-battery{border-right:0;border-bottom:1px solid var(--line);padding-right:0}.dossier-snapshot dl{padding-left:0}.vehicle-dossier footer{display:grid;grid-template-columns:1fr 1fr}}
</style>
