<script setup lang="ts">
import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Position } from '../api/types'

export interface TrailPoint { lat: number; lng: number; speed: number | null }

const props = defineProps<{
  position: Position | null | undefined
  route?: Array<[number, number]> | undefined
  trail?: TrailPoint[] | undefined
  marks?: number[] | undefined
}>()
const emit = defineEmits<{ pick: [index: number] }>()
const element = ref<HTMLDivElement>()
const tilesLoading = ref(true)
const tilesUnavailable = ref(false)
const { t } = useI18n()
let map: L.Map | undefined
let marker: L.Marker | undefined
let startMarker: L.CircleMarker | undefined
let polyline: L.Polyline | undefined
let routeHalo: L.Polyline | undefined
let trailLayers: L.Layer[] = []

const SPEED_STOPS = [0, 30, 60, 90, 120]

function speedColor(speed: number | null): string {
  if (speed === null) return 'var(--muted-2)'
  const slot = SPEED_STOPS.findIndex((stop) => speed < stop)
  return `var(--chart-${slot <= 0 ? 4 : Math.min(slot, 4)})`
}

function drawTrail(target: L.Map, points: TrailPoint[]): void {
  const bounds: Array<[number, number]> = []
  for (let index = 0; index < points.length - 1; index += 1) {
    const from = points[index]!
    const to = points[index + 1]!
    const pair: Array<[number, number]> = [[from.lat, from.lng], [to.lat, to.lng]]
    bounds.push(pair[0]!)
    trailLayers.push(L.polyline(pair, { color: speedColor(from.speed), weight: 4, opacity: 1, lineCap: 'round' }).addTo(target))
  }
  const last = points.at(-1)
  if (last) bounds.push([last.lat, last.lng])
  points.forEach((point, index) => {
    const dot = L.circleMarker([point.lat, point.lng], {
      radius: props.marks?.includes(index) ? 7 : 4,
      color: props.marks?.includes(index) ? 'var(--accent)' : 'transparent',
      weight: 2,
      fillColor: speedColor(point.speed),
      fillOpacity: props.marks?.includes(index) ? 1 : 0,
      bubblingMouseEvents: false,
    }).addTo(target)
    dot.on('click', () => emit('pick', index))
    trailLayers.push(dot)
  })
  if (bounds.length) target.fitBounds(L.latLngBounds(bounds), { padding: [28, 28], maxZoom: 15 })
}

function positionIcon(heading: number | null | undefined): L.DivIcon {
  const direction = Number.isFinite(heading) ? Number(heading) : 0
  return L.divIcon({
    className: 'carhibou-position-marker',
    html: `<span class="position-puck" style="--heading:${direction}deg"><i></i><b></b></span>`,
    iconSize: [34, 34],
    iconAnchor: [17, 17],
  })
}

function update() {
  if (!map) return
  for (const layer of trailLayers) layer.remove()
  trailLayers = []
  polyline?.remove()
  routeHalo?.remove()
  startMarker?.remove()
  polyline = undefined
  routeHalo = undefined
  startMarker = undefined
  if (props.trail?.length) {
    drawTrail(map, props.trail)
  } else if (props.route?.length) {
    routeHalo = L.polyline(props.route, { color: 'var(--map-route-halo)', weight: 10, opacity: 0.82, lineCap: 'round', lineJoin: 'round' }).addTo(map)
    polyline = L.polyline(props.route, { color: 'var(--accent)', weight: 4, opacity: 1, lineCap: 'round', lineJoin: 'round' }).addTo(map)
    const routeStart = props.route[0]
    if (routeStart) {
      startMarker = L.circleMarker(routeStart, { radius: 5, color: 'var(--accent)', weight: 2, fillColor: 'var(--panel)', fillOpacity: 1 }).addTo(map)
      startMarker.bindTooltip(t('history.routeStart'), { direction: 'top', offset: [0, -5] })
    }
    map.fitBounds(polyline.getBounds(), { padding: [28, 28], maxZoom: 15 })
  }
  marker?.remove()
  marker = undefined
  if (props.position) {
    const point = L.latLng(props.position.latitude, props.position.longitude)
    marker = L.marker(point, { icon: positionIcon(props.position.heading), keyboard: false }).addTo(map)
    marker.bindTooltip(t('history.latestPosition'), { direction: 'top', offset: [0, -15] })
    if (!props.route?.length) map.setView(point, 14)
  }
}

onMounted(() => {
  map = L.map(element.value!, { zoomControl: false, attributionControl: true, scrollWheelZoom: false, minZoom: 2 }).setView([20, 0], 2)
  let tileErrors = 0
  const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
    maxZoom: 19,
  })
  tiles.on('loading', () => { tilesLoading.value = true; tileErrors = 0 })
  tiles.on('tileerror', () => { tileErrors += 1; if (tileErrors >= 2) tilesUnavailable.value = true })
  tiles.on('load', () => { tilesLoading.value = false; if (tileErrors === 0) tilesUnavailable.value = false })
  tiles.addTo(map)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 90 }).addTo(map)
  update()
  requestAnimationFrame(() => map?.invalidateSize())
})
watch(() => [props.position, props.route, props.trail, props.marks], update, { deep: true })
onBeforeUnmount(() => map?.remove())
</script>

<template>
  <div class="map-frame" :class="{ unavailable: tilesUnavailable }" :aria-busy="tilesLoading">
    <div ref="element" class="vehicle-map" role="region" :aria-label="t('history.route')" />
    <span v-if="tilesLoading && !tilesUnavailable" class="map-state" aria-live="polite">{{ t('history.mapLoading') }}</span>
    <span v-if="tilesUnavailable" class="map-state unavailable-message" role="status">{{ t('history.mapUnavailable') }}</span>
    <span v-if="!position && !route?.length" class="map-empty">{{ t('dashboard.noPosition') }}</span>
  </div>
</template>

<style scoped>
.map-frame{--map-route-halo:rgba(255,255,255,.9);position:relative;width:100%;height:100%;min-height:300px;overflow:hidden;background:var(--panel-2)}
.vehicle-map{width:100%;height:100%;min-height:300px;background:var(--panel-2)}
:deep(.leaflet-tile-pane){filter:grayscale(.42) saturate(.62) contrast(.9) brightness(1.055)}
:global([data-theme="dark"] .map-frame){--map-route-halo:rgba(13,16,14,.86)}
:global([data-theme="dark"] .map-frame .leaflet-tile-pane){filter:brightness(.5) saturate(.22) contrast(1.16)}
:deep(.leaflet-control-zoom){margin:0 10px 10px 0!important;overflow:hidden;border:1px solid var(--line-strong)!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-soft)!important}
:deep(.leaflet-control-zoom a){width:28px!important;height:26px!important;display:grid!important;place-items:center;color:var(--text)!important;background:color-mix(in srgb,var(--panel) 94%,transparent)!important;border:0!important;border-bottom:1px solid var(--line)!important;font:400 16px/1 "IBM Plex Sans",sans-serif!important}
:deep(.leaflet-control-zoom a:last-child){border-bottom:0!important}
:deep(.leaflet-control-zoom a:hover){background:var(--panel)!important}
:deep(.leaflet-control-scale){margin:0 0 10px 10px!important}
:deep(.leaflet-control-scale-line){padding:1px 6px;color:var(--muted);background:color-mix(in srgb,var(--panel) 82%,transparent);border-color:var(--line-strong);border-top:0;font:400 11px/1.5 var(--mono)}
:deep(.leaflet-control-attribution){padding:2px 5px!important;color:var(--muted);background:color-mix(in srgb,var(--panel) 84%,transparent)!important;font-size:11px}
:deep(.leaflet-control-attribution a){color:var(--accent)}
:deep(.leaflet-tooltip){padding:4px 7px;color:var(--text);background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow-soft);font:400 12px/1.3 "IBM Plex Sans",sans-serif}
:deep(.leaflet-tooltip::before){display:none}
:deep(.carhibou-position-marker){background:transparent;border:0}
:deep(.position-puck){position:relative;width:34px;height:34px;display:grid;place-items:center;filter:drop-shadow(0 3px 6px rgba(16,24,20,.22))}
:deep(.position-puck i){position:absolute;inset:4px;background:var(--panel);border:2px solid var(--accent);border-radius:50%}
:deep(.position-puck b){position:relative;width:10px;height:10px;background:var(--accent);border:2px solid var(--panel);border-radius:50%;box-shadow:0 0 0 2px var(--accent)}
:deep(.position-puck::before){content:"";position:absolute;top:-1px;left:14px;width:6px;height:9px;background:var(--accent);clip-path:polygon(50% 0,100% 100%,0 100%);transform:rotate(var(--heading)) translateY(-1px);transform-origin:3px 18px}
.map-state,.map-empty{position:absolute;z-index:500;top:10px;left:10px;padding:5px 8px;color:var(--muted);background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:var(--radius);font:400 12px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none}
.map-empty{top:50%;left:50%;max-width:220px;transform:translate(-50%,-50%);color:var(--text);text-align:center}
.unavailable-message{color:var(--danger)}
.map-frame.unavailable :deep(.leaflet-tile-pane){opacity:.12}
</style>
