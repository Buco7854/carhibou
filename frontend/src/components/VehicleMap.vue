<script setup lang="ts">
import type { GeoJSONSource, Map as MapLibreMap, MapGeoJSONFeature, Marker as MapLibreMarker } from 'maplibre-gl'
import type { Feature, FeatureCollection } from 'geojson'
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { PositionFix } from '../api/types'
import { layerHost } from '../layerHost'
import { resolvedMapStyle } from '../mapPreferences'
import { bandFor, speedBands, type SpeedBand } from '../mapSpeedScale'
import { SPEED_KEY, formatInstant, formatMetricNumber, metricDefinition } from '../vehicleDisplay'
import AppIcon from './AppIcon.vue'

export interface TrailPoint { lat: number; lng: number; speed: number | null; at?: string }

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
  /**
   * What this map is of, said on the map itself once it fills the viewport.
   *
   * A card names its map in its own head, which the expanded map leaves behind
   * on the page underneath. Rather than repeat the head in the card, the name
   * is shown only where it would otherwise be missing.
   */
  heading?: string | undefined
}>()
const emit = defineEmits<{ pick: [index: number] }>()
const frame = ref<HTMLDivElement>()
const element = ref<HTMLDivElement>()
const tilesLoading = ref(true)
const tilesUnavailable = ref(false)
const expanded = ref(false)
const wheelHint = ref(false)
const { t, locale } = useI18n()
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
const TRAIL_HIT_LAYER = 'carhibou-trail-hit'

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

/** Wide enough to hit with a thumb, and never drawn. */
const TRAIL_HIT_WIDTH = 20

/*
 * Which cartography is under the drawing.
 *
 * Map style and interface theme are separate settings, so a light interface can
 * carry a dark basemap. Everything painted onto the ground — the route ramp, the
 * halo that holds it — belongs to the ground's tone rather than to the
 * interface's. The floating chips are app chrome and stay with the interface.
 */
const darkGround = computed(() => resolvedMapStyle.value.style.tone === 'dark')

const speedDefinition = metricDefinition(SPEED_KEY)

/** The bands the plotted speeds earn. Empty when nothing reported a speed. */
const scale = computed(() => speedBands((props.trail ?? []).map((point) => point.speed)))
/** A scale of one band encodes nothing, so it is not offered as a key. */
const legend = computed<SpeedBand[]>(() => (scale.value.length > 1 ? scale.value : []))
const legendHasUnknown = computed(() => Boolean(legend.value.length
  && props.trail?.some((point) => typeof point.speed !== 'number')))
const legendFloor = computed(() => legend.value[0]?.from ?? 0)
const legendTop = computed(() => legend.value.at(-1)?.to ?? 0)

/*
 * How much room the key has.
 *
 * The same card is 360 pixels wide on a phone and twice that in a desktop
 * column. Five labelled ranges are worth their space on the second and take a
 * third of the map on the first, so under 480 pixels of canvas the key is a bar
 * with the two ends of the scale on it, and a reader who wants the ranges asks
 * for them. Asking is not remembered: the key returns to the bar on the next
 * card, because the bar is what it should be most of the time.
 */
const COMPACT_MAP_WIDTH = 480
const compactLegend = ref(false)
const legendOpen = ref(false)
let sizeObserver: ResizeObserver | undefined

const legendAttrs = computed(() => (compactLegend.value
  ? { type: 'button', 'aria-expanded': legendOpen.value ? 'true' : 'false', 'aria-label': t('history.speedLegendToggle') }
  : { role: 'group', 'aria-label': t('history.speedLegend') }))

function toggleLegend(): void {
  if (compactLegend.value) legendOpen.value = !legendOpen.value
}

function watchMapWidth(): void {
  if (!element.value || typeof ResizeObserver === 'undefined') return
  sizeObserver = new ResizeObserver((entries) => {
    const width = entries[0]?.contentRect.width ?? element.value?.clientWidth ?? 0
    if (!width) return
    compactLegend.value = width < COMPACT_MAP_WIDTH
    if (!compactLegend.value) legendOpen.value = false
  })
  sizeObserver.observe(element.value)
}

function speedLabel(speed: number): string {
  return formatMetricNumber(speed, speedDefinition, locale.value)
}

/**
 * One band, said as the range it covers.
 *
 * The numbers used to sit on the boundaries between swatches, with the top of
 * the scale closing the row: an axis, and correct, but five colours came with
 * six numbers and it read as one number per band plus a stray. A band now
 * carries its own two ends, which is the thing a reader wants anyway — what a
 * colour on the line means, without counting along the row to work it out.
 */
function bandLabel(band: SpeedBand): string {
  return `${speedLabel(band.from)}\u2013${speedLabel(band.to)}`
}

/**
 * MapLibre paints from real colours, so the tokens are resolved here.
 *
 * Read from the frame rather than from the document, because the ramp and the
 * halo are declared on the frame and follow the basemap's tone.
 */
function palette(): Record<string, string> {
  const styles = getComputedStyle(frame.value ?? document.documentElement)
  const read = (name: string) => styles.getPropertyValue(name).trim()
  const colors: Record<string, string> = {
    accent: read('--accent'),
    panel: read('--panel'),
    halo: read('--map-route-halo') || read('--panel'),
    trailCasing: read('--trail-casing'),
    chevronInk: read('--map-chevron-ink'),
    chevronHalo: read('--map-chevron-halo'),
    muted: read('--muted-2'),
  }
  for (let step = 1; step <= 5; step += 1) colors[`trail${step}`] = read(`--trail-${step}`)
  return colors
}

/** The ramp step a speed earns, or the muted ink when it reported none. */
function speedColor(speed: number | null, colors: Record<string, string>): string {
  const band = bandFor(speed, scale.value)
  return band ? colors[`trail${band.step}`] || colors.muted! : colors.muted!
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
  const scaling = Math.max(1, Math.round(window.devicePixelRatio || 1))
  const size = CHEVRON_PX * scaling
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const context = canvas.getContext('2d')!
  const draw = (stroke: string, width: number) => {
    context.strokeStyle = stroke
    context.lineWidth = width * scaling
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

function frameOnce(apply: () => void): void {
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
  const painted = Boolean(props.trail?.length)

  // Which line the casing is under can change without the style reloading, so
  // it is set here rather than only where the layer is added.
  if (map.getLayer('carhibou-route-casing')) {
    map.setPaintProperty('carhibou-route-casing', 'line-color', painted ? colors.trailCasing! : colors.halo!)
    map.setPaintProperty('carhibou-route-casing', 'line-opacity', painted ? 1 : 0.9)
  }

  const route = map.getSource(ROUTE_SOURCE) as GeoJSONSource | undefined
  route?.setData(path.length > 1
    ? { type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: path } }
    : emptyCollection())

  // One feature per leg, each carrying the colour its speed earns and the
  // reading that earned it, so hovering the line can say what it means.
  const legs: Feature[] = []
  if (props.trail?.length) {
    for (let index = 0; index < props.trail.length - 1; index += 1) {
      const from = props.trail[index]!
      const to = props.trail[index + 1]!
      legs.push({
        type: 'Feature',
        properties: {
          color: speedColor(from.speed, colors),
          speed: from.speed,
          at: from.at ?? '',
          index,
        },
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
    frameOnce(() => {
      const bounds = new gl!.LngLatBounds(path[0]!, path[0]!)
      for (const at of path) bounds.extend(at)
      map!.fitBounds(bounds, { padding: 34, maxZoom: 15, animate: false })
    })
  } else if (props.position) {
    frameOnce(() => map!.jumpTo({ center: [props.position!.longitude, props.position!.latitude], zoom: 14 }))
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
    bindInteractions()
  } finally {
    installing = false
  }
}

function addLayers(): void {
  if (!map || !gl) return
  const colors = palette()
  if (!map.hasImage('carhibou-chevron')) {
    map.addImage('carhibou-chevron', chevronImage(colors.chevronInk!, colors.chevronHalo!), { pixelRatio: Math.max(1, Math.round(window.devicePixelRatio || 1)) })
  }
  map.addSource(ROUTE_SOURCE, { type: 'geojson', data: emptyCollection() })
  map.addSource(TRAIL_SOURCE, { type: 'geojson', data: emptyCollection() })
  map.addSource(POINT_SOURCE, { type: 'geojson', data: emptyCollection() })

  /*
   * Both lines keep a casing, and the trail's is not the route's.
   *
   * The speed ramp is a cold-to-hot sweep, so its bands run from a mid blue to
   * a light amber and no single ground can hold all five: the casing carries
   * that contrast instead. It is a dark, opaque stroke under the colour, which
   * clears the pale basemap by 15.7:1 and leaves every band at least 3:1
   * against the casing it sits on. The plain accent route keeps the ground's
   * own halo, which is what a single dark-blue line wants.
   */
  map.addLayer({
    id: 'carhibou-route-casing', type: 'line', source: ROUTE_SOURCE,
    filter: ['==', ['geometry-type'], 'LineString'],
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': colors.halo!, 'line-width': CASING_WIDTH as never, 'line-opacity': 0.9 },
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
  // A two-pixel line is not a target. This one is never painted; it exists so a
  // pointer near the trail counts as a pointer on it.
  map.addLayer({
    id: TRAIL_HIT_LAYER, type: 'line', source: TRAIL_SOURCE,
    layout: { 'line-cap': 'round', 'line-join': 'round' },
    paint: { 'line-color': colors.accent!, 'line-width': TRAIL_HIT_WIDTH, 'line-opacity': 0 },
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
      // The unpicked ones are never drawn, so their radius is a target size
      // rather than a mark size: a downsampled trail puts its points far
      // enough apart that a thumb needs the room.
      'circle-radius': ['case', ['==', ['get', 'picked'], 1], 5, 9] as never,
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
 * The reading behind a coloured segment.
 *
 * Colour on its own is decoration: a reader could see that one stretch is
 * redder than another and had no way to learn what either meant. Pointing at
 * the trail says the speed and when it was measured; on a touch screen the
 * same tap pins it, and a tap anywhere else puts it away.
 */
interface TrailReading { speed: number | null; at: string; x: number; y: number; below: boolean; pinned: boolean }
const reading = ref<TrailReading | null>(null)

const readingText = computed(() => {
  const current = reading.value
  if (!current) return null
  return {
    speed: current.speed === null
      ? t('history.speedUnknown')
      : `${speedLabel(current.speed)} ${speedDefinition.unit}`,
    at: current.at ? formatInstant(current.at) : '',
  }
})

const readingStyle = computed(() => {
  const current = reading.value
  if (!current) return undefined
  return {
    left: `${current.x}px`,
    top: `${current.y + (current.below ? 18 : -14)}px`,
    transform: current.below ? 'translate(-50%,0)' : 'translate(-50%,-100%)',
  }
})

function showReading(feature: MapGeoJSONFeature | undefined, at: { x: number; y: number }, pinned: boolean): void {
  if (!feature) return
  const speed = feature.properties?.['speed']
  const observed = feature.properties?.['at']
  const width = element.value?.clientWidth ?? 0
  reading.value = {
    speed: typeof speed === 'number' ? speed : null,
    at: typeof observed === 'string' ? observed : '',
    // Kept clear of the frame's edges, so the readout is never half off the map.
    x: width ? Math.min(Math.max(at.x, 76), width - 76) : at.x,
    y: at.y,
    below: at.y < 70,
    pinned,
  }
}

let interactionsBound = false

function bindInteractions(): void {
  if (!map || interactionsBound) return
  interactionsBound = true
  const cursor = (shape: string) => { if (map) map.getCanvas().style.cursor = shape }

  map.on('click', 'carhibou-picks', (event) => {
    const index = event.features?.[0]?.properties?.['index']
    if (typeof index === 'number') emit('pick', index)
  })
  map.on('mouseenter', 'carhibou-picks', () => cursor('pointer'))
  map.on('mouseleave', 'carhibou-picks', () => cursor(''))

  map.on('mousemove', TRAIL_HIT_LAYER, (event) => {
    cursor('pointer')
    if (!reading.value?.pinned) showReading(event.features?.[0], event.point, false)
  })
  map.on('mouseleave', TRAIL_HIT_LAYER, () => {
    cursor('')
    if (!reading.value?.pinned) reading.value = null
  })
  // One handler for the whole canvas rather than two that race: a tap on the
  // trail pins its reading, and a tap anywhere else dismisses it.
  map.on('click', (event) => {
    const found = map?.queryRenderedFeatures(event.point, { layers: [TRAIL_HIT_LAYER] }) ?? []
    if (found.length) showReading(found[0], event.point, true)
    else reading.value = null
  })
  // The readout is anchored in screen pixels, so it stops meaning anything the
  // moment the ground moves under it.
  map.on('movestart', () => { reading.value = null })
  map.on('zoom', trackZoom)
}

/*
 * How far in the map already is.
 *
 * The zoom buttons are the app's own, so they also own saying when they can do
 * nothing: a control that looks live and answers nothing reads as a broken map.
 */
const zoomLevel = ref(0)
const zoomFloor = ref(0)
const zoomCeiling = ref(20)
const canZoomIn = computed(() => zoomLevel.value < zoomCeiling.value - 0.01)
const canZoomOut = computed(() => zoomLevel.value > zoomFloor.value + 0.01)

function trackZoom(): void {
  if (!map) return
  zoomLevel.value = map.getZoom()
  zoomFloor.value = map.getMinZoom()
  zoomCeiling.value = map.getMaxZoom()
}

function zoomBy(step: number): void {
  if (!map) return
  reading.value = null
  map.easeTo({ zoom: map.getZoom() + step, duration: 180 })
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

/* A map over the whole viewport is the only thing on it, so the page behind it
   does not scroll while it is open. */
function lockPage(locked: boolean): void {
  document.body.style.overflow = locked ? 'hidden' : ''
}

function toggleExpanded(): void {
  expanded.value = !expanded.value
  wheelHint.value = false
  reading.value = null
  applyWheelPolicy()
  lockPage(expanded.value)
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
    style: resolvedMapStyle.value.url,
    center: [0, 20],
    zoom: 1.4,
    attributionControl: false,
    scrollZoom: false,
    // A vector map has no reason to stop where a raster tileset ran out.
    maxZoom: 20,
  })
  /*
   * Their guide: with MapLibre the attribution is added automatically, because
   * the tile source declares it. Nothing is passed here on purpose, and no
   * option either: left to decide for itself the control carries the full
   * credit on a map wide enough for it and the compact toggle on a card, which
   * is the behaviour a 300-pixel widget and a full viewport both want.
   */
  map.addControl(new gl.AttributionControl(), 'bottom-right')
  map.addControl(new gl.ScaleControl({ maxWidth: 70, unit: 'metric' }), 'bottom-left')
  map.on('error', () => { tilesUnavailable.value = true })
  map.on('load', () => {
    tilesLoading.value = false
    tilesUnavailable.value = false
    ready = true
    install()
    trackZoom()
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
  watchMapWidth()
  document.addEventListener('keydown', onKeydown)
})

watch(() => [props.position, props.route, props.trail, props.marks], draw, { deep: true })
// Another vehicle, or another range, is another thing to look at: that earns a
// new frame, which is what this releases.
watch(() => props.subject, () => { framedOnce = false; reading.value = null; draw() })
// A new basemap is a new style, and a style swap puts the drawing back with
// the ramp and the halo the new ground earns.
watch(() => resolvedMapStyle.value.url, (url) => { map?.setStyle(url) })

onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  sizeObserver?.disconnect()
  clearTimeout(hintTimer)
  lockPage(false)
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
      ref="frame"
      class="map-frame"
      :class="{ unavailable: tilesUnavailable, expanded, 'dark-ground': darkGround }"
      :aria-busy="tilesLoading"
      @wheel="onWheel"
    >
      <div class="map-view">
        <div ref="element" class="vehicle-map" role="region" :aria-label="heading || t('history.route')" />
        <span v-if="!position && !route?.length" class="map-empty">{{ t('dashboard.noPosition') }}</span>
        <span v-if="wheelHint" class="map-hint" role="status">{{ t('history.wheelHint') }}</span>

        <!--
          Everything the map says about itself, in one column.

          The renderer owns the two bottom corners: the scale bar on the left and
          the attribution on the right, which opens itself on load and wraps to
          two or three lines on a phone. Anything of ours parked down there has
          to be placed around a height only MapLibre knows, so none of it is: the
          chips and the key stack from the top-left corner instead, in reading
          order, and the credit keeps the whole bottom to itself.
        -->
        <div class="map-corner">
          <span v-if="expanded && heading" class="map-heading">{{ heading }}</span>
          <span v-if="tilesLoading && !tilesUnavailable" class="map-state" aria-live="polite">{{ t('history.mapLoading') }}</span>
          <span v-if="tilesUnavailable" class="map-state unavailable-message" role="status">{{ t('history.mapUnavailable') }}</span>

          <!--
            What the colours on the trail stand for.

            The edges are the drive's own, so they are printed rather than
            implied by a gradient. Both renditions are in the markup and the
            width decides which one shows: on a narrow map the ramp is one bar
            carrying the ends of the scale, and the whole chip is the control
            that opens the ranges — by tap, or by keyboard focus, which reveals
            them without changing what the next reader sees.
          -->
          <component
            :is="compactLegend ? 'button' : 'div'"
            v-if="legend.length"
            class="map-legend"
            :class="{ 'is-compact': compactLegend, open: legendOpen }"
            v-bind="legendAttrs"
            @click="toggleLegend"
          >
            <span class="legend-strip">
              <span class="legend-bar">
                <i v-for="band in legend" :key="band.step" :style="{ background: `var(--trail-${band.step})` }" />
              </span>
              <span class="legend-ends">
                <span>{{ speedLabel(legendFloor) }}</span>
                <span>{{ speedLabel(legendTop) }} {{ speedDefinition.unit }}</span>
              </span>
            </span>
            <span class="legend-full">
              <span class="legend-bands">
                <span v-for="band in legend" :key="band.step" class="legend-band">
                  <i :style="{ background: `var(--trail-${band.step})` }" />
                  <span>{{ bandLabel(band) }}</span>
                </span>
              </span>
              <span class="legend-caption">
                <span>{{ speedDefinition.unit }}</span>
                <span v-if="legendHasUnknown" class="legend-unknown"><i />{{ t('history.speedUnknown') }}</span>
              </span>
            </span>
          </component>
        </div>

        <div v-if="readingText" class="map-reading" :style="readingStyle" aria-hidden="true">
          <strong>{{ readingText.speed }}</strong>
          <span v-if="readingText.at">{{ readingText.at }}</span>
        </div>

        <div class="map-controls">
          <button
            class="map-control map-expand"
            type="button"
            :aria-label="expanded ? t('history.mapCollapse') : t('history.mapExpand')"
            @click="toggleExpanded"
          >
            <AppIcon :name="expanded ? 'close' : 'expand'" :size="16" />
          </button>
          <div class="map-zoom">
            <button class="map-control" type="button" :disabled="!canZoomIn" :aria-label="t('history.mapZoomIn')" @click="zoomBy(1)">
              <AppIcon name="plus" :size="16" />
            </button>
            <button class="map-control" type="button" :disabled="!canZoomOut" :aria-label="t('history.mapZoomOut')" @click="zoomBy(-1)">
              <AppIcon name="minus" :size="16" />
            </button>
          </div>
        </div>
      </div>

      <!--
        Whatever the card said about this map, said inside the map.

        It used to sit in the card around the frame, and the frame is what
        travels to the viewport when the map is expanded: the reader who opened
        the map to see the route better lost the readout describing it. Kept in
        here, it goes where the map goes.
      -->
      <div v-if="$slots.context" class="map-context"><slot name="context" /></div>
    </div>
  </Teleport>
</template>

<style scoped>
/* Leaflet numbers its own panes from 200 to 700 and its controls at 1000, all
   as plain z-indexes. Without a stacking context of its own the map spends
   those numbers in the page's context, where they outrank the nav rail and
   the mobile nav bar. Isolating the frame confines them, so app chrome wins
   on its own much smaller numbers and no map internal can ever compete. */
.map-frame{
  /*
   * The ramp the speed trail is painted with: cold to hot as the car goes faster.
   *
   * Two earlier ramps were single-hue and stepped by lightness. The first
   * measured 8.5 ΔE2000 between neighbouring bands, the second 18.8, and a
   * reader on a phone could separate neither: at two pixels wide, lightness is
   * the channel a line has least of. Hue is the one it has most of, so the ramp
   * sweeps blue → cyan → green → amber → red with at least 52° of OKLCH hue
   * between neighbours and 41.9 ΔE2000 at its tightest — twice the previous
   * ramp's separation, and the order reads as temperature rather than as depth.
   *
   * One ramp for both basemaps, which the casing below is what makes possible:
   * the same speed is the same colour whichever cartography is under it, rather
   * than a per-ground set a reader has to learn twice.
   */
  --trail-1:#555cca;--trail-2:#05cee5;--trail-3:#389121;--trail-4:#feaf0f;--trail-5:#bd393b;
  /*
   * The stroke under the ramp, and the reason the ramp can be this bright.
   *
   * A cold-to-hot sweep cannot hold 3:1 against a near-white basemap at both
   * ends — the amber band alone would need a luminance no amber has — so the
   * contrast against the ground is carried by an opaque dark casing (15.7:1 on
   * the pale ground) and every band clears the casing instead, by 3.09:1 at
   * worst. On a dark basemap the same casing beats a pale one measurably: with
   * a near-white casing the cyan and amber bands would sit at 1.56:1 and
   * 1.51:1 against their own outline, against 8.99:1 and 9.31:1 here.
   */
  --trail-casing:#1b1b1b;
  /*
   * Direction, in achromatic ink.
   *
   * The chevrons were the accent blue, which is 6.6 ΔE2000 from the ramp's own
   * slowest band at the same lightness: two blues on one line, one meaning
   * "this way" and one meaning "23 km/h". Neutral ink keeps direction and speed
   * on different channels, and reads on all five bands (3.1:1 at worst) with
   * the pale halo carrying it on the dark ones.
   */
  --map-chevron-ink:#1b1b1b;
  --map-chevron-halo:rgba(255,255,255,.92);
  --map-route-halo:rgba(255,255,255,.9);
  position:relative;isolation:isolate;width:100%;height:100%;min-height:300px;
  display:grid;grid-template-rows:minmax(0,1fr) auto;overflow:hidden;background:var(--panel-2);
}
/*
 * The ground's tone, not the interface's: a light interface may carry a dark
 * basemap, and the ink drawn onto the ground belongs to the ground.
 *
 * The speed ramp is deliberately not here. It is stroked over its own casing
 * rather than over the cartography, so it does not change with the ground; only
 * what the plain accent route is haloed against does.
 */
.map-frame.dark-ground{
  --map-route-halo:rgba(16,16,16,.86);
}
/* A query container, so the key can size itself to the map rather than to the
   window: the same widget is 360 pixels wide on a phone and 300 in a narrow
   dashboard column, and the viewport says nothing about either. */
.map-view{position:relative;min-height:0;min-width:0;container-type:inline-size}
.vehicle-map{width:100%;height:100%;min-height:300px;background:var(--panel-2)}

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

/* The corner the map speaks from: one column, so each chip is placed by the one
   above it rather than by a hand-tuned offset that the next chip invalidates. */
.map-corner{
  position:absolute;z-index:550;top:10px;left:10px;
  max-width:calc(100% - 20px);
  display:flex;flex-direction:column;align-items:flex-start;gap:6px;
  pointer-events:none;
}
.map-state,.map-empty,.map-heading{padding:5px 8px;color:var(--muted);background:color-mix(in srgb,var(--panel) 90%,transparent);border:1px solid var(--line);border-radius:var(--radius);font:400 12px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none}
.map-heading{max-width:100%;overflow:hidden;color:var(--text);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.map-empty{position:absolute;z-index:500;top:50%;left:50%;max-width:220px;transform:translate(-50%,-50%);color:var(--text);text-align:center}
.unavailable-message{color:var(--danger)}

/* What a colour on the trail is worth, in the numbers of this drive. Opaque:
   the swatches are being compared with each other, and whatever the map draws
   underneath is one more thing between the reader and that comparison. */
.map-legend{
  padding:6px 8px 5px;color:var(--muted);
  background:var(--panel);
  border:1px solid var(--line);border-radius:var(--radius);
  font:400 11px/1.3 "IBM Plex Sans",sans-serif;pointer-events:none;
}
/* Swatches deep enough to compare against each other: a four-pixel sliver of
   colour is no more legible in the key than it is on the line, and the gap
   between two of them is what stops the row reading as one gradient. */
.legend-bands{display:flex;flex-wrap:nowrap;align-items:flex-end;gap:3px}
.legend-band{min-width:0;display:grid;gap:4px}
.legend-band i{width:100%;height:9px;border-radius:2px}
/* Each band is labelled with its own range, centred under the colour it
   describes, and never wraps: a key that reflows is a key that has to be read
   twice. The swatch takes the width its range needs. */
.legend-band span{padding:0 3px;font-size:var(--font-caption);font-variant-numeric:tabular-nums;text-align:center;white-space:nowrap}
.legend-caption{display:flex;align-items:center;gap:10px;margin-top:4px;color:var(--muted-2)}
.legend-unknown{display:inline-flex;align-items:center;gap:5px}
.legend-unknown i{width:12px;height:9px;border-radius:2px;background:var(--muted-2)}

/* The bar the key collapses to: the ramp itself, its two ends, and the unit. */
.legend-strip{display:none}
.legend-bar{display:flex;gap:2px;width:112px;height:9px}
.legend-bar i{flex:1;border-radius:2px}
.legend-ends{display:flex;justify-content:space-between;gap:12px;margin-top:4px;font-size:var(--font-micro);font-variant-numeric:tabular-nums;white-space:nowrap}
.legend-full{display:grid;justify-items:start}
/* Narrow map: the bar, and the ranges only while asked for. A keyboard reader
   gets them on focus, which asks for nothing and changes no state. */
.map-legend.is-compact{pointer-events:auto;text-align:left;cursor:pointer}
.map-legend.is-compact .legend-strip{display:grid}
.map-legend.is-compact .legend-full{display:none}
.map-legend.is-compact.open .legend-strip,
.map-legend.is-compact:focus-visible .legend-strip{display:none}
.map-legend.is-compact.open .legend-full,
.map-legend.is-compact:focus-visible .legend-full{display:grid}
.map-legend.is-compact:hover{border-color:var(--line-strong)}
.map-legend.is-compact:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
/* Narrow map, same five ranges once open: the type steps down to the smallest
   size in the scale before anything is allowed to wrap or be cut. */
@container (max-width: 340px){
  .map-legend{padding:5px 6px 4px}
  .legend-bands{gap:2px}
  .legend-band span{padding:0 2px;font-size:var(--font-micro)}
}

/* The reading behind a segment, anchored where the pointer asked. */
.map-reading{
  position:absolute;z-index:600;display:grid;gap:1px;
  min-width:96px;padding:6px 9px;
  color:var(--text);background:var(--panel);
  border:1px solid var(--line-strong);border-radius:var(--radius);
  box-shadow:var(--shadow-soft);pointer-events:none;
}
.map-reading strong{font-size:13px;font-weight:500;font-variant-numeric:tabular-nums}
.map-reading span{color:var(--muted);font-size:11px}

/*
 * The map's own controls, as app buttons rather than as the renderer's.
 *
 * The zoom pair used to be MapLibre's navigation control: 29 pixels square,
 * with its own artwork, its own English-only labels and a hairline between the
 * two halves that stayed white whatever the theme. Owning the buttons is what
 * makes them the size of a target, legible on either ground, named in the
 * reader's language and styled once with everything else.
 */
.map-controls{position:absolute;z-index:600;top:8px;right:8px;display:grid;gap:8px;justify-items:end}
.map-zoom{display:grid;overflow:hidden;border-radius:var(--radius)}
.map-control{
  width:34px;height:34px;display:grid;place-items:center;
  color:var(--text);background:color-mix(in srgb,var(--panel) 94%,transparent);
  border:1px solid var(--line-strong);border-radius:var(--radius);cursor:pointer;
  box-shadow:var(--shadow-soft);
  transition:background-color .12s,border-color .12s,color .12s;
}
.map-control:hover:not(:disabled){background:var(--panel);color:var(--accent)}
.map-control:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.map-control:disabled{color:var(--muted-2);cursor:not-allowed}
/* One block of two: a shared hairline between them rather than two rings. */
.map-zoom .map-control{border-radius:0}
.map-zoom .map-control:first-child{border-radius:var(--radius) var(--radius) 0 0}
.map-zoom .map-control:last-child{border-top-width:0;border-radius:0 0 var(--radius) var(--radius)}
/* A finger is not a mouse pointer: where there is no hover, the targets grow to
   the size the platform guidelines ask for. */
@media(hover:none){
  .map-control{width:42px;height:42px}
  .map-controls{gap:10px}
}

/* Whatever the card said about the map, carried inside the frame. */
.map-context{
  min-width:0;padding:9px 12px;
  background:var(--panel);border-top:1px solid var(--line);
}
.map-frame.expanded .map-context{padding:10px 16px;box-shadow:0 -1px 0 var(--line)}

/* MapLibre's remaining chrome, dressed to match the rest of the interface. */
:deep(.maplibregl-ctrl-scale){margin:0 0 10px 10px!important;padding:1px 6px;color:var(--muted);background:color-mix(in srgb,var(--panel) 82%,transparent);border-color:var(--line-strong);border-top:0;font:400 11px/1.5 var(--mono)}
/*
 * The attribution, which has to stay readable and complete.
 *
 * The compact form parks a 24-pixel toggle over the text's own box and reserves
 * room for it with padding; a flat padding override took that room away, so the
 * button sat on top of "OpenStreetMap". The reservation is restored here, on the
 * side the control actually sits, and the text wraps rather than being clipped.
 */
/*
 * MapLibre's own compact CSS sets its own black text colour on this same
 * element (`.maplibregl-ctrl-attrib.maplibregl-compact`, two classes, the same
 * specificity as ours below); its stylesheet loads after this component's
 * scoped one, since MapLibre itself is imported lazily, so on a tie it was
 * winning and painting "Data from" black on the dark panel behind it.
 * !important is the deciding vote, not just a stronger selector.
 */
:deep(.maplibregl-ctrl-attrib){
  /* The bottom row belongs to the renderer's two controls, and on a phone the
     credit is wide enough to reach the scale bar in the opposite corner. The
     reservation is the scale's own strip plus both margins: a 70-pixel bar and
     its padding come to about 92, and the credit starts clear of that. */
  max-width:min(460px,calc(100% - 128px));margin:0 10px 10px 0!important;padding:3px 8px;
  color:var(--muted)!important;background:color-mix(in srgb,var(--panel) 88%,transparent)!important;
  border:1px solid var(--line);border-radius:var(--radius)!important;
  font:400 11px/1.45 "IBM Plex Sans",sans-serif;white-space:normal;
}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact){min-height:26px;padding:0}
:deep(.maplibregl-ctrl-attrib.maplibregl-compact-show){padding:4px 34px 4px 9px}
/*
 * Anchored to the bottom edge, not the top. The control hangs from the map's
 * bottom-right corner, so when the credit opens and wraps to a second line the
 * box grows upward: a top-anchored toggle rode that edge and jumped every time
 * it was tapped. The bottom edge is the one that stays put.
 */
:deep(.maplibregl-ctrl-attrib-button){
  top:auto;bottom:1px;right:1px;width:24px;height:24px;
  background-color:transparent!important;border-radius:var(--radius-sm);opacity:.75;
}
:deep(.maplibregl-ctrl-attrib-button:hover){opacity:1}
/*
 * MapLibre draws its blue box-shadow on :focus, which a tap or click also
 * satisfies, so that is where it is cancelled; the ring itself is reserved for
 * :focus-visible, as the rest of the interface does, so a tap leaves no halo.
 */
:deep(.maplibregl-ctrl-attrib-button:focus){box-shadow:none!important;outline:none}
:deep(.maplibregl-ctrl-attrib-button:focus-visible){outline:2px solid var(--accent)!important;outline-offset:1px}
:deep(.maplibregl-ctrl-attrib a){color:var(--accent)}
:deep(.maplibregl-canvas){outline:none}
/* The renderer's own glyph is dark artwork on a panel that is not, in one theme
   of two; inverting it is cheaper than replacing the control. */
:global([data-theme="dark"] .map-frame .maplibregl-ctrl-attrib-button){filter:invert(1)}
/*
 * The dark-theme filter above inverts this button's own focus ring along with
 * its glyph, which turned MapLibre's blue (#0096ff) into an orange (#ff6900)
 * once the two combined. Rather than special-case the filter around focus (and
 * lose the glyph's contrast while focused), the ring's colour is pre-inverted
 * so the filter lands it back on var(--accent): 255-0x60,255-0xa5,255-0xfa.
 */
:global([data-theme="dark"] .map-frame .maplibregl-ctrl-attrib-button:focus-visible){outline-color:#9f5a05!important}

/* Nothing to draw the ground with: dim what did arrive rather than pretend. */
.map-frame.unavailable :deep(.maplibregl-canvas){opacity:.12}

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
