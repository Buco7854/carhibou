<script setup lang="ts">
import type { GeoJSONSource, Map as MapLibreMap, Marker as MapLibreMarker } from 'maplibre-gl'
import type { Feature, FeatureCollection } from 'geojson'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PositionFix } from '../api/types'
import { layerHost } from '../layerHost'
import { resolvedMapTheme } from '../theme'
import { styleFor } from '../mapStyle'
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
const expanded = ref(false)
const wheelHint = ref(false)
const { t } = useI18n()
const host = computed(layerHost)

/* MapLibre is about a megabyte of parser and renderer, and most pages never
   draw a map. It arrives with the first one that does. */
type MapLibre = typeof import('maplibre-gl')
let gl: MapLibre | undefined
let map: MapLibreMap | undefined
let marker: MapLibreMarker | undefined
let ready = false
let hintTimer: ReturnType<typeof setTimeout> | undefined

const ROUTE_SOURCE = 'carhibou-route'
const TRAIL_SOURCE = 'carhibou-trail'
const POINT_SOURCE = 'carhibou-points'

/*
 * Line weight.
 *
 * One weight cannot serve a view of a whole region and a view of one street. A
 * hairline reads as precise when the roads under it are hairlines too, and
 * disappears once they are forty pixels wide. Expressed as a zoom interpolation
 * rather than restyled on every zoom, which is what the renderer is for.
 */
const ROUTE_WIDTH: unknown = ['interpolate', ['linear'], ['zoom'],
  11, 1.75, 14, 2, 16, 2.5, 18, 3]
const CASING_WIDTH: unknown = ['interpolate', ['linear'], ['zoom'],
  11, 3.75, 14, 4, 16, 4.5, 18, 5]

/*
 * Spaced on screen, not along the ground, so the density a reader sees is the
 * same whatever the zoom. The renderer places these along the line and turns
 * each to the line's own direction, which is the whole of what the old
 * hand-placed markers did, for none of the arithmetic.
 *
 * The number is not the pixel gap: symbol-spacing is measured in the tile's own
 * coordinates and lands at roughly two and a half times its value on screen, so
 * this is the value that produces the ninety-odd pixels that were tuned for.
 */
const ARROW_SPACING = 40

const SPEED_STOPS = [0, 30, 60, 90, 120]

/** MapLibre paints from real colours, so the tokens are resolved here. */
function palette(): Record<string, string> {
  const styles = getComputedStyle(document.documentElement)
  const read = (name: string) => styles.getPropertyValue(name).trim()
  return {
    accent: read('--accent'),
    panel: read('--panel'),
    halo: read('--map-route-halo') || read('--panel'),
    muted: read('--muted-2'),
    chart1: read('--chart-1'), chart2: read('--chart-2'),
    chart3: read('--chart-3'), chart4: read('--chart-4'),
  }
}

function speedColor(speed: number | null, colors: Record<string, string>): string {
  if (speed === null) return colors.muted!
  const slot = SPEED_STOPS.findIndex((stop) => speed < stop)
  return colors[`chart${slot <= 0 ? 4 : Math.min(slot, 4)}`]!
}

/* Leaflet spoke in [lat, lng] and MapLibre speaks in [lng, lat]; every crossing
   goes through here so the flip is in one place rather than twenty. */
function lngLat(at: [number, number]): [number, number] {
  return [at[1], at[0]]
}

function routeCoordinates(): Array<[number, number]> {
  if (props.trail?.length) return props.trail.map((point) => [point.lng, point.lat])
  return (props.route ?? []).map(lngLat)
}

/*
 * Where the car is, and which way it faces.
 *
 * A fix is a point, so it is drawn as one: a dot the size of a road marking,
 * cased in the panel colour so it holds on any ground, and a needle on that
 * casing for the heading. No heading, no needle: falling back to zero degrees
 * drew a car pointing due north on every fix that never reported a bearing.
 */
function positionElement(heading: number | null | undefined): HTMLElement {
  const known = Number.isFinite(heading)
  // The same shape the old renderer produced, so the styling and everything
  // that looks for a vehicle on the map still finds one.
  const wrap = document.createElement('span')
  wrap.className = 'carhibou-position-marker'
  const puck = document.createElement('span')
  puck.className = `position-puck${known ? ' has-heading' : ''}`
  puck.style.setProperty('--heading', `${known ? Number(heading) : 0}deg`)
  puck.appendChild(document.createElement('i'))
  wrap.appendChild(puck)
  return wrap
}

/**
 * The chevron the direction layer repeats, drawn once at the screen's density.
 *
 * A stroked arrowhead rather than a filled wedge: it reads as direction at this
 * size and keeps the road under it visible, which is what the hand-placed
 * markers did before. The halo is what holds it against a pale road.
 */
const CHEVRON_PX = 13

function chevronImage(color: string, halo: string): ImageData {
  const scale = Math.max(1, Math.round(window.devicePixelRatio || 1))
  const size = CHEVRON_PX * scale
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')!
  const draw = (stroke: string, width: number) => {
    context.strokeStyle = stroke
    context.lineWidth = width * scale
    context.lineCap = 'round'
    context.lineJoin = 'round'
    context.beginPath()
    context.moveTo(0.3 * size, 0.16 * size)
    context.lineTo(0.72 * size, 0.5 * size)
    context.lineTo(0.3 * size, 0.84 * size)
    context.stroke()
  }
  draw(halo, 3.4)
  draw(color, 1.8)
  return context.getImageData(0, 0, size, size)
}

function emptyCollection(): FeatureCollection {
  return { type: 'FeatureCollection', features: [] }
}

/*
 * Whether the map may still choose its own viewport.
 *
 * Live state arrives every few seconds and each arrival redraws the layers. It
 * must not also re-frame: a reader who panned across town to look at something
 * had the map yanked back under them on the next upload. So the map frames
 * itself once for a subject, and after that the viewport belongs to the reader.
 */
let framedSubject: string | undefined
let framedOnce = false

function frame(apply: () => void): void {
  const subject = props.subject ?? ''
  if (framedOnce && framedSubject === subject) return
  framedOnce = true
  framedSubject = subject
  apply()
}

/*
 * Whether the car is already marking the end of the route.
 *
 * A route ends where the car last was, so a map showing both draws two dots for
 * one fact: one with a heading needle and one without, a stone's throw apart,
 * reading as two vehicles. The plotted route is a downsample of what the car
 * reported, so the two never coincide exactly and no distance threshold
 * separates them cleanly. Whenever the car is on the map, it is the end, and
 * the line running into it says so. The start keeps its dot: nothing else says
 * where a drive began.
 */
function vehicleMarksTheEnd(): boolean {
  return Boolean(props.position)
}

function draw(): void {
  if (!map || !gl || !ready) return
  const colors = palette()
  const path = routeCoordinates()

  const route = map.getSource(ROUTE_SOURCE) as GeoJSONSource | undefined
  route?.setData(path.length > 1
    ? { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: path } }
    : emptyCollection())

  // One feature per leg, each carrying the colour its speed earns.
  const legs: Feature[] = []
  if (props.trail?.length) {
    for (let index = 0; index < props.trail.length - 1; index += 1) {
      const from = props.trail[index]!
      const to = props.trail[index + 1]!
      legs.push({
        type: 'Feature',
        properties: { color: speedColor(from.speed, colors) },
        geometry: { type: 'LineString', coordinates: [[from.lng, from.lat], [to.lng, to.lat]] },
      })
    }
  }
  ;(map.getSource(TRAIL_SOURCE) as GeoJSONSource | undefined)
    ?.setData({ type: 'FeatureCollection', features: legs })

  // Endpoints and the picked trail points share one source: they are all
  // single points drawn as circles, and one source is one update.
  const points: Feature[] = []
  const start = path[0]
  if (start && path.length > 1) {
    points.push({ type: 'Feature', properties: { kind: 'start' }, geometry: { type: 'Point', coordinates: start } })
  }
  const end = path.at(-1)
  if (end && path.length > 1 && !vehicleMarksTheEnd()) {
    points.push({ type: 'Feature', properties: { kind: 'end' }, geometry: { type: 'Point', coordinates: end } })
  }
  props.trail?.forEach((point, index) => {
    points.push({
      type: 'Feature',
      properties: { kind: 'pick', index, picked: props.marks?.includes(index) ? 1 : 0, color: speedColor(point.speed, colors) },
      geometry: { type: 'Point', coordinates: [point.lng, point.lat] },
    })
  })
  ;(map.getSource(POINT_SOURCE) as GeoJSONSource | undefined)
    ?.setData({ type: 'FeatureCollection', features: points })

  marker?.remove()
  marker = undefined
  if (props.position) {
    marker = new gl.Marker({ element: positionElement(props.position.heading) })
      .setLngLat([props.position.longitude, props.position.latitude])
      .addTo(map)
  }

  if (path.length > 1) {
    frame(() => {
      const bounds = new gl!.LngLatBounds(path[0]!, path[0]!)
      for (const at of path) bounds.extend(at)
      map!.fitBounds(bounds, { padding: 34, maxZoom: 15, animate: false })
    })
  } else if (props.position) {
    frame(() => map!.jumpTo({ center: [props.position!.longitude, props.position!.latitude], zoom: 14 }))
  }
}

/* Adding a source fires styledata, which is also what asks for the drawing to
   be put back after a style swap. Without this the first add re-enters and
   tries to register everything twice. */
let installing = false

function install(): void {
  if (!map || !gl || installing) return
  installing = true
  try {
    addLayers()
  } finally {
    installing = false
  }
}

function addLayers(): void {
  if (!map || !gl) return
  const colors = palette()
  if (!map.hasImage('carhibou-chevron')) {
    map.addImage('carhibou-chevron', chevronImage(colors.accent!, colors.halo!), { pixelRatio: Math.max(1, Math.round(window.devicePixelRatio || 1)) })
  }
  map.addSource(ROUTE_SOURCE, { type: 'geojson', data: emptyCollection() })
  map.addSource(TRAIL_SOURCE, { type: 'geojson', data: emptyCollection() })
  map.addSource(POINT_SOURCE, { type: 'geojson', data: emptyCollection() })

  // The single-colour route keeps a casing; the speed ramp does not need one.
  map.addLayer({
    id: 'carhibou-route-casing', type: 'line', source: ROUTE_SOURCE,
    filter: ['==', ['geometry-type'], 'LineString'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': colors.halo!, 'line-width': CASING_WIDTH as never, 'line-opacity': props.trail?.length ? 0 : 0.9 },
  })
  map.addLayer({
    id: 'carhibou-route-line', type: 'line', source: ROUTE_SOURCE,
    filter: ['==', ['geometry-type'], 'LineString'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': colors.accent!, 'line-width': ROUTE_WIDTH as never, 'line-opacity': props.trail?.length ? 0 : 1 },
  })
  map.addLayer({
    id: 'carhibou-trail-line', type: 'line', source: TRAIL_SOURCE,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': ['get', 'color'] as never, 'line-width': ROUTE_WIDTH as never },
  })
  map.addLayer({
    id: 'carhibou-direction', type: 'symbol', source: ROUTE_SOURCE,
    layout: {
      'symbol-placement': 'line',
      'symbol-spacing': ARROW_SPACING,
      'icon-image': 'carhibou-chevron',
      'icon-rotation-alignment': 'map',
      'icon-allow-overlap': true,
      'icon-ignore-placement': true,
    },
  })
  map.addLayer({
    id: 'carhibou-picks', type: 'circle', source: POINT_SOURCE,
    filter: ['==', ['get', 'kind'], 'pick'],
    paint: {
      // The unpicked ones are the click targets and are never drawn.
      'circle-radius': ['case', ['==', ['get', 'picked'], 1], 4.5, 4] as never,
      'circle-color': ['get', 'color'] as never,
      'circle-opacity': ['case', ['==', ['get', 'picked'], 1], 1, 0] as never,
      'circle-stroke-color': colors.accent!,
      'circle-stroke-width': ['case', ['==', ['get', 'picked'], 1], 1.75, 0] as never,
    },
  })
  map.addLayer({
    id: 'carhibou-endpoint', type: 'circle', source: POINT_SOURCE,
    filter: ['!=', ['get', 'kind'], 'pick'],
    paint: {
      // Punctuation on the line, not a second vehicle: half the size of the
      // position marker, and without the casing that lifts it off the ground.
      'circle-radius': 3.5,
      'circle-color': ['case', ['==', ['get', 'kind'], 'start'], colors.panel!, colors.accent!] as never,
      'circle-stroke-color': colors.accent!,
      'circle-stroke-width': 1.5,
    },
  })

  map.on('click', 'carhibou-picks', (event) => {
    const index = event.features?.[0]?.properties?.['index']
    if (typeof index === 'number') emit('pick', index)
  })
  map.on('mouseenter', 'carhibou-picks', () => { if (map) map.getCanvas().style.cursor = 'pointer' })
  map.on('mouseleave', 'carhibou-picks', () => { if (map) map.getCanvas().style.cursor = '' })

  /*
   * What the renderer drew, for the tests that ask.
   *
   * Routes and endpoints are painted into a canvas now, so unlike the old
   * renderer there is no DOM node to count. The end-to-end checks assert what
   * reached the screen rather than what this component believes it asked for,
   * and this is the only way to let them.
   */
  ;(element.value as unknown as { carhibouMap?: unknown }).carhibouMap = map
}

/*
 * Wheel zoom, without stealing the page.
 *
 * Expanded, the map is the page and the wheel is its own. On a card inside a
 * scrolling page it is not, so a plain wheel scrolls past as it always did and
 * ctrl or command plus wheel zooms, which is the convention every embedded map
 * has settled on. Anyone who wheels without the modifier is told, once. Pinch
 * is untouched: on a touch screen there is no ambiguity to resolve.
 */
function applyWheelPolicy(): void {
  if (!map) return
  if (expanded.value) map.scrollZoom.enable()
  else map.scrollZoom.disable()
}

function onWheel(event: WheelEvent): void {
  if (!map || expanded.value) return
  if (event.ctrlKey || event.metaKey) {
    event.preventDefault()
    const point = map.unproject([event.offsetX, event.offsetY])
    map.easeTo({ zoom: map.getZoom() - Math.sign(event.deltaY), around: point, duration: 120 })
    return
  }
  wheelHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => { wheelHint.value = false }, 1400)
}

function toggleExpanded(): void {
  expanded.value = !expanded.value
  wheelHint.value = false
  applyWheelPolicy()
  // The frame changes size when it moves, and the renderer only knows once told.
  requestAnimationFrame(() => map?.resize())
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape' && expanded.value) toggleExpanded()
}

async function build(): Promise<void> {
  // The stylesheet rides in the same lazy chunk, so a page without a map pays
  // for neither the renderer nor its CSS.
  await import('maplibre-gl/dist/maplibre-gl.css')
  gl = await import('maplibre-gl')
  if (!element.value) return
  map = new gl.Map({
    container: element.value,
    style: styleFor(resolvedMapTheme.value),
    center: [0, 20],
    zoom: 1.4,
    attributionControl: false,
    scrollZoom: false,
    // A vector map has no reason to stop where a raster tileset ran out.
    maxZoom: 20,
  })
  // Their guide: with MapLibre the attribution is added automatically, because
  // the tile source declares it. Nothing is passed here on purpose.
  map.addControl(new gl.AttributionControl({ compact: true }), 'bottom-right')
  map.addControl(new gl.NavigationControl({ showCompass: false }), 'bottom-right')
  map.addControl(new gl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-left')
  map.on('error', () => { tilesUnavailable.value = true })
  map.on('load', () => {
    tilesLoading.value = false
    tilesUnavailable.value = false
    ready = true
    install()
    draw()
  })
  // A style swap drops every layer this component owns, so they go back on.
  map.on('styledata', () => {
    if (!ready || !map || map.getSource(ROUTE_SOURCE)) return
    install()
    draw()
  })
}

onMounted(() => {
  void build()
  document.addEventListener('keydown', onKeydown)
})

watch(() => [props.position, props.route, props.trail, props.marks], draw, { deep: true })
// Another vehicle, or another range, is another thing to look at: that earns a
// new frame, which is what this releases.
watch(() => props.subject, () => { framedOnce = false; draw() })
watch(resolvedMapTheme, (theme) => { map?.setStyle(styleFor(theme)) })

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  clearTimeout(hintTimer)
  marker?.remove()
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
/* The halo the route casing and the chevrons are drawn against, which is the
   panel colour of whichever theme the map itself is wearing. */
:global([data-theme="dark"] .map-frame){--map-route-halo:rgba(13,16,14,.86)}

/* The marker's own box: the renderer positions this absolutely, and an inline
   span would collapse to nothing around its child. */
:deep(.carhibou-position-marker){display:block;width:26px;height:26px;background:transparent;border:0}
/* A fix is a point. The dot is the point; the casing is what makes it hold on
   a pale road or a dark one; the shadow only lifts it off the ground. */
:deep(.position-puck){position:relative;width:26px;height:26px;display:grid;place-items:center;filter:drop-shadow(0 1px 2px rgba(16,24,20,.3))}
:deep(.position-puck i){width:12px;height:12px;background:var(--accent);border:2px solid var(--panel);border-radius:50%}
/* The needle rotates the whole box about the dot, which keeps it on the ring at
   every bearing without a transform origin to get wrong. */
:deep(.position-puck.has-heading::after){
  content:"";position:absolute;inset:4px;background:var(--accent);
  clip-path:polygon(50% 0, 63% 20%, 37% 20%);
  transform:rotate(var(--heading));
  filter:drop-shadow(0 0 1px var(--panel));
}

.map-state,.map-empty{position:absolute;z-index:500;top:10px;left:10px;padding:5px 8px;color:var(--muted);background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:var(--radius);font:400 12px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none}
.map-empty{top:50%;left:50%;max-width:220px;transform:translate(-50%,-50%);color:var(--text);text-align:center}
.unavailable-message{color:var(--danger)}


/* MapLibre's own controls, dressed to match the rest of the interface. */
:deep(.maplibregl-ctrl-group){margin:0 10px 10px 0!important;overflow:hidden;background:transparent!important;border:1px solid var(--line-strong)!important;border-radius:var(--radius)!important;box-shadow:var(--shadow-soft)!important}
:deep(.maplibregl-ctrl-group button){width:28px!important;height:26px!important;background:color-mix(in srgb,var(--panel) 94%,transparent)!important;border-bottom:1px solid var(--line)!important}
:deep(.maplibregl-ctrl-group button:last-child){border-bottom:0!important}
:deep(.maplibregl-ctrl-group button:hover){background:var(--panel)!important}
:deep(.maplibregl-ctrl-scale){margin:0 0 10px 10px!important;padding:1px 6px;color:var(--muted);background:color-mix(in srgb,var(--panel) 82%,transparent);border-color:var(--line-strong);border-top:0;font:400 11px/1.5 var(--mono)}
:deep(.maplibregl-ctrl-attrib){padding:2px 5px!important;color:var(--muted);background:color-mix(in srgb,var(--panel) 84%,transparent)!important;font-size:11px}
:deep(.maplibregl-ctrl-attrib a){color:var(--accent)}
:deep(.maplibregl-ctrl-attrib-button){background-color:transparent!important}
:deep(.maplibregl-canvas){outline:none}
/* The renderer's own glyphs are dark artwork; in dark theme they are inverted
   rather than replaced, which is the one thing left worth filtering. */
:global([data-theme="dark"] .map-frame .maplibregl-ctrl-group button span){filter:invert(1)}

/* Nothing to draw the ground with: dim what did arrive rather than pretend. */
.map-frame.unavailable :deep(.maplibregl-canvas){opacity:.12}

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
