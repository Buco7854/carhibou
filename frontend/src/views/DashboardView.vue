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
const soc = computed(() => Number(selected.value?.state?.metrics['battery.soc'] ?? 0))
const power = computed(() => selected.value?.state?.metrics['battery.power'])
const speed = computed(() => selected.value?.state?.position?.speed ?? selected.value?.state?.metrics['vehicle.speed'] ?? 0)
const charging = computed(() => Boolean(selected.value?.state?.metrics['charging.active']))
const signal = computed(() => selected.value?.state?.device.mobile_signal)
const signalBarCount = computed(() => typeof signal.value === 'number' ? Math.min(12, Math.max(1, Math.round((signal.value + 110) / 3))) : 0)
const positionLabel = computed(() => selected.value?.state?.position
  ? `${selected.value.state.position.latitude.toFixed(5)} / ${selected.value.state.position.longitude.toFixed(5)}`
  : t('dashboard.noPosition'))
const chartSeries = computed(() => [{
  name: t('dashboard.soc'), unit: '%', data: (history.value?.points ?? []).flatMap((point) => {
    const value = point.metrics['battery.soc']
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])

function vehicleSoc(vehicle: Vehicle): number | null {
  const value = vehicle.state?.metrics['battery.soc']
  return typeof value === 'number' ? Math.round(value) : null
}

function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? new Date(vehicle.state.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : t('common.never')
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
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="!vehicles.length" class="panel empty"><h2>{{ t('dashboard.quiet') }}</h2><p>{{ t('dashboard.quietHint') }}</p><RouterLink class="button" to="/vehicles">{{ t('dashboard.addFirst') }}</RouterLink></section>
    <template v-else-if="selected">
      <section class="console-frame">
        <header class="command-header">
          <div class="command-identity">
            <span class="eyebrow">{{ t('dashboard.live') }} / {{ selected.propulsion_type }}</span>
            <div class="identity-line"><h1>{{ selected.name }}</h1><span :class="['status', { online: selected.state?.online }]">{{ selected.state?.online ? t('common.online') : t('common.stale') }}</span></div>
            <p>{{ [selected.manufacturer, selected.model, selected.year].filter(Boolean).join(' · ') }}</p>
          </div>
          <div class="vehicle-figure"><VehicleSilhouette :color="selected.color || '#137d78'" /></div>
          <div class="command-time"><span>{{ t('dashboard.lastContact') }}</span><strong>{{ lastContact(selected) }}</strong><RouterLink class="button secondary" :to="`/vehicles/${selected.id}/history`"><AppIcon name="history" :size="14" />{{ t('vehicles.history') }}</RouterLink></div>
        </header>

        <nav class="vehicle-strip" :aria-label="t('dashboard.chooseVehicle')">
          <button v-for="(vehicle, index) in vehicles" :key="vehicle.id" :class="{ active: vehicle.id === selectedId }" @click="selectVehicle(vehicle.id)">
            <span class="vehicle-index">{{ String(index + 1).padStart(2, '0') }}</span>
            <span class="vehicle-strip-name"><strong>{{ vehicle.name }}</strong><small>{{ vehicle.manufacturer }} {{ vehicle.model }}</small></span>
            <span class="vehicle-strip-state"><b>{{ vehicleSoc(vehicle) ?? '—' }}%</b><i :class="{ online: vehicle.state?.online }" /></span>
          </button>
        </nav>

        <div class="live-layout">
          <section class="map-bay">
            <div class="bay-label"><span>01 / {{ t('dashboard.position') }}</span><strong>{{ selected.state?.position ? t('dashboard.validFix') : t('dashboard.awaitingFix') }}</strong></div>
            <VehicleMap :position="selected.state?.position" />
            <div class="coordinate-readout"><AppIcon name="location" :size="15" /><div><span>{{ t('dashboard.latestPosition') }}</span><strong>{{ positionLabel }}</strong></div></div>
          </section>

          <aside class="instrument-stack">
            <div class="instrument-heading"><span>02 / {{ t('dashboard.telemetry') }}</span><i :class="{ online: selected.state?.online }" /></div>
            <div class="signal-rail">
              <div><span>{{ t('dashboard.signal') }}</span><strong>{{ signal ?? '—' }} <em>dBm</em></strong></div>
              <div class="signal-bars" aria-hidden="true"><i v-for="index in 12" :key="index" :class="{ active: index <= signalBarCount }" /></div>
            </div>
            <div class="battery-instrument">
              <div class="battery-copy"><span>{{ t('dashboard.battery') }}</span><strong>{{ Math.round(soc) }}<em>%</em></strong><small>{{ charging ? t('dashboard.active') : t('dashboard.notCharging') }}</small></div>
              <div class="battery-cells" aria-hidden="true"><i v-for="index in 20" :key="index" :class="{ active: index <= Math.round(soc / 5) }" /></div>
            </div>
            <dl class="telemetry-list">
              <div><dt><AppIcon name="speed" :size="15" />{{ t('dashboard.speed') }}</dt><dd>{{ Math.round(Number(speed)) }}<em>km/h</em></dd></div>
              <div><dt><AppIcon name="charging" :size="15" />{{ t('dashboard.power') }}</dt><dd>{{ typeof power === 'number' ? power.toFixed(1) : '—' }}<em>kW</em></dd></div>
              <div><dt><AppIcon name="battery" :size="15" />{{ t('dashboard.charging') }}</dt><dd class="word-value">{{ charging ? t('dashboard.active') : t('dashboard.no') }}</dd></div>
            </dl>
            <div class="instrument-foot"><span>{{ t('dashboard.sampleCount', { count: history?.original_count ?? 0 }) }}</span><strong>{{ t('dashboard.refreshCycle') }}</strong></div>
          </aside>
        </div>
      </section>

      <section class="trace-panel panel">
        <header><div><span class="eyebrow">03 / {{ t('dashboard.pastDay') }}</span><h2>{{ t('dashboard.batteryTrace') }}</h2></div><div class="trace-link"><span>{{ t('dashboard.sampleCount', { count: history?.original_count ?? 0 }) }}</span><RouterLink :to="`/vehicles/${selected.id}/history`">{{ t('dashboard.explore') }}</RouterLink></div></header>
        <div class="trace-ruler" aria-hidden="true"><i v-for="index in 24" :key="index" /></div>
        <TimeSeriesChart :series="chartSeries" :height="250" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.console-frame{overflow:hidden;border:1px solid var(--line-strong);border-radius:8px;background:var(--panel);box-shadow:var(--shadow)}
.command-header{min-height:128px;display:grid;grid-template-columns:minmax(260px,1fr) 260px minmax(190px,.7fr);align-items:center;gap:25px;padding:19px 22px;border-bottom:1px solid var(--line)}
.command-identity h1{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:clamp(43px,5vw,62px);font-weight:600;letter-spacing:-.025em;line-height:.78;text-transform:uppercase}.identity-line{display:flex;align-items:center;gap:14px}.command-identity p{margin:11px 0 0;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:8px;text-transform:uppercase}.vehicle-figure{height:90px;display:grid;place-items:center;border-inline:1px solid var(--line)}.vehicle-figure .vehicle-silhouette{width:190px}.command-time{display:grid;justify-items:end;gap:6px}.command-time>span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;letter-spacing:.09em;text-transform:uppercase}.command-time>strong{font-family:"Barlow Condensed",sans-serif;font-size:26px;font-weight:500}.command-time .button{margin-top:4px}
.vehicle-strip{display:flex;min-width:0;overflow:auto;border-bottom:1px solid var(--line);background:var(--panel-2)}.vehicle-strip button{position:relative;min-width:230px;flex:1;display:grid;grid-template-columns:28px 1fr auto;align-items:center;gap:9px;padding:12px 15px;color:var(--muted);background:transparent;border:0;border-right:1px solid var(--line);text-align:left;cursor:pointer}.vehicle-strip button:hover{color:var(--text);background:color-mix(in srgb,var(--panel) 55%,transparent)}.vehicle-strip button.active{color:var(--text);background:var(--panel)}.vehicle-strip button.active::after{content:"";position:absolute;left:0;right:0;bottom:0;height:3px;background:var(--signal)}.vehicle-index{font-family:"IBM Plex Mono",monospace;font-size:8px}.vehicle-strip-name strong,.vehicle-strip-name small{display:block}.vehicle-strip-name strong{font-family:"Barlow Condensed",sans-serif;font-size:15px;letter-spacing:.03em;text-transform:uppercase}.vehicle-strip-name small{margin-top:2px;font-size:8px}.vehicle-strip-state{display:flex;align-items:center;gap:8px;font-family:"IBM Plex Mono",monospace;font-size:8px}.vehicle-strip-state i{width:5px;height:5px;background:var(--muted-2)}.vehicle-strip-state i.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}
.live-layout{display:grid;grid-template-columns:minmax(420px,1.55fr) minmax(290px,.6fr);min-height:520px}.map-bay{position:relative;min-width:0;min-height:520px;overflow:hidden;border-right:1px solid var(--line)}.bay-label{position:absolute;z-index:500;top:16px;left:17px;display:flex;align-items:center;gap:10px;padding:8px 10px;color:var(--text);background:color-mix(in srgb,var(--panel) 92%,transparent);border-left:3px solid var(--signal);box-shadow:var(--shadow-soft);backdrop-filter:blur(9px)}.bay-label span,.bay-label strong{font-family:"IBM Plex Mono",monospace;font-size:7px;letter-spacing:.06em;text-transform:uppercase}.bay-label strong{color:var(--success)}.coordinate-readout{position:absolute;z-index:500;right:16px;bottom:16px;max-width:min(430px,calc(100% - 32px));display:flex;align-items:center;gap:10px;padding:10px 13px;color:var(--ink-inverse);background:color-mix(in srgb,var(--text) 92%,transparent);border-bottom:3px solid var(--signal);box-shadow:var(--shadow)}.coordinate-readout .app-icon{color:var(--signal)}.coordinate-readout span,.coordinate-readout strong{display:block;font-family:"IBM Plex Mono",monospace}.coordinate-readout span{color:color-mix(in srgb,var(--ink-inverse) 62%,transparent);font-size:7px;text-transform:uppercase}.coordinate-readout strong{margin-top:3px;font-size:9px;white-space:nowrap}
.instrument-stack{display:flex;flex-direction:column;background:var(--panel)}.instrument-heading{height:47px;display:flex;align-items:center;justify-content:space-between;padding:0 18px;border-bottom:1px solid var(--line);font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.08em;text-transform:uppercase}.instrument-heading i{width:7px;height:7px;background:var(--muted-2)}.instrument-heading i.online{background:var(--signal);animation:bus-pulse 2.4s ease-in-out infinite}.signal-rail{display:grid;grid-template-columns:auto 1fr;align-items:end;gap:16px;padding:15px 18px;border-bottom:1px solid var(--line);background:var(--panel-2)}.signal-rail span,.signal-rail strong{display:block}.signal-rail span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.signal-rail strong{margin-top:4px;font-family:"Barlow Condensed",sans-serif;font-size:20px;font-weight:500}.signal-rail em{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;font-style:normal}.signal-bars{height:25px;display:flex;align-items:end;gap:3px}.signal-bars i{height:4px;flex:1;background:var(--line-strong)}.signal-bars i:nth-child(3n+2){height:10px}.signal-bars i:nth-child(3n){height:17px}.signal-bars i.active{background:var(--petrol)}.battery-instrument{min-height:200px;display:grid;grid-template-columns:1fr 42px;gap:24px;align-items:center;padding:22px 22px 22px 25px;border-bottom:1px solid var(--line)}.battery-copy span,.battery-copy strong,.battery-copy small{display:block}.battery-copy span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:8px;letter-spacing:.08em;text-transform:uppercase}.battery-copy strong{margin:4px 0;font-family:"Barlow Condensed",sans-serif;font-size:88px;font-weight:500;letter-spacing:-.055em;line-height:.85}.battery-copy strong em{margin-left:4px;color:var(--petrol);font-size:22px;font-style:normal}.battery-copy small{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.battery-cells{height:145px;display:flex;flex-direction:column-reverse;gap:2px;padding:5px;border:1px solid var(--line-strong);background:var(--panel-2)}.battery-cells i{flex:1;background:var(--line)}.battery-cells i.active{background:var(--signal)}
.telemetry-list{margin:0;padding:0 18px}.telemetry-list>div{min-height:60px;display:flex;align-items:center;justify-content:space-between;gap:15px;border-bottom:1px solid var(--line)}.telemetry-list dt{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:9px}.telemetry-list dt .app-icon{color:var(--petrol)}.telemetry-list dd{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:27px;font-weight:500}.telemetry-list dd em{margin-left:5px;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;font-style:normal}.telemetry-list .word-value{font-size:18px;text-transform:uppercase}.instrument-foot{display:flex;justify-content:space-between;gap:10px;margin-top:auto;padding:11px 18px;color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.instrument-foot strong{color:var(--petrol);font-weight:500}
.trace-panel{position:relative;margin-top:14px;padding:19px 21px 10px;overflow:hidden}.trace-panel>header{display:flex;align-items:flex-end;justify-content:space-between;gap:20px}.trace-panel h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:25px;font-weight:600;letter-spacing:.01em;text-transform:uppercase}.trace-link{display:flex;align-items:center;gap:17px;font-family:"IBM Plex Mono",monospace;font-size:7px;text-transform:uppercase}.trace-link span{color:var(--muted)}.trace-link a{color:var(--petrol);font-weight:500;text-decoration:none}.trace-ruler{height:12px;display:grid;grid-template-columns:repeat(24,1fr);align-items:end;margin-top:14px;border-top:1px solid var(--line)}.trace-ruler i{height:4px;border-left:1px solid var(--line-strong)}.trace-ruler i:nth-child(6n+1){height:9px}
@media(max-width:1180px){.command-header{grid-template-columns:1fr 220px}.command-time{grid-column:1/-1;display:flex;justify-content:space-between;align-items:center;border-top:1px solid var(--line);padding-top:12px}.command-time>span{margin-left:auto}.command-time .button{margin:0}.live-layout{grid-template-columns:1fr}.map-bay{min-height:440px;border-right:0;border-bottom:1px solid var(--line)}.instrument-stack{display:grid;grid-template-columns:1fr 1fr}.instrument-heading,.signal-rail,.instrument-foot{grid-column:1/-1}.battery-instrument{border-right:1px solid var(--line);border-bottom:0}.telemetry-list>div:last-child{border-bottom:0}}
@media(max-width:700px){.command-header{grid-template-columns:1fr;padding:17px}.vehicle-figure{display:none}.command-time{justify-content:flex-start;flex-wrap:wrap}.command-time>span{margin-left:0}.command-time>strong{margin-right:auto}.vehicle-strip button{min-width:195px}.live-layout,.map-bay{min-height:360px}.instrument-stack{display:block}.battery-instrument{min-height:170px;border-right:0;border-bottom:1px solid var(--line)}.battery-copy strong{font-size:74px}.trace-panel{padding-inline:14px}.trace-link span{display:none}}
@media(max-width:440px){.command-identity h1{font-size:48px}.identity-line{align-items:flex-start;flex-direction:column}.command-time .button{width:100%;margin-top:4px}.map-bay{min-height:320px}.coordinate-readout{left:12px;right:12px;bottom:12px}.coordinate-readout strong{overflow:hidden;text-overflow:ellipsis}.bay-label{top:12px;left:12px}.trace-panel>header{align-items:flex-start;flex-direction:column}.trace-link{width:100%;justify-content:flex-end}}
</style>
