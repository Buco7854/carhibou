<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorMessage } from '../api/client'
import { useLiveVehicles } from '../api/live'
import type { Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import RowMenu from '../components/RowMenu.vue'
import VehicleMedia from '../components/VehicleMedia.vue'
import { canOperate, isAdmin } from '../access'
import { agentStatus, chargingState, energySummary, energyTone, formatAge, formatMetricNumber, headlineReading, isPercentage, isStale, metricLabel, metricNumber, observedAt, vehicleActivity } from '../vehicleDisplay'
import { askConfirm } from '../confirm'
import { formatFixedNumber } from '../numberFormat'

type VehicleFilter = 'all' | 'online' | 'parked'

interface VehicleForm {
  name: string
}

const vehicles = ref<Vehicle[]>([])
const { locale, t } = useI18n()
const showForm = ref(false)
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
  return formatMetricNumber(reading.value, reading, locale.value)
}
function headlineProgress(vehicle: Vehicle): number | null {
  const reading = headlineReading(vehicle)
  if (!reading || !isPercentage(reading)) return null
  return Math.min(100, Math.max(0, Number(reading.value)))
}
/**
 * The fill for the level bar. Charging keeps the bar, as it always has: a pack
 * that is filling is being handled whatever it currently reads. Only an energy
 * headline is toned, so a card led by engine load stays neutral.
 */
function levelFill(vehicle: Vehicle): string {
  if (charging(vehicle).active) return 'is-charging'
  const energy = energySummary(vehicle)
  return energy.value === null ? '' : energyTone(energy.value)
}
function vehicleSpeed(vehicle: Vehicle): number | null { return metricNumber(vehicle, 'vehicle.speed') }
/** Relative time reads faster than a timestamp when the only question is "recently?". */
function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? formatAge(vehicle.state.updated_at, locale.value) : t('common.never')
}

/**
 * The short facts worth reading at a glance, and only the ones this vehicle
 * reports. Units carry the meaning, so the labels that made every card read like
 * a specification table are gone.
 */
function vehicleFacts(vehicle: Vehicle): string[] {
  const facts: string[] = []
  const speed = vehicleSpeed(vehicle)
  if (speed !== null) facts.push(`${formatFixedNumber(speed, locale.value, 0)} km/h`)
  const state = chargingState(vehicle)
  if (state.active) facts.push(state.power === null ? t('vehicles.charging') : `${t('vehicles.charging')} ${formatFixedNumber(state.power, locale.value, 1)} kW`)
  else if (state.active === false) facts.push(t('vehicles.notCharging'))
  return facts
}

async function load(): Promise<void> {
  vehicles.value = await api<Vehicle[]>('/vehicles')
}

// Every card here shows a live reading, so it follows the stream rather than
// staying at whatever was true when the page opened.
const live = useLiveVehicles()
watch(live.vehicles, (next) => { if (next.length) vehicles.value = next })
async function create(): Promise<void> {
  error.value = ''
  const payload = { name: form.value.name.trim() }
  try { await api('/vehicles', { method: 'POST', body: JSON.stringify(payload) }); showForm.value = false; form.value = emptyForm(); await load() }
  catch (reason) { error.value = errorMessage(reason, t('common.error')) }
}

async function clearTelemetry(vehicle: Vehicle): Promise<void> {
  const accepted = await askConfirm({
    title: t('vehicles.clearTitle'),
    question: t('vehicles.clearQuestion', { name: vehicle.name }),
    detail: t('vehicles.clearDetail'),
    confirmLabel: t('vehicles.clearAction'),
    action: async () => { await api(`/vehicles/${vehicle.id}/telemetry`, { method: 'DELETE' }) },
  })
  if (accepted) await load()
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
    photoNotice.value = { kind: 'error', message: errorMessage(reason, t('common.error')) }
  } finally {
    photoBusyId.value = ''
  }
}

async function removePhoto(vehicle: Vehicle): Promise<void> {
  const accepted = await askConfirm({
    title: t('vehicles.photoTitle'),
    question: t('vehicles.photoQuestion', { name: vehicle.name }),
    confirmLabel: t('vehicles.photoAction'),
  })
  if (!accepted) return
  photoNotice.value = null
  photoBusyId.value = vehicle.id
  try {
    await api<void>(`/vehicles/${vehicle.id}/photo`, { method: 'DELETE' })
    await load()
    photoNotice.value = { kind: 'success', message: t('vehicles.photoRemoved', { name: vehicle.name }) }
  } catch (reason) {
    photoNotice.value = { kind: 'error', message: errorMessage(reason, t('common.error')) }
  } finally {
    photoBusyId.value = ''
  }
}


async function deleteVehicle(vehicle: Vehicle): Promise<void> {
  photoNotice.value = null
  const accepted = await askConfirm({
    title: t('vehicles.deleteTitle'),
    question: t('vehicles.deleteQuestion', { name: vehicle.name }),
    detail: t('vehicles.deleteWarning'),
    confirmLabel: t('vehicles.deleteVehicle'),
    busyLabel: t('vehicles.deleting'),
    action: async () => { await api<void>(`/vehicles/${vehicle.id}`, { method: 'DELETE' }) },
  })
  if (!accepted) return
  await load()
  photoNotice.value = { kind: 'success', message: t('vehicles.deleted', { name: vehicle.name }) }
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
        <button v-if="isAdmin" class="button" @click="showForm = true"><AppIcon name="plus" :size="15" />{{ t('vehicles.add') }}</button>
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
        <div class="vehicle-visual"><VehicleMedia :vehicle="vehicle" :editable="canOperate(vehicle)" :busy="photoBusyId === vehicle.id" @select="uploadPhoto(vehicle, $event)" @remove="removePhoto(vehicle)" /></div>

        <div class="vehicle-card-body">
          <header class="vehicle-identity">
            <div>
              <h2>{{ vehicle.name }}</h2>
              <p v-if="[vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).length">{{ [vehicle.manufacturer, vehicle.model, vehicle.year].filter(Boolean).join(' · ') }}</p>
            </div>
            <span :class="['status',{online:vehicle.state?.online}]">{{ vehicle.state?.online ? t(`dashboard.activity.${vehicleActivity(vehicle)}`) : t(`dashboard.agent.${agentStatus(vehicle)}`) }}</span>
          </header>

          <section class="charge-reading">
            <template v-if="headline(vehicle)">
              <div class="reading-row" :class="{ 'is-stale': isStale(headline(vehicle)) }">
                <span>{{ metricLabel(headline(vehicle)!, t) }}</span>
                <strong>{{ headlineValue(vehicle) }}<em v-if="headline(vehicle)!.unit">{{ headline(vehicle)!.unit }}</em></strong>
              </div>
              <i v-if="headlineProgress(vehicle) !== null" class="level-bar" :class="{ 'is-stale': isStale(headline(vehicle)) }"><b :class="levelFill(vehicle)" :style="{ width: `${headlineProgress(vehicle)}%` }" /></i>
              <!-- A sleeping car keeps its last charge level; saying when it was
                   measured is what stops it reading as a live number. -->
              <small v-if="isStale(headline(vehicle))" class="stale-age">{{ formatAge(observedAt(headline(vehicle)), locale) }}</small>
            </template>
            <p v-else class="awaiting">{{ t('vehicles.awaitingTelemetry') }}</p>
          </section>

          <p class="vehicle-facts">
            <span v-for="(fact, index) in vehicleFacts(vehicle)" :key="fact" :class="{ 'is-charging':index === 1 && charging(vehicle).active }">{{ fact }}</span>
            <small>{{ lastContact(vehicle) }}</small>
          </p>
        </div>

        <!-- Two places to go, and the destructive pair behind the same menu the
             data source rows use. Four labels never fitted one line in French,
             so one wrapped and sat a line higher than the rest. -->
        <footer>
          <div class="card-actions">
            <RouterLink class="card-action" :to="`/vehicles/${vehicle.id}/history`"><AppIcon name="history" :size="15" />{{ t('vehicles.history') }}</RouterLink>
            <RouterLink class="card-action" to="/data-sources"><AppIcon name="agent" :size="15" />{{ t('vehicles.agent') }}</RouterLink>
          </div>
          <RowMenu v-if="canOperate(vehicle) || isAdmin" :label="t('dataSources.moreActions', { name: vehicle.name })">
            <button v-if="canOperate(vehicle)" type="button" role="menuitem" @click="clearTelemetry(vehicle)">{{ t('vehicles.clearData') }}</button>
            <button v-if="isAdmin" type="button" role="menuitem" class="danger" @click="deleteVehicle(vehicle)">{{ t('common.delete') }}</button>
          </RowMenu>
        </footer>
      </article>

      <div v-if="!filteredVehicles.length" class="empty panel">
        <h2>{{ vehicles.length ? t('vehicles.noMatch') : t('vehicles.noVehicles') }}</h2>
        <!-- Only an administrator can act on this hint, so only one sees it. -->
        <p v-if="!vehicles.length && isAdmin">{{ t('vehicles.noVehiclesHint') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.stack-form{display:grid;gap:14px}
.stack-form .form-actions{justify-content:flex-end;margin-top:4px}

.catalog-toolbar{display:flex;align-items:center;gap:10px;margin-bottom:14px}
.search-field{width:min(280px,100%);height:32px;display:flex;align-items:center;gap:7px;padding:0 10px;color:var(--muted);background:var(--input);border:1px solid var(--line-strong);border-radius:var(--radius);transition:border-color .12s,box-shadow .12s}
.search-field:focus-within{border-color:var(--accent);box-shadow:var(--focus-ring)}
.search-field input{min-width:0;width:100%;color:var(--text);background:transparent;border:0;outline:0;font-size:var(--font-body)}
.filter-tabs{display:flex;gap:2px;padding:2px;background:var(--panel-2);border-radius:var(--radius)}
.filter-tabs button{height:26px;padding:0 10px;color:var(--muted);background:transparent;border:0;border-radius:var(--radius-sm);font-size:var(--font-caption);cursor:pointer;transition:color .12s,background-color .12s}
.filter-tabs button:hover{color:var(--text)}
.filter-tabs button.active{color:var(--text);background:var(--panel);font-weight:500;box-shadow:var(--shadow-soft)}
.catalog-toolbar .count{margin-left:auto;color:var(--muted);font-size:var(--font-caption);font-variant-numeric:tabular-nums}

.roster-notice{margin:0 0 14px;padding:8px 12px;border-radius:var(--radius);font-size:var(--font-body)}
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

.vehicle-card-body{min-width:0;flex:1;padding:16px}
.vehicle-identity{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:start;gap:10px}
.vehicle-identity h2{margin:0;overflow:hidden;font-size:var(--font-card-title);font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.vehicle-identity p{margin:2px 0 0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}

.charge-reading{min-height:40px;margin-top:16px}
.reading-row{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
.reading-row span{color:var(--muted);font-size:var(--font-caption)}
.reading-row strong{font-size:var(--font-value-sm);font-weight:500;letter-spacing:-.02em;line-height:1.1;font-variant-numeric:tabular-nums}
.reading-row em{margin-left:2px;color:var(--muted);font-size:var(--font-caption);font-style:normal;font-weight:400}
.charge-reading .level-bar{margin-top:8px}
/* Real but old: dimmed and dated, keeping its place rather than being replaced
   by whatever happens to be freshest. */
.reading-row.is-stale strong,.reading-row.is-stale span{color:var(--muted)}
.level-bar.is-stale{opacity:.55}
.stale-age{display:block;margin-top:5px;color:var(--muted-2);font-size:var(--font-micro)}
.charge-reading .level-bar b.is-charging{background:var(--success-fill)}
.awaiting{margin:0;color:var(--muted-2);font-size:var(--font-body)}

.vehicle-facts{display:flex;align-items:baseline;flex-wrap:wrap;gap:2px 8px;margin:12px 0 0;font-size:var(--font-body);font-variant-numeric:tabular-nums}
.vehicle-facts span+span::before{content:"·";margin-right:8px;color:var(--muted-2)}
.vehicle-facts .is-charging{color:var(--success)}
.vehicle-facts small{flex-basis:100%;color:var(--muted);font-size:var(--font-caption)}

/* One row, one height, one treatment. The links used to be .link-button, which
   left the two RouterLinks with the browser's underline and the two buttons
   without it. A fixed height is what keeps the four baselines on one line. */
.vehicle-card>footer{display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 10px 7px 8px;border-top:1px solid var(--line)}
.card-actions{min-width:0;display:flex;align-items:center;gap:2px}
.card-action{height:30px;display:inline-flex;align-items:center;gap:6px;padding:0 9px;color:var(--muted);border-radius:var(--radius);font-size:var(--font-body);text-decoration:none;white-space:nowrap;transition:color .12s,background-color .12s}
.card-action:hover{color:var(--text);background:var(--panel-2)}
/* The menu trigger is one of the row's controls, so it stands the same height. */
.vehicle-card>footer :deep(.row-menu-button){width:30px;height:30px}

.empty{grid-column:1/-1}

@media(max-width:560px){
  .catalog-toolbar{flex-wrap:wrap}
  .search-field{width:100%}
  .filter-tabs{flex:1}
  .filter-tabs button{flex:1}
  .vehicle-list{grid-template-columns:1fr}
  .vehicle-card>footer{padding:7px 8px}
  .card-action{padding:0 7px}
  .vehicle-card-body{padding:14px}
}
</style>
