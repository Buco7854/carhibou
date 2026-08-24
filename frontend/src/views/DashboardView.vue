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
              <VehicleSilhouette :color="vehicle.color || '#ff682d'" />
              <div class="picker-footer"><span><b>{{ vehicle.state?.metrics['battery.soc'] ?? '—' }}%</b> SOC</span><span>{{ lastContact(vehicle) }}</span></div>
            </button>
          </aside>
          <div class="map-stage">
            <VehicleMap :position="selected.state?.position" />
            <div class="map-location-card"><span><AppIcon name="location" :size="18" /></span><div><small>{{ t('dashboard.latestPosition') }}</small><strong>{{ positionLabel }}</strong></div></div>
            <div class="map-vehicle-tag"><span :style="{ background: selected.color }" /><strong>{{ selected.name }}</strong></div>
          </div>
          <aside class="telemetry-pane">
            <div class="vehicle-identity"><div><span class="eyebrow">{{ selected.propulsion_type }}</span><h3>{{ selected.name }}</h3><p>{{ [selected.manufacturer, selected.model, selected.year].filter(Boolean).join(' · ') }}</p></div><VehicleSilhouette :color="selected.color || '#ff682d'" /></div>
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

      <section class="panel chart-panel"><div class="chart-heading"><div><span class="eyebrow">{{ t('dashboard.pastDay') }}</span><h2>{{ t('dashboard.batteryState') }}</h2></div><RouterLink :to="`/vehicles/${selected.id}/history`">{{ t('dashboard.explore') }}</RouterLink></div><TimeSeriesChart :series="chartSeries" :height="250" /></section>
    </template>
  </div>
</template>

<style scoped>
.dashboard-header p{margin:6px 0 0;color:var(--muted);font-size:11px}.section-heading,.console-heading,.chart-heading{display:flex;align-items:center;justify-content:space-between;gap:16px}.section-heading{margin-bottom:10px}.section-heading h2,.console-heading h2,.chart-heading h2{margin:0;font-size:15px;font-weight:600;letter-spacing:-.02em}.section-heading span,.console-heading p{color:var(--muted);font-size:9px}.overview-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:14px}.overview-card{position:relative;min-height:118px;padding:14px;display:grid;grid-template-columns:33px 1fr;gap:11px;overflow:hidden}.overview-icon{width:33px;height:33px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:9px}.overview-icon.success{color:var(--success);background:var(--success-soft)}.overview-icon.blue{color:var(--blue);background:var(--blue-soft)}.overview-icon.amber{color:var(--amber);background:var(--amber-soft)}.overview-card small,.overview-card strong,.overview-card div>span{display:block}.overview-card small{font-size:8px;font-weight:600}.overview-card strong{margin:8px 0 2px;font-size:26px;font-weight:500;letter-spacing:-.055em}.overview-card strong em{margin-left:3px;color:var(--muted);font-size:10px;font-style:normal}.overview-card div>span{color:var(--muted);font-size:8px}.meter{position:absolute;left:14px;right:14px;bottom:12px;height:5px;display:flex;gap:2px;overflow:hidden;background:repeating-linear-gradient(90deg,var(--line) 0 4px,transparent 4px 7px)}.meter b{display:block;height:100%;background:repeating-linear-gradient(90deg,var(--accent) 0 4px,transparent 4px 7px)}.meter.success b{background:repeating-linear-gradient(90deg,var(--success) 0 4px,transparent 4px 7px)}.meter.blue b{background:repeating-linear-gradient(90deg,var(--blue) 0 4px,transparent 4px 7px)}.meter.amber b{background:repeating-linear-gradient(90deg,var(--amber) 0 4px,transparent 4px 7px)}
.live-console{overflow:hidden;margin-bottom:14px}.console-heading{min-height:61px;padding:12px 15px;border-bottom:1px solid var(--line)}.console-heading p{margin:3px 0 0}.live-console-body{display:grid;grid-template-columns:238px minmax(350px,1fr) 265px;min-height:440px}.vehicle-picker{max-height:490px;padding:11px;display:grid;align-content:start;gap:8px;overflow:auto;background:color-mix(in srgb,var(--panel-2) 42%,var(--panel));border-right:1px solid var(--line)}.vehicle-picker-card{position:relative;width:100%;display:grid;grid-template-columns:1fr auto;gap:4px;padding:11px;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:12px;text-align:left;cursor:pointer;transition:.16s}.vehicle-picker-card:hover{border-color:var(--line-strong);transform:translateY(-1px)}.vehicle-picker-card.active{border-color:var(--accent);box-shadow:0 5px 16px rgba(var(--accent-rgb),.12)}.vehicle-picker-card strong,.vehicle-picker-card small{display:block}.vehicle-picker-card strong{font-size:10px}.vehicle-picker-card small{margin-top:3px;color:var(--muted);font-size:8px}.picker-state{width:7px;height:7px;margin:3px;background:var(--muted-2);border-radius:50%}.picker-state.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}.vehicle-picker-card .vehicle-silhouette{grid-column:1/-1;width:110px;margin:-8px 0 -9px auto}.picker-footer{grid-column:1/-1;display:flex;justify-content:space-between;padding-top:7px;color:var(--muted);border-top:1px solid var(--line);font-size:7px}.picker-footer b{color:var(--text);font-size:9px}.map-stage{position:relative;min-width:0;min-height:440px;overflow:hidden}.map-location-card{position:absolute;z-index:500;top:14px;left:14px;right:14px;max-width:420px;display:flex;align-items:center;gap:9px;padding:10px 12px;color:var(--text);background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:11px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.map-location-card>span{width:30px;height:30px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:8px}.map-location-card small,.map-location-card strong{display:block}.map-location-card small{color:var(--muted);font-size:7px}.map-location-card strong{margin-top:3px;font-size:9px}.map-vehicle-tag{position:absolute;z-index:500;left:14px;bottom:14px;display:flex;align-items:center;gap:7px;padding:8px 10px;background:var(--panel);border:1px solid var(--line);border-radius:9px;box-shadow:var(--shadow-soft);font-size:8px}.map-vehicle-tag span{width:7px;height:7px;border-radius:50%}.telemetry-pane{padding:14px;background:var(--panel);border-left:1px solid var(--line)}.vehicle-identity{min-height:118px;display:flex;flex-direction:column}.vehicle-identity h3{margin:0;font-size:17px}.vehicle-identity p{margin:3px 0;color:var(--muted);font-size:8px}.vehicle-identity .vehicle-silhouette{width:145px;margin:-13px auto -17px}.battery-readout{padding:12px;background:var(--panel-2);border:1px solid var(--line);border-radius:11px}.battery-readout>div{display:flex;align-items:end;justify-content:space-between}.battery-readout span{color:var(--muted);font-size:8px}.battery-readout strong{font-size:27px;font-weight:500;line-height:1;letter-spacing:-.055em}.battery-readout em{margin-left:2px;color:var(--muted);font-size:9px;font-style:normal}.battery-readout>i{height:5px;display:block;margin-top:9px;overflow:hidden;background:var(--line);border-radius:5px}.battery-readout>i b{display:block;height:100%;background:linear-gradient(90deg,var(--accent),#ff9d60)}.telemetry-grid{display:grid;grid-template-columns:1fr 1fr;gap:7px;margin-top:9px}.telemetry-grid>div{min-width:0;padding:9px;border:1px solid var(--line);border-radius:9px}.telemetry-grid span{display:flex;align-items:center;gap:5px;color:var(--muted);font-size:7px}.telemetry-grid span .app-icon{color:var(--accent)}.telemetry-grid strong{display:block;margin-top:7px;font-size:16px;font-weight:500;letter-spacing:-.035em}.telemetry-grid strong em{display:block;margin-top:2px;color:var(--muted);font-size:7px;font-style:normal}.telemetry-grid .word-value{font-size:11px}.last-contact{display:flex;justify-content:space-between;margin-top:10px;padding-top:10px;border-top:1px solid var(--line);font-size:7px}.last-contact span{color:var(--muted)}.chart-panel{padding:16px}.chart-heading h2{font-size:15px}.chart-heading a{color:var(--accent);font-size:9px;font-weight:600;text-decoration:none}
@media(max-width:1370px){.overview-grid{grid-template-columns:repeat(2,1fr)}.live-console-body{grid-template-columns:220px minmax(340px,1fr)}.telemetry-pane{grid-column:1/-1;display:grid;grid-template-columns:190px 200px 1fr auto;align-items:center;gap:14px;border-left:0;border-top:1px solid var(--line)}.vehicle-identity{min-height:0}.vehicle-identity .vehicle-silhouette{display:none}.telemetry-grid{margin:0}.last-contact{display:grid;gap:5px;margin:0;padding:0 0 0 12px;border:0;border-left:1px solid var(--line)}}
@media(max-width:760px){.overview-grid{grid-template-columns:1fr 1fr}.overview-card{min-height:116px;grid-template-columns:30px 1fr;padding:12px}.live-console-body{display:block}.vehicle-picker{display:flex;max-height:none;border:0;border-bottom:1px solid var(--line);overflow:auto}.vehicle-picker-card{min-width:185px}.map-stage{min-height:350px}.telemetry-pane{display:block}.vehicle-identity{min-height:116px}.vehicle-identity .vehicle-silhouette{display:block}.battery-readout{margin-top:5px}.telemetry-grid{margin-top:9px}.last-contact{display:flex;margin-top:11px;padding:10px 0 0;border-left:0;border-top:1px solid var(--line)}}
@media(max-width:480px){.overview-grid{grid-template-columns:1fr}.dashboard-header p{display:none}.map-stage{min-height:310px}.map-location-card{right:10px;left:10px}.telemetry-grid{grid-template-columns:1fr 1fr}}
</style>
