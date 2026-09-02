<script setup lang="ts">
import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PositionFix } from '../api/types'

export interface TrailPoint { lat: number; lng: number; speed: number | null }

const props = defineProps<{
  position: PositionFix | null | undefined
  route?: Array<[number, number]> | undefined
  trail?: TrailPoint[] | undefined
  marks?: number[] | undefined
  /**
   * What the map is showing. Changing it is what earns a new frame; live updates
   * to the same subject redraw without touching the reader's viewport.
   */
  subject?: string | undefined
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
let directionLayers: L.Layer[] = []
let endMarker: L.CircleMarker | undefined

/*
 * Direction cues.
 *
 * Where a road is driven twice, or two drives share it, the line alone says
 * nothing about which way anything ran. Arrows are spaced in screen pixels
 * rather than along the ground, so the density a reader sees is the same
 * whatever the zoom, and only the arrows inside the current view are built:
 * spacing by distance would crowd a city and vanish on a motorway, and drawing
 * the whole line at close zoom would put thousands of markers on the map.
 */
const ARROW_SPACING_PX = 96
const ARROW_EDGE_PADDING_PX = 40

function arrowIcon(angle: number): L.DivIcon {
  return L.divIcon({
    className: 'carhibou-route-arrow',
    html: `<span style="--angle:${angle}deg"></span>`,
    iconSize: [14, 14],
    iconAnchor: [7, 7],
  })
}

function drawDirection(target: L.Map, path: L.LatLngExpression[]): void {
  if (path.length < 2) return
  const points = path.map((entry) => target.latLngToLayerPoint(L.latLng(entry as L.LatLngTuple)))
  const view = target.getPixelBounds()
  const origin = target.getPixelOrigin()
  const visible = (point: L.Point): boolean => {
    const absolute = point.add(origin)
    return absolute.x >= view.min!.x - ARROW_EDGE_PADDING_PX && absolute.x <= view.max!.x + ARROW_EDGE_PADDING_PX
      && absolute.y >= view.min!.y - ARROW_EDGE_PADDING_PX && absolute.y <= view.max!.y + ARROW_EDGE_PADDING_PX
  }

  // Half a gap in, so a short leg still earns one arrow instead of none.
  let travelled = ARROW_SPACING_PX / 2
  for (let index = 0; index < points.length - 1; index += 1) {
    const from = points[index]!
    const to = points[index + 1]!
    const length = from.distanceTo(to)
    if (length === 0) continue
    const angle = (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI
    while (travelled <= length) {
      const along = travelled / length
      const at = L.point(from.x + (to.x - from.x) * along, from.y + (to.y - from.y) * along)
      if (visible(at)) {
        directionLayers.push(
          L.marker(target.layerPointToLatLng(at), { icon: arrowIcon(angle), interactive: false, keyboard: false })
            .addTo(target),
        )
      }
      travelled += ARROW_SPACING_PX
    }
    travelled -= length
  }
}

function endpoint(target: L.Map, at: L.LatLngExpression, kind: 'start' | 'end'): L.CircleMarker {
  const mark = L.circleMarker(at, {
    radius: kind === 'start' ? 5 : 6,
    color: 'var(--accent)',
    weight: 2,
    // The end is filled and the start is hollow, so which is which survives
    // being read at a glance and in either theme.
    fillColor: kind === 'start' ? 'var(--panel)' : 'var(--accent)',
    fillOpacity: 1,
  }).addTo(target)
  mark.bindTooltip(t(kind === 'start' ? 'history.routeStart' : 'history.routeEnd'), { direction: 'top', offset: [0, -5] })
  return mark
}

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
  if (bounds.length) frame(() => target.fitBounds(L.latLngBounds(bounds), { padding: [28, 28], maxZoom: 15 }))
}

/**
 * Whether the map may still choose its own viewport.
 *
 * Live state arrives every few seconds and each arrival redraws the layers. It
 * must not also re-frame: a reader who panned across town to look at something
 * had the map yanked back under them on the next upload. So the map frames
 * itself once for a subject, and after that the viewport belongs to the reader.
 * A new subject, meaning another vehicle or another range, earns a new frame.
 */
let framed = false

function frame(apply: () => void): void {
  if (framed) return
  framed = true
  apply()
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

/** Rebuilds only the arrows, leaving the lines and markers where they are. */
function redrawDirection(): void {
  if (!map) return
  for (const layer of directionLayers) layer.remove()
  directionLayers = []
  if (props.trail?.length) drawDirection(map, props.trail.map((point) => [point.lat, point.lng] as L.LatLngTuple))
  else if (props.route?.length) drawDirection(map, props.route)
}

function update() {
  if (!map) return
  for (const layer of trailLayers) layer.remove()
  trailLayers = []
  for (const layer of directionLayers) layer.remove()
  directionLayers = []
  polyline?.remove()
  routeHalo?.remove()
  startMarker?.remove()
  endMarker?.remove()
  polyline = undefined
  routeHalo = undefined
  startMarker = undefined
  endMarker = undefined
  if (props.trail?.length) {
    drawTrail(map, props.trail)
    drawDirection(map, props.trail.map((point) => [point.lat, point.lng] as L.LatLngTuple))
    const trailStart = props.trail[0]
    const trailEnd = props.trail.at(-1)
    if (trailStart) startMarker = endpoint(map, [trailStart.lat, trailStart.lng], 'start')
    if (trailEnd && props.trail.length > 1) endMarker = endpoint(map, [trailEnd.lat, trailEnd.lng], 'end')
  } else if (props.route?.length) {
    routeHalo = L.polyline(props.route, { color: 'var(--map-route-halo)', weight: 10, opacity: 0.82, lineCap: 'round', lineJoin: 'round' }).addTo(map)
    polyline = L.polyline(props.route, { color: 'var(--accent)', weight: 4, opacity: 1, lineCap: 'round', lineJoin: 'round' }).addTo(map)
    drawDirection(map, props.route)
    const routeStart = props.route[0]
    const routeEnd = props.route.at(-1)
    if (routeStart) startMarker = endpoint(map, routeStart, 'start')
    if (routeEnd && props.route.length > 1) endMarker = endpoint(map, routeEnd, 'end')
    frame(() => map!.fitBounds(polyline!.getBounds(), { padding: [28, 28], maxZoom: 15 }))
  }
  marker?.remove()
  marker = undefined
  if (props.position) {
    const point = L.latLng(props.position.latitude, props.position.longitude)
    marker = L.marker(point, { icon: positionIcon(props.position.heading), keyboard: false }).addTo(map)
    marker.bindTooltip(t('history.latestPosition'), { direction: 'top', offset: [0, -15] })
    if (!props.route?.length && !props.trail?.length) frame(() => map!.setView(point, 14))
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
  // Arrow spacing is measured on screen and only the visible ones are built, so
  // both moving and zooming invalidate the set that is currently drawn.
  map.on('moveend zoomend', redrawDirection)
  update()
  requestAnimationFrame(() => map?.invalidateSize())
})
watch(() => [props.position, props.route, props.trail, props.marks], update, { deep: true })
// Another vehicle, or another range, is another thing to look at: that earns a
// fresh frame, and nothing else does.
watch(() => props.subject, () => { framed = false; update() })
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
/* Leaflet numbers its own panes from 200 to 700 and its controls at 1000, all
   as plain z-indexes. Without a stacking context of its own the map spends
   those numbers in the page's context, where they outrank the nav rail and
   the mobile nav bar. Isolating the frame confines them, so app chrome wins
   on its own much smaller numbers and no map internal can ever compete. */
.map-frame{--map-route-halo:rgba(255,255,255,.9);position:relative;isolation:isolate;width:100%;height:100%;min-height:300px;overflow:hidden;background:var(--panel-2)}
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
/* A chevron rather than a filled triangle: it reads as direction at 14px and
   keeps the road under it visible. The halo is the same token the route line
   uses, so it holds against both a pale and a dark map. */
:deep(.carhibou-route-arrow){pointer-events:none}
:deep(.carhibou-route-arrow span){
  display:block;width:14px;height:14px;transform:rotate(var(--angle));
  background:var(--accent);
  clip-path:polygon(18% 8%, 34% 8%, 78% 50%, 34% 92%, 18% 92%, 62% 50%);
  filter:drop-shadow(0 0 1.4px var(--map-route-halo)) drop-shadow(0 0 1.4px var(--map-route-halo));
}
.map-frame.unavailable :deep(.leaflet-tile-pane){opacity:.12}
</style>
