<script setup lang="ts">
import L from 'leaflet'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PositionFix } from '../api/types'
import { layerHost } from '../layerHost'
import AppIcon from './AppIcon.vue'

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
let tiles: L.TileLayer | undefined
let tileErrors = 0
const expanded = ref(false)
const wheelHint = ref(false)
let hintTimer: ReturnType<typeof setTimeout> | undefined
const host = computed(layerHost)

/*
 * Wheel zoom, without stealing the page.
 *
 * Expanded, the map is the page and the wheel is its own: nothing else wants
 * that gesture. On a card inside a scrolling page it does, so a plain wheel
 * scrolls past as it always did and ctrl or command plus wheel zooms, which is
 * the convention every embedded map has settled on. Anyone who wheels without
 * the modifier is told, once, rather than left wondering why nothing happened.
 * Pinch is untouched: on a touch screen there is no ambiguity to resolve.
 */
function onWheel(event: WheelEvent): void {
  if (!map || expanded.value) return
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    const point = map.mouseEventToContainerPoint(event)
    map.setZoomAround(map.containerPointToLatLng(point), map.getZoom() - Math.sign(event.deltaY))
    return
  }
  wheelHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => { wheelHint.value = false }, 1400)
}

function toggleExpanded(): void {
  expanded.value = !expanded.value
  wheelHint.value = false
  if (expanded.value) map?.scrollWheelZoom.enable()
  else map?.scrollWheelZoom.disable()
  // The frame changes size when it moves, and Leaflet only knows once told.
  requestAnimationFrame(() => map?.invalidateSize())
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && expanded.value) toggleExpanded()
}

/*
 * The ground the map is drawn on.
 *
 * CARTO's Positron and Dark Matter were the obvious answer here, and they are
 * what this tried first: purpose-built neutral palettes, one per theme, with
 * native @2x tiles. They now watermark every tile with "API KEY REQUIRED"
 * unless you hold a key, so they are not something this can ship. Anything else
 * with a real dark basemap wants a key too.
 *
 * So the source stays OpenStreetMap and the two real problems are fixed
 * directly. detectRetina is what sharpens it: osm.org serves no @2x tiles, but
 * Leaflet answers a hi-DPI screen by fetching one zoom deeper and drawing those
 * into half the space, which is the same pixel density by another route and
 * works against any raster source.
 */
const BASEMAP_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'

function basemap(): L.TileLayer {
  const layer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: BASEMAP_ATTRIBUTION,
    maxZoom: 19,
    detectRetina: true,
  })
  layer.on('loading', () => { tilesLoading.value = true; tileErrors = 0 })
  layer.on('tileerror', () => { tileErrors += 1; if (tileErrors >= 2) tilesUnavailable.value = true })
  layer.on('load', () => { tilesLoading.value = false; if (tileErrors === 0) tilesUnavailable.value = false })
  return layer
}
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
    iconSize: [11, 11],
    iconAnchor: [5.5, 5.5],
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
    /*
     * Punctuation on the line, not a second vehicle.
     *
     * These used to be the size of the position marker and filled with the same
     * accent, so an endpoint beside the car read as another car. They are now
     * half the size and carry no casing, which is what the position marker uses
     * to stand off the map.
     */
    radius: 3.5,
    color: 'var(--accent)',
    weight: 1.5,
    // The end is filled and the start is hollow, so which is which survives
    // being read at a glance and in either theme.
    fillColor: kind === 'start' ? 'var(--panel)' : 'var(--accent)',
    fillOpacity: 1,
  }).addTo(target)
  mark.bindTooltip(t(kind === 'start' ? 'history.routeStart' : 'history.routeEnd'), { direction: 'top', offset: [0, -5] })
  return mark
}

/*
 * Line weight.
 *
 * One weight cannot serve a view of a whole region and a view of one street. A
 * hairline reads as precise when the roads under it are hairlines too, and
 * disappears once they are forty pixels wide. This is the only thing that
 * scales: the casing stays a single pixel either side at every zoom, which is
 * what lets a thin line hold against a busy map without becoming a band.
 */
function routeWeight(zoom: number): number {
  if (zoom <= 11) return 1.75
  if (zoom <= 14) return 2
  if (zoom <= 16) return 2.5
  return 3
}

const CASING_EXTRA = 2

const SPEED_STOPS = [0, 30, 60, 90, 120]

function speedColor(speed: number | null): string {
  if (speed === null) return 'var(--muted-2)'
  const slot = SPEED_STOPS.findIndex((stop) => speed < stop)
  return `var(--chart-${slot <= 0 ? 4 : Math.min(slot, 4)})`
}

function drawTrail(target: L.Map, points: TrailPoint[]): void {
  const bounds: Array<[number, number]> = points.map((point) => [point.lat, point.lng] as [number, number])
  const weight = routeWeight(target.getZoom())
  /*
   * No casing here, unlike the single-colour route.
   *
   * The speed ramp is already saturated against neutralized tiles, so a casing
   * bought no separation and cost two pixels of width on a line the whole point
   * of this pass was to thin. The plain accent route keeps one because a single
   * colour has less to hold it apart from the map.
   */
  for (let index = 0; index < points.length - 1; index += 1) {
    const from = points[index]!
    const to = points[index + 1]!
    const pair: Array<[number, number]> = [[from.lat, from.lng], [to.lat, to.lng]]
    trailLayers.push(L.polyline(pair, { color: speedColor(from.speed), weight, opacity: 1, lineCap: 'round' }).addTo(target))
  }
  points.forEach((point, index) => {
    const picked = props.marks?.includes(index) ?? false
    const dot = L.circleMarker([point.lat, point.lng], {
      // The unpicked ones are the click targets and are never drawn; a picked
      // one only has to be found, not to announce itself.
      radius: picked ? 4.5 : 4,
      color: picked ? 'var(--accent)' : 'transparent',
      weight: picked ? 1.75 : 2,
      fillColor: speedColor(point.speed),
      fillOpacity: picked ? 1 : 0,
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

/*
 * Where the car is, and which way it faces.
 *
 * This was a thirty-four pixel disc of concentric rings, which on a street-level
 * view covered the junction it was meant to point at. What a fix actually is is
 * a point, so it is drawn as one: a dot the size of a road marking, cased in the
 * panel colour so it holds on any tile, and a needle outside it for the heading.
 *
 * No heading, no needle. It used to fall back to zero degrees, which drew a car
 * pointing due north on every fix that never reported a bearing.
 */
function positionIcon(heading: number | null | undefined): L.DivIcon {
  const known = Number.isFinite(heading)
  return L.divIcon({
    className: 'carhibou-position-marker',
    html: `<span class="position-puck${known ? ' has-heading' : ''}" style="--heading:${known ? Number(heading) : 0}deg"><i></i></span>`,
    iconSize: [26, 26],
    iconAnchor: [13, 13],
  })
}

/** Restyles the lines in place, which is cheaper than rebuilding them. */
function applyWeights(): void {
  if (!map) return
  const weight = routeWeight(map.getZoom())
  polyline?.setStyle({ weight })
  routeHalo?.setStyle({ weight: weight + CASING_EXTRA })
  for (const layer of trailLayers) {
    if (!(layer instanceof L.Polyline) || layer instanceof L.CircleMarker) continue
    layer.setStyle({ weight })
  }
}

/** Rebuilds only the arrows, leaving the lines and markers where they are. */
function redrawDirection(): void {
  if (!map) return
  for (const layer of directionLayers) layer.remove()
  directionLayers = []
  if (props.trail?.length) drawDirection(map, props.trail.map((point) => [point.lat, point.lng] as L.LatLngTuple))
  else if (props.route?.length) drawDirection(map, props.route)
}

/*
 * Whether the car is already marking the end of the route.
 *
 * A route ends where the car last was, so a map showing both draws two dots for
 * one fact: one with a heading needle and one without, a stone's throw apart,
 * reading as two vehicles. That is what a reader saw. The two never coincide
 * exactly either, because the plotted route is a downsample of what the car
 * reported, so no distance threshold separates "the same place" from "not" -
 * whenever the car is on the map, it is the end, and the line running into it
 * says so without a second mark. The start keeps its dot: nothing else says
 * where a drive began.
 */
function vehicleMarksTheEnd(): boolean {
  return Boolean(props.position)
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
    if (trailEnd && props.trail.length > 1 && !vehicleMarksTheEnd()) {
      endMarker = endpoint(map, [trailEnd.lat, trailEnd.lng], 'end')
    }
  } else if (props.route?.length) {
    const weight = routeWeight(map.getZoom())
    routeHalo = L.polyline(props.route, { color: 'var(--map-route-halo)', weight: weight + CASING_EXTRA, opacity: 0.9, lineCap: 'round', lineJoin: 'round', interactive: false }).addTo(map)
    polyline = L.polyline(props.route, { color: 'var(--accent)', weight, opacity: 1, lineCap: 'round', lineJoin: 'round' }).addTo(map)
    drawDirection(map, props.route)
    const routeStart = props.route[0]
    const routeEnd = props.route.at(-1)
    if (routeStart) startMarker = endpoint(map, routeStart, 'start')
    if (routeEnd && props.route.length > 1 && !vehicleMarksTheEnd()) {
      endMarker = endpoint(map, routeEnd, 'end')
    }
    frame(() => map!.fitBounds(polyline!.getBounds(), { padding: [28, 28], maxZoom: 15 }))
  }
  marker?.remove()
  marker = undefined
  if (props.position) {
    const point = L.latLng(props.position.latitude, props.position.longitude)
    marker = L.marker(point, { icon: positionIcon(props.position.heading), keyboard: false }).addTo(map)
    marker.bindTooltip(t('history.latestPosition'), { direction: 'top', offset: [0, -10] })
    if (!props.route?.length && !props.trail?.length) frame(() => map!.setView(point, 14))
  }
}

onMounted(() => {
  map = L.map(element.value!, {
    zoomControl: false,
    attributionControl: true,
    // Off by the card's rules; the expanded view turns it on. Pinch stays on
    // everywhere, because a two-finger gesture asks for nothing else.
    scrollWheelZoom: false,
    touchZoom: true,
    minZoom: 2,
  }).setView([20, 0], 2)
  tiles = basemap()
  tiles.addTo(map)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  L.control.scale({ position: 'bottomleft', imperial: false, maxWidth: 90 }).addTo(map)
  // Arrow spacing is measured on screen and only the visible ones are built, so
  // both moving and zooming invalidate the set that is currently drawn.
  map.on('moveend zoomend', redrawDirection)
  map.on('zoomend', applyWeights)
  update()
  requestAnimationFrame(() => map?.invalidateSize())
  document.addEventListener('keydown', onKeydown)
})
watch(() => [props.position, props.route, props.trail, props.marks], update, { deep: true })
// Another vehicle, or another range, is another thing to look at: that earns a
// fresh frame, and nothing else does.
watch(() => props.subject, () => { framed = false; update() })
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  clearTimeout(hintTimer)
  map?.remove()
})
</script>

<template>
  <!-- The card keeps its shape while the map is away, so expanding does not
       collapse the dashboard behind it. -->
  <div v-if="expanded" class="map-placeholder" aria-hidden="true" />
  <!-- Teleported rather than rebuilt: the same element moves, so every layer,
       the viewport and the reader's own panning all survive the trip. -->
  <Teleport :to="host" :disabled="!expanded">
    <div
      class="map-frame"
      :class="{ unavailable: tilesUnavailable, expanded }"
      :aria-busy="tilesLoading"
      @wheel="onWheel"
    >
      <div ref="element" class="vehicle-map" role="region" :aria-label="t('history.route')" />
      <span v-if="tilesLoading && !tilesUnavailable" class="map-state" aria-live="polite">{{ t('history.mapLoading') }}</span>
      <span v-if="tilesUnavailable" class="map-state unavailable-message" role="status">{{ t('history.mapUnavailable') }}</span>
      <span v-if="!position && !route?.length" class="map-empty">{{ t('dashboard.noPosition') }}</span>
      <span v-if="wheelHint" class="map-hint" role="status">{{ t('history.wheelHint') }}</span>
      <button
        class="map-expand"
        type="button"
        :aria-label="expanded ? t('history.mapCollapse') : t('history.mapExpand')"
        @click="toggleExpanded"
      >
        <AppIcon :name="expanded ? 'close' : 'expand'" :size="15" />
      </button>
    </div>
  </Teleport>
</template>

<style scoped>
/* Leaflet numbers its own panes from 200 to 700 and its controls at 1000, all
   as plain z-indexes. Without a stacking context of its own the map spends
   those numbers in the page's context, where they outrank the nav rail and
   the mobile nav bar. Isolating the frame confines them, so app chrome wins
   on its own much smaller numbers and no map internal can ever compete. */
.map-frame{--map-route-halo:rgba(255,255,255,.9);position:relative;isolation:isolate;width:100%;height:100%;min-height:300px;overflow:hidden;background:var(--panel-2)}
.vehicle-map{width:100%;height:100%;min-height:300px;background:var(--panel-2)}
:global([data-theme="dark"] .map-frame){--map-route-halo:rgba(13,16,14,.86)}
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
/* A fix is a point. The dot is the point; the casing is what makes it hold on
   a pale road or a dark one; the shadow only lifts it off the tile. */
:deep(.position-puck){position:relative;width:26px;height:26px;display:grid;place-items:center;filter:drop-shadow(0 1px 2px rgba(16,24,20,.3))}
:deep(.position-puck i){width:12px;height:12px;background:var(--accent);border:2px solid var(--panel);border-radius:50%}
/* The needle rotates the whole box about the dot, which keeps it on the ring at
   every bearing without a transform origin to get wrong. */
/* Sat at the edge of a 26px box while the dot shrank to 12px, which left it
   floating clear of the marker and reading as a mark of its own. Pulled in so
   it touches the casing it belongs to. */
:deep(.position-puck.has-heading::after){
  content:"";position:absolute;inset:4px;background:var(--accent);
  clip-path:polygon(50% 0, 63% 20%, 37% 20%);
  transform:rotate(var(--heading));
  filter:drop-shadow(0 0 1px var(--panel));
}
.map-state,.map-empty{position:absolute;z-index:500;top:10px;left:10px;padding:5px 8px;color:var(--muted);background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:var(--radius);font:400 12px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none}
.map-empty{top:50%;left:50%;max-width:220px;transform:translate(-50%,-50%);color:var(--text);text-align:center}
.unavailable-message{color:var(--danger)}
/* A chevron rather than a filled triangle: it reads as direction at 14px and
   keeps the road under it visible. The halo is the same token the route line
   uses, so it holds against both a pale and a dark map. */
:deep(.carhibou-route-arrow){pointer-events:none}
:deep(.carhibou-route-arrow span){
  display:block;width:11px;height:11px;transform:rotate(var(--angle));
  background:var(--accent);
  clip-path:polygon(18% 8%, 34% 8%, 78% 50%, 34% 92%, 18% 92%, 62% 50%);
  filter:drop-shadow(0 0 1.2px var(--map-route-halo));
}
/*
 * Light: a gentle desaturation, so the map recedes behind what is drawn on it.
 *
 * Dark: an inversion, not a dimming. brightness(.5) over light cartography is
 * what produced the washed, half-transparent look a reader reported, because
 * turning a white map down gives grey, not dark. Inverting makes land genuinely
 * dark and paper-white labels legible again; the hue rotation puts the colours
 * back the right way round afterwards, so water is blue rather than orange.
 */
:deep(.leaflet-tile-pane){filter:grayscale(.35) saturate(.7) contrast(.92) brightness(1.03)}
:global([data-theme="dark"] .map-frame .leaflet-tile-pane){
  filter:invert(1) hue-rotate(180deg) saturate(.32) brightness(.88) contrast(.88);
}

.map-frame.unavailable :deep(.leaflet-tile-pane){opacity:.12}

/* An icon on the map, where the map's own controls are, rather than a bar of
   chrome above it. */
.map-expand{
  position:absolute;z-index:600;top:8px;right:8px;width:30px;height:30px;
  display:grid;place-items:center;color:var(--text);
  background:color-mix(in srgb,var(--panel) 92%,transparent);
  border:1px solid var(--line);border-radius:var(--radius);cursor:pointer;
  transition:background-color .12s,border-color .12s;
}
.map-expand:hover{background:var(--panel);border-color:var(--line-strong)}
.map-expand:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

/* Full viewport, above everything, and the same element that was in the card. */
.map-frame.expanded{
  position:fixed;inset:0;z-index:3000;width:100%;height:100%;
  border-radius:0;box-shadow:none;
}
.map-placeholder{width:100%;height:100%;min-height:300px;background:var(--panel-2);border-radius:inherit}

.map-hint{
  position:absolute;z-index:600;top:50%;left:50%;transform:translate(-50%,-50%);
  padding:7px 12px;color:var(--text);background:color-mix(in srgb,var(--panel) 94%,transparent);
  border:1px solid var(--line);border-radius:var(--radius);
  font:400 12px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none;
}
</style>
