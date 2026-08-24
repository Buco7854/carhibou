<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { History, Vehicle } from '../api/types'
import TimeSeriesChart from '../components/TimeSeriesChart.vue'
import VehicleMap from '../components/VehicleMap.vue'

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
const chartSeries = computed(() => [{
  name: t('dashboard.soc'), unit: '%', data: (history.value?.points ?? []).flatMap((point) => {
    const value = point.metrics['battery.soc']; return typeof value === 'number' ? [[point.recorded_at, value] as [string, number]] : []
  }),
}])

async function load() {
  try {
    vehicles.value = await api<Vehicle[]>('/vehicles')
    if (!selectedId.value && vehicles.value[0]) selectedId.value = vehicles.value[0].id
    if (selectedId.value) history.value = await api<History>(`/vehicles/${selectedId.value}/history?max_points=150`)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : t('dashboard.loadError') }
}
onMounted(() => { void load(); timer = window.setInterval(load, 15000) })
onUnmounted(() => window.clearInterval(timer))
</script>

<template>
  <div class="page dashboard-page">
    <header class="page-header">
      <div><span class="eyebrow">{{ t('dashboard.live') }}</span><h1>{{ t(new Date().getHours() < 12 ? 'dashboard.morning' : 'dashboard.evening') }}</h1></div>
      <select v-if="vehicles.length" v-model="selectedId" class="select vehicle-select" aria-label="Selected vehicle" @change="load">
        <option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option>
      </select>
    </header>
    <p v-if="error" class="error">{{ error }}</p>
    <section v-if="!vehicles.length" class="panel empty"><h2>{{ t('dashboard.quiet') }}</h2><p>{{ t('dashboard.quietHint') }}</p><RouterLink class="button" to="/vehicles">{{ t('dashboard.addFirst') }}</RouterLink></section>
    <template v-else-if="selected">
      <section class="vehicle-title">
        <div><h2>{{ selected.name }}</h2><p>{{ [selected.manufacturer, selected.model, selected.year].filter(Boolean).join(' · ') }}</p></div>
        <div :class="['status', { online: selected.state?.online }]">{{ selected.state?.online ? t('common.online') : t('common.stale') }}</div>
        <small class="muted">{{ selected.state ? `${t('common.updated')} ${new Date(selected.state.updated_at).toLocaleTimeString()}` : t('dashboard.awaiting') }}</small>
      </section>
      <div class="live-grid">
        <article class="panel map-panel"><VehicleMap :position="selected.state?.position" /></article>
        <article class="panel battery-panel">
          <span class="eyebrow">{{ t('dashboard.battery') }}</span>
          <div class="soc-ring" :style="{ '--soc': `${soc * 3.6}deg` }"><div><span>{{ Math.round(soc) }}</span><small>%</small></div></div>
          <div class="battery-stats"><div><small>{{ t('dashboard.power') }}</small><strong>{{ typeof power === 'number' ? power.toFixed(1) : '—' }} <span>kW</span></strong></div><div><small>{{ t('dashboard.charging') }}</small><strong>{{ charging ? t('dashboard.active') : t('dashboard.no') }}</strong></div></div>
        </article>
        <article class="panel compact-metric"><span class="eyebrow">{{ t('dashboard.speed') }}</span><div class="metric-value">{{ Math.round(Number(speed)) }}<span class="metric-unit">km/h</span></div><div class="speed-track"><i :style="{ width: `${Math.min(Number(speed), 140) / 1.4}%` }" /></div></article>
        <article class="panel compact-metric"><span class="eyebrow">{{ t('dashboard.signal') }}</span><div class="metric-value">{{ selected.state?.device.mobile_signal ?? '—' }}<span class="metric-unit">dBm</span></div><p class="muted">{{ t('dashboard.connection') }}</p></article>
        <article class="panel chart-panel"><div class="panel-heading"><div><span class="eyebrow">{{ t('dashboard.pastDay') }}</span><h3>{{ t('dashboard.batteryState') }}</h3></div><RouterLink :to="`/vehicles/${selected.id}/history`">{{ t('dashboard.explore') }}</RouterLink></div><TimeSeriesChart :series="chartSeries" :height="255" /></article>
      </div>
    </template>
  </div>
</template>

<style scoped>
.vehicle-select{width:auto;min-width:190px}.vehicle-title{display:grid;grid-template-columns:1fr auto;gap:5px 20px;align-items:center;margin-bottom:18px}.vehicle-title h2{margin:0;font-size:20px}.vehicle-title p{margin:3px 0;color:var(--muted);font-size:12px}.vehicle-title small{grid-column:2;text-align:right;font-size:10px}.live-grid{display:grid;grid-template-columns:minmax(0,1.65fr) minmax(290px,.75fr);gap:16px}.map-panel{overflow:hidden;min-height:420px}.battery-panel{padding:22px;display:flex;flex-direction:column;align-items:center}.battery-panel>.eyebrow{align-self:flex-start}.soc-ring{width:190px;height:190px;margin:15px 0;border-radius:50%;display:grid;place-items:center;background:conic-gradient(var(--accent) var(--soc),var(--accent-soft) 0);position:relative}.soc-ring::after{content:'';position:absolute;inset:12px;border-radius:50%;background:var(--panel)}.soc-ring div{z-index:1}.soc-ring span{font:500 54px 'DM Mono',monospace;letter-spacing:-.08em}.soc-ring small{color:var(--muted);margin-left:4px}.battery-stats{width:100%;display:grid;grid-template-columns:1fr 1fr;border-top:1px solid var(--line);padding-top:17px}.battery-stats div+div{border-left:1px solid var(--line);padding-left:20px}.battery-stats small,.battery-stats strong{display:block}.battery-stats small{color:var(--muted);font-size:10px;margin-bottom:5px}.battery-stats strong{font:500 15px 'DM Mono',monospace}.battery-stats strong span{color:var(--muted);font-size:10px}.compact-metric{padding:20px}.speed-track{height:3px;background:var(--accent-soft);margin-top:22px}.speed-track i{display:block;height:100%;background:var(--accent)}.compact-metric p{font-size:11px;margin:10px 0 0}.chart-panel{grid-column:1/-1;padding:20px}.panel-heading{display:flex;justify-content:space-between;align-items:flex-start}.panel-heading h3{margin:0}.panel-heading a{color:var(--accent);font-size:11px;text-decoration:none}
@media(max-width:1000px){.live-grid{grid-template-columns:1fr 1fr}.map-panel,.chart-panel{grid-column:1/-1}.battery-panel{grid-row:2/span 2}}@media(max-width:600px){.live-grid{display:block}.live-grid>*{margin-bottom:14px}.map-panel{min-height:300px}.vehicle-title{grid-template-columns:1fr auto}.vehicle-title small{grid-column:1/-1;text-align:left}}
</style>
