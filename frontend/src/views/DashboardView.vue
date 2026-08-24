<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { History, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMap from '../components/VehicleMap.vue'
import VehicleSilhouette from '../components/VehicleSilhouette.vue'

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const selectedId = ref('')
const history = ref<History | null>(null)
const error = ref('')
let timer: number | undefined

const selected = computed(() => vehicles.value.find((vehicle) => vehicle.id === selectedId.value))
const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const chargingCount = computed(() => vehicles.value.filter((vehicle) => Boolean(vehicle.state?.metrics['charging.active'])).length)
const averageSoc = computed(() => {
  const values = vehicles.value.flatMap((vehicle) => typeof vehicle.state?.metrics['battery.soc'] === 'number' ? [vehicle.state.metrics['battery.soc'] as number] : [])
  return values.length ? Math.round(values.reduce((total, value) => total + value, 0) / values.length) : null
})
const soc = computed(() => Number(selected.value?.state?.metrics['battery.soc'] ?? 0))
const power = computed(() => selected.value?.state?.metrics['battery.power'])
const speed = computed(() => selected.value?.state?.position?.speed ?? selected.value?.state?.metrics['vehicle.speed'] ?? 0)
const charging = computed(() => Boolean(selected.value?.state?.metrics['charging.active']))
const signal = computed(() => selected.value?.state?.device.mobile_signal)
const positionLabel = computed(() => selected.value?.state?.position
  ? `${selected.value.state.position.latitude.toFixed(5)}, ${selected.value.state.position.longitude.toFixed(5)}`
  : t('dashboard.noPosition'))
const chartSeries = computed(() => [{
  name: t('dashboard.soc'), unit: '%', data: (history.value?.points ?? []).flatMap((point) => {
    const value = point.metrics['battery.soc']
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])

function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? new Date(vehicle.state.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : t('common.never')
}

async function loadHistory(): Promise<void> {
  if (selectedId.value) history.value = await api<History>(`/vehicles/${selectedId.value}/history?max_points=150`)
}

async function selectVehicle(id: string): Promise<void> {
  selectedId.value = id
  await loadHistory()
}

async function load(): Promise<void> {
  try {
    vehicles.value = await api<Vehicle[]>('/vehicles')
    if (!selectedId.value && vehicles.value[0]) selectedId.value = vehicles.value[0].id
    await loadHistory()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('dashboard.loadError') }
}

onMounted(() => { void load(); timer = window.setInterval(load, 15000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="page dashboard-page">
    <header class="page-header dashboard-header">
      <div><span class="eyebrow">{{ t('dashboard.live') }}</span><h1>{{ t(new Date().getHours() < 12 ? 'dashboard.morning' : 'dashboard.evening') }}</h1><p>{{ t('dashboard.fleetReady') }}</p></div>
      <RouterLink v-if="selected" class="button secondary" :to="`/vehicles/${selected.id}/history`"><AppIcon name="history" :size="16" />{{ t('vehicles.history') }}</RouterLink>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="!vehicles.length" class="panel empty"><h2>{{ t('dashboard.quiet') }}</h2><p>{{ t('dashboard.quietHint') }}</p><RouterLink class="button" to="/vehicles">{{ t('dashboard.addFirst') }}</RouterLink></section>
    <template v-else-if="selected">
      <section class="overview-section">
        <div class="section-heading"><h2>{{ t('dashboard.overview') }}</h2><span>{{ t('dashboard.vehiclesCount', { count: vehicles.length }) }}</span></div>
        <div class="overview-grid">
          <article class="overview-card panel"><span class="overview-icon"><AppIcon name="vehicle" /></span><div><small>{{ t('dashboard.tracked') }}</small><strong>{{ vehicles.length }}</strong><span>{{ t('dashboard.vehiclesCount', { count: vehicles.length }) }}</span></div><i class="meter"><b style="width:100%" /></i></article>
          <article class="overview-card panel"><span class="overview-icon success"><AppIcon name="signal" /></span><div><small>{{ t('dashboard.connected') }}</small><strong>{{ onlineCount }}</strong><span>{{ t('dashboard.onlineCount', { count: onlineCount }) }}</span></div><i class="meter success"><b :style="{ width: `${vehicles.length ? onlineCount / vehicles.length * 100 : 0}%` }" /></i></article>
          <article class="overview-card panel"><span class="overview-icon blue"><AppIcon name="battery" /></span><div><small>{{ t('dashboard.averageSoc') }}</small><strong>{{ averageSoc ?? '—' }}<em>%</em></strong><span>{{ t('dashboard.batteryLevel') }}</span></div><i class="meter blue"><b :style="{ width: `${averageSoc ?? 0}%` }" /></i></article>
          <article class="overview-card panel"><span class="overview-icon amber"><AppIcon name="charging" /></span><div><small>{{ t('dashboard.chargingNow') }}</small><strong>{{ chargingCount }}</strong><span>{{ t('dashboard.chargingCount', { count: chargingCount }) }}</span></div><i class="meter amber"><b :style="{ width: `${vehicles.length ? chargingCount / vehicles.length * 100 : 0}%` }" /></i></article>
        </div>
      </section>

      <section class="live-console panel">
        <header class="console-heading"><div><h2>{{ t('dashboard.liveWorkspace') }}</h2><p>{{ t('dashboard.chooseVehicle') }}</p></div><span :class="['status', { online: selected.state?.online }]">{{ selected.state?.online ? t('common.online') : t('common.stale') }}</span></header>
        <div class="live-console-body">
          <aside class="vehicle-picker">
            <button v-for="vehicle in vehicles" :key="vehicle.id" :class="['vehicle-picker-card', { active: vehicle.id === selectedId }]" @click="selectVehicle(vehicle.id)">
              <div><strong>{{ vehicle.name }}</strong><small>{{ vehicle.manufacturer }} {{ vehicle.model }}</small></div><span :class="['picker-state', { online: vehicle.state?.online }]" />
              <VehicleSilhouette :color="vehicle.color || '#ff6428'" />
              <div class="picker-footer"><span><b>{{ vehicle.state?.metrics['battery.soc'] ?? '—' }}%</b> SOC</span><span>{{ lastContact(vehicle) }}</span></div>
            </button>
          </aside>
          <div class="map-stage">
            <VehicleMap :position="selected.state?.position" />
            <div class="map-location-card"><span><AppIcon name="location" :size="18" /></span><div><small>{{ t('dashboard.latestPosition') }}</small><strong>{{ positionLabel }}</strong></div></div>
            <div class="map-vehicle-tag"><span :style="{ background: selected.color }" /><strong>{{ selected.name }}</strong></div>
          </div>
          <aside class="telemetry-pane">
            <div class="vehicle-identity"><div><span class="eyebrow">{{ selected.propulsion_type }}</span><h3>{{ selected.name }}</h3><p>{{ [selected.manufacturer, selected.model, selected.year].filter(Boolean).join(' · ') }}</p></div><VehicleSilhouette :color="selected.color || '#ff6428'" /></div>
            <div class="battery-readout"><div><span>{{ t('dashboard.batteryLevel') }}</span><strong>{{ Math.round(soc) }}<em>%</em></strong></div><i><b :style="{ width: `${Math.min(Math.max(soc, 0), 100)}%` }" /></i></div>
            <div class="telemetry-grid">
              <div><span><AppIcon name="speed" :size="16" />{{ t('dashboard.speed') }}</span><strong>{{ Math.round(Number(speed)) }}<em>km/h</em></strong></div>
              <div><span><AppIcon name="charging" :size="16" />{{ t('dashboard.power') }}</span><strong>{{ typeof power === 'number' ? power.toFixed(1) : '—' }}<em>kW</em></strong></div>
              <div><span><AppIcon name="signal" :size="16" />{{ t('dashboard.signal') }}</span><strong>{{ signal ?? '—' }}<em>dBm</em></strong></div>
              <div><span><AppIcon name="battery" :size="16" />{{ t('dashboard.charging') }}</span><strong class="word-value">{{ charging ? t('dashboard.active') : t('dashboard.no') }}</strong></div>
            </div>
            <div class="last-contact"><span>{{ t('dashboard.lastContact') }}</span><strong>{{ lastContact(selected) }}</strong></div>
          </aside>
        </div>
      </section>

      <section class="panel chart-panel"><div class="chart-heading"><div><span class="eyebrow">{{ t('dashboard.pastDay') }}</span><h2>{{ t('dashboard.batteryState') }}</h2></div><RouterLink :to="`/vehicles/${selected.id}/history`">{{ t('dashboard.explore') }}</RouterLink></div><TimeSeriesChart :series="chartSeries" :height="260" /></section>
    </template>
  </div>
</template>

<style scoped>
.dashboard-header p{margin:7px 0 0;color:var(--muted);font-size:12px}.section-heading,.console-heading,.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-heading{margin-bottom:12px}.section-heading h2,.console-heading h2,.chart-heading h2{margin:0;font-size:16px;letter-spacing:-.02em}.section-heading span,.console-heading p{color:var(--muted);font-size:10px}.overview-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:17px}.overview-card{position:relative;min-height:132px;padding:16px;display:grid;grid-template-columns:35px 1fr;gap:12px;overflow:hidden}.overview-icon{width:34px;height:34px;display:grid;place-items:center;border-radius:9px;color:var(--accent);background:var(--accent-soft)}.overview-icon.success{color:var(--success);background:var(--success-soft)}.overview-icon.blue{color:#5677e8;background:rgba(86,119,232,.1)}.overview-icon.amber{color:#d4872e;background:rgba(212,135,46,.11)}.overview-card small,.overview-card strong,.overview-card div>span{display:block}.overview-card small{font-size:9px;font-weight:700}.overview-card strong{margin:9px 0 2px;font-size:28px;font-weight:520;letter-spacing:-.06em}.overview-card strong em{margin-left:3px;color:var(--muted);font-size:11px;font-style:normal}.overview-card div>span{color:var(--muted);font-size:9px}.meter{position:absolute;left:16px;right:16px;bottom:14px;height:4px;border-radius:4px;background:var(--panel-2);overflow:hidden}.meter b{display:block;height:100%;background:var(--accent)}.meter.success b{background:var(--success)}.meter.blue b{background:#5677e8}.meter.amber b{background:#d4872e}.live-console{overflow:hidden;margin-bottom:17px}.console-heading{min-height:66px;padding:14px 17px;border-bottom:1px solid var(--line)}.console-heading p{margin:4px 0 0}.live-console-body{display:grid;grid-template-columns:250px minmax(360px,1fr) 274px;min-height:470px}.vehicle-picker{padding:12px;display:grid;align-content:start;gap:9px;border-right:1px solid var(--line);background:color-mix(in srgb,var(--panel-2) 35%,var(--panel));overflow:auto;max-height:520px}.vehicle-picker-card{position:relative;width:100%;display:grid;grid-template-columns:1fr auto;gap:5px;text-align:left;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:13px;padding:12px;cursor:pointer;transition:.16s}.vehicle-picker-card:hover{border-color:var(--line-strong);transform:translateY(-1px)}.vehicle-picker-card.active{border-color:var(--accent);box-shadow:0 5px 18px rgba(var(--accent-rgb),.12)}.vehicle-picker-card strong,.vehicle-picker-card small{display:block}.vehicle-picker-card strong{font-size:11px}.vehicle-picker-card small{margin-top:3px;color:var(--muted);font-size:9px}.picker-state{width:7px;height:7px;margin:3px;border-radius:50%;background:var(--muted-2)}.picker-state.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}.vehicle-picker-card .vehicle-silhouette{grid-column:1/-1;width:115px;margin:-7px 0 -8px auto}.picker-footer{grid-column:1/-1;display:flex;justify-content:space-between;padding-top:8px;border-top:1px solid var(--line);color:var(--muted);font-size:8px}.picker-footer b{color:var(--text);font-size:10px}.map-stage{position:relative;min-width:0;min-height:470px;overflow:hidden}.map-location-card{position:absolute;z-index:500;top:15px;left:15px;right:15px;max-width:440px;display:flex;align-items:center;gap:10px;padding:10px 12px;color:var(--text);background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:12px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.map-location-card>span{width:31px;height:31px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:9px}.map-location-card small,.map-location-card strong{display:block}.map-location-card small{color:var(--muted);font-size:8px}.map-location-card strong{margin-top:3px;font-size:10px}.map-vehicle-tag{position:absolute;z-index:500;left:15px;bottom:15px;display:flex;align-items:center;gap:7px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow-soft);font-size:9px}.map-vehicle-tag span{width:7px;height:7px;border-radius:50%}.telemetry-pane{padding:16px;border-left:1px solid var(--line);background:var(--panel)}.vehicle-identity{min-height:125px;display:flex;flex-direction:column}.vehicle-identity h3{margin:0;font-size:18px}.vehicle-identity p{margin:4px 0;color:var(--muted);font-size:9px}.vehicle-identity .vehicle-silhouette{width:155px;margin:-13px auto -16px}.battery-readout{padding:13px;border:1px solid var(--line);border-radius:12px;background:var(--panel-2)}.battery-readout>div{display:flex;align-items:end;justify-content:space-between}.battery-readout span{color:var(--muted);font-size:9px}.battery-readout strong{font-size:28px;font-weight:520;line-height:1;letter-spacing:-.06em}.battery-readout em{margin-left:2px;color:var(--muted);font-size:10px;font-style:normal}.battery-readout>i{height:5px;display:block;margin-top:10px;background:var(--line);border-radius:5px;overflow:hidden}.battery-readout>i b{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#ff9c5b)}.telemetry-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:10px}.telemetry-grid>div{min-width:0;padding:10px;border:1px solid var(--line);border-radius:10px}.telemetry-grid span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:8px}.telemetry-grid span .app-icon{color:var(--accent)}.telemetry-grid strong{display:block;margin-top:8px;font-size:17px;font-weight:560;letter-spacing:-.04em}.telemetry-grid strong em{display:block;margin-top:2px;color:var(--muted);font-size:7px;font-style:normal;letter-spacing:0}.telemetry-grid .word-value{font-size:12px}.last-contact{display:flex;justify-content:space-between;margin-top:12px;padding-top:11px;border-top:1px solid var(--line);font-size:8px}.last-contact span{color:var(--muted)}.chart-panel{padding:18px}.chart-heading h2{font-size:16px}.chart-heading a{color:var(--accent);font-size:10px;font-weight:700;text-decoration:none}
@media(max-width:1350px){.overview-grid{grid-template-columns:repeat(2,1fr)}.live-console-body{grid-template-columns:230px minmax(360px,1fr)}.telemetry-pane{grid-column:1/-1;display:grid;grid-template-columns:210px 210px 1fr auto;align-items:center;gap:15px;border-left:0;border-top:1px solid var(--line)}.vehicle-identity{min-height:0}.vehicle-identity .vehicle-silhouette{display:none}.telemetry-grid{margin:0}.last-contact{display:grid;gap:5px;margin:0;padding:0 0 0 12px;border:0;border-left:1px solid var(--line)}}
@media(max-width:760px){.overview-grid{grid-template-columns:1fr 1fr}.overview-card{min-height:120px;grid-template-columns:30px 1fr;padding:13px}.live-console-body{display:block}.vehicle-picker{display:flex;max-height:none;border:0;border-bottom:1px solid var(--line);overflow:auto}.vehicle-picker-card{min-width:190px}.map-stage{min-height:360px}.telemetry-pane{display:block}.vehicle-identity{min-height:120px}.vehicle-identity .vehicle-silhouette{display:block}.battery-readout{margin-top:5px}.telemetry-grid{margin-top:10px}.last-contact{display:flex;margin-top:12px;padding:10px 0 0;border-left:0;border-top:1px solid var(--line)}}
@media(max-width:480px){.overview-grid{grid-template-columns:1fr}.dashboard-header p{display:none}.map-stage{min-height:310px}.map-location-card{right:10px;left:10px}.telemetry-grid{grid-template-columns:1fr 1fr}}
</style>
