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
const showForm = ref(false)
const error = ref('')
const search = ref('')
const filter = ref<VehicleFilter>('all')
const form = ref({ name: '', manufacturer: 'Citroën', model: 'C-Zero', year: new Date().getFullYear(), propulsion_type: 'electric', battery_nominal_capacity_kwh: 16, vehicle_profile: 'citroen-c-zero-v1', color: '#ff6428' })

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
onMounted(load)
</script>

<template>
  <div class="page vehicles-page">
    <header class="page-header"><div><span class="eyebrow">{{ t('vehicles.garage') }}</span><h1>{{ t('vehicles.title') }}</h1></div><button class="button" @click="showForm = !showForm">{{ showForm ? t('common.close') : t('vehicles.add') }}</button></header>

    <form v-if="showForm" class="panel panel-pad vehicle-form" @submit.prevent="create">
      <div class="form-heading"><div><span class="eyebrow">{{ t('vehicles.add') }}</span><h2>{{ t('vehicles.create') }}</h2></div><button class="icon-button" type="button" :aria-label="t('common.close')" @click="showForm=false">×</button></div>
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

    <section class="vehicles-overview">
      <div class="section-heading"><h2>{{ t('vehicles.overview') }}</h2><span>{{ vehicles.length }}</span></div>
      <div class="vehicles-overview-grid">
        <article class="panel overview-stat"><span class="overview-stat-icon"><AppIcon name="vehicle" /></span><div><small>{{ t('vehicles.totalVehicles') }}</small><strong>{{ vehicles.length }}</strong><span>{{ t('dashboard.vehiclesCount', { count: vehicles.length }) }}</span></div><i><b style="width:100%" /></i></article>
        <article class="panel overview-stat"><span class="overview-stat-icon green"><AppIcon name="signal" /></span><div><small>{{ t('vehicles.onlineVehicles') }}</small><strong>{{ onlineCount }}</strong><span>{{ t('dashboard.onlineCount', { count: onlineCount }) }}</span></div><i class="green"><b :style="{ width: `${vehicles.length ? onlineCount / vehicles.length * 100 : 0}%` }" /></i></article>
        <article class="panel overview-stat"><span class="overview-stat-icon blue"><AppIcon name="battery" /></span><div><small>{{ t('vehicles.averageBattery') }}</small><strong>{{ averageSoc ?? '—' }}<em>%</em></strong><span>{{ t('vehicles.batteryLevel') }}</span></div><i class="blue"><b :style="{ width: `${averageSoc ?? 0}%` }" /></i></article>
      </div>
    </section>

    <section class="vehicle-catalog panel">
      <header class="catalog-heading"><div><h2>{{ t('vehicles.listTitle') }}</h2><span>{{ filteredVehicles.length }} / {{ vehicles.length }}</span></div><div class="catalog-controls"><label class="search-field"><AppIcon name="search" :size="17" /><input v-model="search" :placeholder="t('vehicles.search')" /></label><div class="filter-tabs"><button :class="{ active: filter === 'all' }" @click="filter='all'">{{ t('vehicles.all') }}</button><button :class="{ active: filter === 'online' }" @click="filter='online'">{{ t('vehicles.onlineOnly') }}</button><button :class="{ active: filter === 'parked' }" @click="filter='parked'">{{ t('vehicles.parkedOnly') }}</button></div></div></header>
      <div class="vehicle-grid">
        <article v-for="vehicle in filteredVehicles" :key="vehicle.id" class="vehicle-card">
          <header><div><h3>{{ vehicle.name }}</h3><p>{{ vehicle.manufacturer }} {{ vehicle.model }} · {{ vehicle.year ?? t('vehicles.yearUnknown') }}</p></div><span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t('common.online') : t('common.parked') }}</span></header>
          <div class="vehicle-visual"><VehicleSilhouette :color="vehicle.color || '#ff6428'" /><span class="propulsion-tag"><AppIcon :name="vehicle.propulsion_type === 'electric' ? 'charging' : 'vehicle'" :size="13" />{{ vehicle.propulsion_type }}</span></div>
          <div class="vehicle-facts">
            <div><span>{{ t('vehicles.currentSpeed') }}</span><strong>{{ speed(vehicle) === null ? '—' : Math.round(speed(vehicle)!) }} <em>km/h</em></strong></div>
            <div><span>{{ t('vehicles.lastContact') }}</span><strong class="contact-value">{{ lastContact(vehicle) }}</strong></div>
          </div>
          <div class="battery-strip"><div><span><AppIcon name="battery" :size="14" />{{ t('vehicles.batteryLevel') }}</span><strong>{{ soc(vehicle) === null ? '—' : Math.round(soc(vehicle)!) }}%</strong></div><i><b :style="{ width: `${soc(vehicle) ?? 0}%` }" /></i></div>
          <footer><RouterLink class="button secondary" :to="`/vehicles/${vehicle.id}/history`"><AppIcon name="history" :size="14" />{{ t('vehicles.history') }}</RouterLink><RouterLink class="button" to="/devices"><AppIcon name="devices" :size="14" />{{ t('vehicles.tracker') }}</RouterLink></footer>
        </article>
        <div v-if="!filteredVehicles.length" class="empty catalog-empty"><h2>{{ vehicles.length ? t('vehicles.noMatch') : t('vehicles.noVehicles') }}</h2><p v-if="!vehicles.length">{{ t('vehicles.noVehiclesHint') }}</p></div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.vehicle-form{margin-bottom:18px}.form-heading,.section-heading,.catalog-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.form-heading{margin-bottom:18px}.form-heading h2,.section-heading h2,.catalog-heading h2{margin:0;font-size:16px}.color-input{padding:5px}.vehicles-overview{margin-bottom:17px}.section-heading{margin-bottom:12px}.section-heading>span,.catalog-heading>div>span{color:var(--muted);font-size:10px}.vehicles-overview-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.overview-stat{position:relative;min-height:128px;padding:16px;display:grid;grid-template-columns:36px 1fr;gap:12px;overflow:hidden}.overview-stat-icon{width:35px;height:35px;display:grid;place-items:center;border-radius:10px;color:var(--accent);background:var(--accent-soft)}.overview-stat-icon.green{color:var(--success);background:var(--success-soft)}.overview-stat-icon.blue{color:#5677e8;background:rgba(86,119,232,.1)}.overview-stat small,.overview-stat strong,.overview-stat div>span{display:block}.overview-stat small{font-size:9px;font-weight:700}.overview-stat strong{margin:8px 0 2px;font-size:29px;font-weight:520;letter-spacing:-.06em}.overview-stat em{margin-left:3px;color:var(--muted);font-size:11px;font-style:normal}.overview-stat div>span{color:var(--muted);font-size:9px}.overview-stat>i{position:absolute;left:16px;right:16px;bottom:14px;height:5px;border-radius:5px;background:var(--panel-2);overflow:hidden}.overview-stat>i b{display:block;height:100%;background:var(--accent)}.overview-stat>i.green b{background:var(--success)}.overview-stat>i.blue b{background:#5677e8}.vehicle-catalog{overflow:hidden}.catalog-heading{min-height:72px;padding:14px 16px;border-bottom:1px solid var(--line)}.catalog-heading>div:first-child{display:flex;align-items:center;gap:8px}.catalog-controls{display:flex;align-items:center;gap:10px}.search-field{width:min(290px,30vw);height:39px;display:flex;align-items:center;gap:8px;padding:0 11px;color:var(--muted);border:1px solid var(--line);border-radius:10px;background:var(--input)}.search-field:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft)}.search-field input{min-width:0;width:100%;border:0;outline:0;color:var(--text);background:transparent;font-size:11px}.filter-tabs{display:flex;padding:3px;border:1px solid var(--line);border-radius:10px;background:var(--panel-2)}.filter-tabs button{border:0;border-radius:7px;padding:7px 10px;color:var(--muted);background:transparent;font-size:9px;font-weight:700;cursor:pointer}.filter-tabs button.active{color:var(--accent);background:var(--panel);box-shadow:var(--shadow-soft)}.vehicle-grid{display:grid;grid-template-columns:repeat(3,minmax(260px,1fr));gap:12px;padding:12px;background:color-mix(in srgb,var(--panel-2) 44%,var(--panel))}.vehicle-card{min-width:0;padding:14px;display:flex;flex-direction:column;border:1px solid var(--line);border-radius:14px;background:var(--panel);transition:transform .16s,border-color .16s,box-shadow .16s}.vehicle-card:hover{transform:translateY(-2px);border-color:var(--line-strong);box-shadow:var(--shadow)}.vehicle-card header{display:flex;justify-content:space-between;align-items:flex-start;gap:10px}.vehicle-card h3{margin:0;font-size:12px}.vehicle-card header p{margin:4px 0 0;color:var(--muted);font-size:9px}.vehicle-visual{position:relative;height:160px;display:grid;place-items:center;overflow:hidden}.vehicle-visual .vehicle-silhouette{width:min(100%,260px)}.propulsion-tag{position:absolute;left:0;bottom:6px;display:flex;align-items:center;gap:5px;padding:5px 7px;color:var(--accent);background:var(--accent-soft);border-radius:7px;font-size:8px;font-weight:700;text-transform:capitalize}.vehicle-facts{display:grid;grid-template-columns:1fr 1.4fr;margin-bottom:10px;border:1px solid var(--line);border-radius:10px;background:var(--panel-2)}.vehicle-facts>div{min-width:0;padding:9px}.vehicle-facts>div+div{border-left:1px solid var(--line)}.vehicle-facts span,.vehicle-facts strong{display:block}.vehicle-facts span{color:var(--muted);font-size:8px}.vehicle-facts strong{margin-top:4px;font-size:11px}.vehicle-facts em{color:var(--muted);font-size:7px;font-style:normal}.vehicle-facts .contact-value{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9px;font-weight:600}.battery-strip{padding:10px;border:1px solid var(--line);border-radius:10px}.battery-strip>div{display:flex;align-items:center;justify-content:space-between;font-size:9px}.battery-strip span{display:flex;align-items:center;gap:5px;color:var(--muted)}.battery-strip>i{display:block;height:5px;margin-top:8px;border-radius:5px;background:var(--panel-2);overflow:hidden}.battery-strip>i b{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#ff9e5f)}.vehicle-card footer{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:12px}.vehicle-card footer .button{min-height:35px;padding:8px 10px;font-size:9px}.catalog-empty{grid-column:1/-1}.catalog-empty h2{font-size:15px}
@media(max-width:1300px){.vehicle-grid{grid-template-columns:repeat(2,minmax(270px,1fr))}}
@media(max-width:840px){.vehicles-overview-grid{grid-template-columns:1fr}.catalog-heading{align-items:flex-start;flex-direction:column}.catalog-controls{width:100%}.search-field{width:100%}.vehicle-grid{grid-template-columns:1fr}}
@media(max-width:520px){.catalog-controls{align-items:stretch;flex-direction:column}.filter-tabs{display:grid;grid-template-columns:repeat(3,1fr)}.vehicle-visual{height:145px}}
</style>
