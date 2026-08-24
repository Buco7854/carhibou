<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { openLiveEventStream, type LiveConnectionStatus } from '../api/events'
import type { History, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMedia from '../components/VehicleMedia.vue'
import VehicleMap from '../components/VehicleMap.vue'
import {
  energySummary,
  formatMetricNumber,
  metricDefinition,
  metricLabel,
  metricNumber,
  preferredHistoryMetric,
  secondaryReadings,
  type MetricReading,
} from '../vehicleDisplay'

const vehicles = ref<Vehicle[]>([])
const { t } = useI18n()
const selectedId = ref('')
const history = ref<History | null>(null)
const error = ref('')
const liveStatus = ref<LiveConnectionStatus>('connecting')
let eventSource: EventSource | undefined
let historyRequest = 0

const selected = computed(() => vehicles.value.find((vehicle) => vehicle.id === selectedId.value))
const onlineCount = computed(() => vehicles.value.filter((vehicle) => vehicle.state?.online).length)
const selectedEnergy = computed(() => energySummary(selected.value))
const speed = computed(() => metricNumber(selected.value, 'vehicle.speed'))
const drivetrainReadings = computed(() => secondaryReadings(selected.value))
const signal = computed(() => selected.value?.state?.device.mobile_signal)
const energyDetail = computed(() => {
  if (selectedEnergy.value.key !== 'battery.soc') return ''
  const value = selected.value?.state?.metrics['charging.active']
  return typeof value === 'boolean' ? `${t('metrics.charging')} · ${t(value ? 'metrics.active' : 'metrics.inactive')}` : ''
})
const positionLabel = computed(() => selected.value?.state?.position
  ? `${selected.value.state.position.latitude.toFixed(5)}, ${selected.value.state.position.longitude.toFixed(5)}`
  : t('dashboard.noPosition'))
const routePoints = computed<Array<[number, number]>>(() => (history.value?.points ?? []).flatMap((point) =>
  point.latitude !== null && point.longitude !== null ? [[point.latitude, point.longitude] as [number, number]] : []))
const historyMetric = computed(() => preferredHistoryMetric(
  selected.value,
  history.value?.available_metrics ?? [],
  (history.value?.points ?? []).some((point) => typeof point.speed === 'number'),
))
const historyDefinition = computed(() => metricDefinition(historyMetric.value))
const chartSeries = computed(() => [{
  name: metricLabel(historyDefinition.value, t),
  unit: historyDefinition.value.unit,
  data: (history.value?.points ?? []).flatMap((point) => {
    const value = historyMetric.value === 'vehicle.speed' ? point.speed : point.metrics[historyMetric.value]
    return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])

function vehicleEnergy(vehicle: Vehicle) { return energySummary(vehicle) }

function formatReading(reading: MetricReading): string {
  if (reading.value === null) return '—'
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  return formatMetricNumber(reading.value, reading)
}

function lastContact(vehicle: Vehicle): string {
  return vehicle.state ? new Date(vehicle.state.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : t('common.never')
}

async function loadHistory(): Promise<void> {
  const vehicleId = selectedId.value
  const request = ++historyRequest
  if (!vehicleId) { history.value = null; return }
  const nextHistory = await api<History>(`/vehicles/${vehicleId}/history?max_points=150`)
  if (request === historyRequest && selectedId.value === vehicleId) history.value = nextHistory
}

async function load(): Promise<void> {
  try {
    vehicles.value = await api<Vehicle[]>('/vehicles')
    if (!selectedId.value && vehicles.value[0]) selectedId.value = vehicles.value[0].id
    await loadHistory()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('dashboard.loadError') }
}

async function selectVehicle(id: string): Promise<void> { selectedId.value = id; await loadHistory() }

async function applyVehicleStates(nextVehicles: Vehicle[]): Promise<void> {
  const previousStateUpdate = selected.value?.state?.updated_at
  vehicles.value = nextVehicles
  if (!vehicles.value.some((vehicle) => vehicle.id === selectedId.value)) {
    selectedId.value = vehicles.value[0]?.id ?? ''
  }
  error.value = ''
  if (selected.value?.state?.updated_at !== previousStateUpdate) await loadHistory()
}

function connectLiveEvents(): void {
  eventSource = openLiveEventStream({
    onStatus: (status) => { liveStatus.value = status },
    onVehicleStates: (nextVehicles) => { void applyVehicleStates(nextVehicles) },
    onSessionExpired: () => {
      window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`)
    },
  })
}

onMounted(async () => { await load(); connectLiveEvents() })
onUnmounted(() => eventSource?.close())
</script>

<template>
  <div class="page dashboard-page">
    <header class="page-header dashboard-header">
      <div v-if="selected"><span class="eyebrow">{{ t('dashboard.live') }}</span><h1>{{ selected.name }}</h1><p>{{ [selected.manufacturer, selected.model, selected.year].filter(Boolean).join(' · ') }}</p></div>
      <div v-else><span class="eyebrow">{{ t('dashboard.live') }}</span><h1>{{ t('nav.dashboard') }}</h1></div>
      <div v-if="selected" class="header-actions"><span :class="['status', { online: selected.state?.online }]">{{ selected.state?.online ? t('common.online') : t('common.stale') }}</span><RouterLink class="button secondary" :to="`/vehicles/${selected.id}/history`"><AppIcon name="history" :size="16" />{{ t('vehicles.history') }}</RouterLink></div>
    </header>

    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="!vehicles.length" class="panel empty"><h2>{{ t('dashboard.quiet') }}</h2><p>{{ t('dashboard.quietHint') }}</p><RouterLink class="button" to="/vehicles">{{ t('dashboard.addFirst') }}</RouterLink></section>

    <template v-else-if="selected">
      <div class="garage-summary">
        <p>{{ t('dashboard.garageSummary', { count: vehicles.length, online: onlineCount }) }}</p>
        <span :class="['status', { online: liveStatus === 'open' }]" role="status" aria-live="polite">{{ t(`dashboard.liveStream.${liveStatus}`) }}</span>
      </div>

      <nav class="vehicle-switcher" :aria-label="t('dashboard.chooseVehicle')">
        <button v-for="vehicle in vehicles" :key="vehicle.id" type="button" :class="{ active: vehicle.id === selectedId }" @click="selectVehicle(vehicle.id)">
          <span class="switch-color" :style="{ background: vehicle.color || '#315fcf' }" />
          <span class="switch-copy"><strong>{{ vehicle.name }}</strong><small>{{ vehicle.manufacturer }} {{ vehicle.model }}</small></span>
          <span class="switch-soc" :title="metricLabel(vehicleEnergy(vehicle), t)"><b>{{ vehicleEnergy(vehicle).value === null ? '—' : Math.round(vehicleEnergy(vehicle).value!) }}<small v-if="vehicleEnergy(vehicle).value !== null">{{ vehicleEnergy(vehicle).unit }}</small></b><i :class="{ online: vehicle.state?.online }" /></span>
        </button>
      </nav>

      <section class="drive-layout">
        <article class="map-panel panel">
          <header class="map-heading">
            <div><span>{{ t('dashboard.mapAndRoute') }}</span><strong>{{ positionLabel }}</strong></div>
            <small>{{ t('dashboard.sampleCount', { count: history?.original_count ?? 0 }) }}</small>
          </header>
          <div class="map-stage">
            <VehicleMap :position="selected.state?.position" :route="routePoints" />
            <div class="map-caption"><span :style="{ background: selected.color || '#315fcf' }" /><strong>{{ selected.name }}</strong><small>{{ t('dashboard.latestPosition') }}</small></div>
          </div>
        </article>

        <aside class="state-ledger panel">
          <div class="vehicle-portrait"><VehicleMedia :vehicle="selected" /></div>
          <div class="energy-state">
            <span>{{ metricLabel(selectedEnergy, t) }}</span>
            <div><strong>{{ selectedEnergy.value === null ? '—' : Math.round(selectedEnergy.value) }}</strong><em v-if="selectedEnergy.value !== null">{{ selectedEnergy.unit }}</em><small v-if="energyDetail">{{ energyDetail }}</small></div>
            <i><b :style="{ width: `${selectedEnergy.progress}%` }" /></i>
          </div>
          <dl class="telemetry-ledger">
            <div><dt><AppIcon name="speed" :size="16" />{{ t('metrics.vehicleSpeed') }}</dt><dd>{{ speed === null ? '—' : Math.round(speed) }}<small v-if="speed !== null">km/h</small></dd></div>
            <div v-for="reading in drivetrainReadings" :key="reading.key"><dt><AppIcon :name="reading.icon" :size="16" />{{ metricLabel(reading, t) }}</dt><dd :class="{ 'word-value': reading.kind === 'boolean' }">{{ formatReading(reading) }}<small v-if="reading.value !== null && reading.kind === 'number' && reading.unit">{{ reading.unit }}</small></dd></div>
            <div><dt><AppIcon name="signal" :size="16" />{{ t('dashboard.signal') }}</dt><dd>{{ typeof signal === 'number' ? signal : '—' }}<small v-if="typeof signal === 'number'">dBm</small></dd></div>
          </dl>
          <div class="contact-line"><span>{{ t('dashboard.lastContact') }}</span><strong>{{ lastContact(selected) }}</strong></div>
        </aside>
      </section>

      <section class="history-strip panel">
        <header><div><span class="eyebrow">{{ t('dashboard.pastDay') }}</span><h2>{{ metricLabel(historyDefinition, t) }}</h2></div><RouterLink :to="`/vehicles/${selected.id}/history`">{{ t('dashboard.explore') }}</RouterLink></header>
        <TimeSeriesChart :series="chartSeries" :height="235" />
      </section>
    </template>
  </div>
</template>

<style scoped>
.dashboard-header{align-items:center}.dashboard-header p{margin:7px 0 0}.header-actions{display:flex;align-items:center;gap:10px}.garage-summary{display:flex;align-items:center;justify-content:space-between;gap:15px;padding:0 2px 10px;color:var(--muted);font-size:11px}.garage-summary p{margin:0}.garage-summary span{font-family:"IBM Plex Mono",monospace;font-size:9px}.vehicle-switcher{display:flex;overflow:auto;margin-bottom:14px;background:var(--panel);border-block:1px solid var(--line)}.vehicle-switcher button{position:relative;min-width:215px;flex:1;display:grid;grid-template-columns:8px 1fr auto;align-items:center;gap:10px;padding:14px 16px;color:var(--muted);background:transparent;border:0;border-right:1px solid var(--line);text-align:left;cursor:pointer}.vehicle-switcher button:last-child{border-right:0}.vehicle-switcher button::after{content:"";position:absolute;left:0;right:0;bottom:-1px;height:3px;background:transparent}.vehicle-switcher button:hover{color:var(--text);background:var(--panel-2)}.vehicle-switcher button.active{color:var(--text)}.vehicle-switcher button.active::after{background:var(--accent)}.switch-color{width:8px;height:8px;border-radius:50%}.switch-copy strong,.switch-copy small{display:block}.switch-copy strong{font-size:12px}.switch-copy small{margin-top:3px;color:var(--muted);font-size:9px}.switch-soc{display:flex;align-items:center;gap:8px;font-size:11px}.switch-soc b small{margin-left:2px;color:var(--muted);font-size:8px;font-weight:400}.switch-soc i{width:6px;height:6px;background:var(--muted-2);border-radius:50%}.switch-soc i.online{background:var(--success);box-shadow:0 0 0 3px var(--success-soft)}
.drive-layout{display:grid;grid-template-columns:minmax(0,1fr) 335px;gap:14px}.map-panel{min-width:0;overflow:hidden}.map-heading{min-height:66px;display:flex;align-items:center;justify-content:space-between;gap:18px;padding:13px 16px;border-bottom:1px solid var(--line)}.map-heading span,.map-heading strong{display:block}.map-heading span{color:var(--muted);font-size:10px}.map-heading strong{max-width:560px;margin-top:5px;overflow:hidden;font-family:"IBM Plex Mono",monospace;font-size:11px;text-overflow:ellipsis;white-space:nowrap}.map-heading small{color:var(--muted);font-size:9px}.map-stage{position:relative;min-height:505px}.map-stage :deep(.vehicle-map){min-height:505px}.map-caption{position:absolute;z-index:500;left:16px;bottom:16px;display:grid;grid-template-columns:8px auto;align-items:center;column-gap:8px;padding:10px 12px;background:color-mix(in srgb,var(--panel) 94%,transparent);border:1px solid var(--line);border-radius:7px;box-shadow:var(--shadow);backdrop-filter:blur(10px)}.map-caption>span{width:8px;height:8px;grid-row:1/3;border-radius:50%}.map-caption strong{font-size:11px}.map-caption small{margin-top:2px;color:var(--muted);font-size:9px}
.state-ledger{overflow:hidden}.vehicle-portrait{height:170px;background:var(--panel-2);border-bottom:1px solid var(--line)}.vehicle-portrait :deep(.vehicle-media){min-height:0;border:0;border-radius:0}.vehicle-portrait :deep(.vehicle-photo-placeholder){align-items:center;padding:22px}.energy-state{padding:22px 20px 20px}.energy-state>span{color:var(--muted);font-size:10px}.energy-state>div{display:flex;align-items:end;margin-top:5px}.energy-state strong{font-size:61px;font-weight:500;letter-spacing:-.075em;line-height:.9}.energy-state em{margin:0 0 5px 5px;color:var(--accent);font-size:17px;font-style:normal}.energy-state small{margin:0 0 6px auto;color:var(--muted);font-size:9px}.energy-state>i{height:6px;display:block;margin-top:14px;overflow:hidden;background:var(--panel-2);border-radius:4px}.energy-state>i b{display:block;height:100%;background:var(--accent)}.telemetry-ledger{margin:0;border-top:1px solid var(--line)}.telemetry-ledger>div{min-height:55px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:9px 19px;border-bottom:1px solid var(--line)}.telemetry-ledger dt{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:10px}.telemetry-ledger dt .app-icon{color:var(--accent)}.telemetry-ledger dd{display:flex;align-items:baseline;gap:5px;margin:0;font-size:20px;font-weight:500}.telemetry-ledger dd small{color:var(--muted);font-size:9px;font-weight:400}.telemetry-ledger .word-value{font-size:12px}.contact-line{display:flex;justify-content:space-between;gap:12px;padding:14px 19px;font-size:9px}.contact-line span{color:var(--muted)}.history-strip{margin-top:14px;padding:17px 18px 5px}.history-strip>header{display:flex;align-items:center;justify-content:space-between;gap:18px}.history-strip h2{margin:0;font-size:17px}.history-strip a{color:var(--accent);font-size:10px;font-weight:600;text-decoration:none}
@media(max-width:1050px){.drive-layout{grid-template-columns:1fr}.state-ledger{display:grid;grid-template-columns:210px 250px 1fr}.vehicle-portrait{height:auto;min-height:150px;border-right:1px solid var(--line);border-bottom:0}.energy-state{border-right:1px solid var(--line)}.contact-line{grid-column:1/-1}.map-stage,.map-stage :deep(.vehicle-map){min-height:430px}}
@media(max-width:720px){.dashboard-header{align-items:flex-start}.header-actions{align-items:flex-end;flex-direction:column}.garage-summary{align-items:flex-start;flex-direction:column;gap:4px}.vehicle-switcher button{min-width:195px}.map-stage,.map-stage :deep(.vehicle-map){min-height:365px}.map-heading{align-items:flex-start;flex-direction:column;gap:4px}.state-ledger{display:block}.vehicle-portrait{height:150px;border-right:0;border-bottom:1px solid var(--line)}.energy-state{border-right:0}.contact-line{grid-column:auto}}
@media(max-width:480px){.dashboard-header{align-items:stretch}.header-actions{align-items:stretch;flex-direction:row;justify-content:space-between}.map-stage,.map-stage :deep(.vehicle-map){min-height:315px}.map-heading strong{max-width:280px}.history-strip{padding-inline:13px}}
</style>
