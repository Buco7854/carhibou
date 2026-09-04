import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { h } from 'vue'
import i18n from '../src/i18n'

/**
 * MapLibre, as far as this component is concerned.
 *
 * The renderer is a canvas, so nothing it draws can be asserted in a DOM test.
 * What can is everything the component puts around it: the controls, the key to
 * the colours, the readout behind a segment, and the strip a host renders inside
 * the frame. The stub keeps the handlers the component registers so a pointer
 * over the trail can be played back.
 */
type Handler = (event: unknown) => void
const handlers = new Map<string, Handler>()
const sources = new Map<string, unknown>()
const layers: string[] = []
const paint = new Map<string, unknown>()

class FakeMap {
  on(type: string, layerOrHandler: string | Handler, maybeHandler?: Handler) {
    const layer = typeof layerOrHandler === 'string' ? layerOrHandler : ''
    const handler = (typeof layerOrHandler === 'string' ? maybeHandler : layerOrHandler) as Handler
    handlers.set(layer ? `${type}:${layer}` : type, handler)
    if (type === 'load') handler({})
  }

  addControl() {}
  addSource(id: string, data: unknown) { sources.set(id, data) }
  addLayer(layer: { id: string }) { layers.push(layer.id) }
  getSource(id: string) { return sources.has(id) ? { setData: (data: unknown) => sources.set(id, data) } : undefined }
  getLayer(id: string) { return layers.includes(id) ? { id } : undefined }
  setPaintProperty(layer: string, property: string, value: unknown) { paint.set(`${layer}.${property}`, value) }
  hasImage() { return true }
  addImage() {}
  getCanvas() { return { style: {} } }
  getZoom() { return 12 }
  getMinZoom() { return 0 }
  getMaxZoom() { return 20 }
  queryRenderedFeatures() { return [] }
  easeTo() {}
  jumpTo() {}
  fitBounds() {}
  resize() {}
  remove() {}
  scrollZoom = { enable() {}, disable() {} }
}

vi.mock('maplibre-gl', () => ({
  Map: FakeMap,
  Marker: class { setLngLat() { return this } addTo() { return this } remove() {} },
  AttributionControl: class {},
  ScaleControl: class {},
  LngLatBounds: class { extend() {} },
}))
vi.mock('maplibre-gl/dist/maplibre-gl.css', () => ({}))

const { default: VehicleMap } = await import('../src/components/VehicleMap.vue')

const trail = [
  { lat: 48.85, lng: 2.35, speed: 0, at: '2026-08-27T08:00:00Z' },
  { lat: 48.86, lng: 2.36, speed: 31, at: '2026-08-27T08:10:00Z' },
  { lat: 48.87, lng: 2.37, speed: 64, at: '2026-08-27T08:20:00Z' },
  { lat: 48.88, lng: 2.38, speed: 118, at: '2026-08-27T08:30:00Z' },
]

async function draw(props: Record<string, unknown> = {}, slots: { context?: () => unknown } = {}) {
  const wrapper = mount(VehicleMap, {
    props: { position: null, trail, ...props },
    slots,
    global: { plugins: [i18n] },
  })
  await flushPromises()
  return wrapper
}

/**
 * The map's own width, which is what decides how much key it can carry.
 *
 * A real ResizeObserver reports nothing in a DOM without layout, so this one is
 * driven by hand: `resizeMap` plays the callback the component registered with
 * whatever width the case is about.
 */
const observers: Array<(entries: Array<{ contentRect: { width: number } }>) => void> = []

function resizeMap(width: number): void {
  for (const observer of observers) observer([{ contentRect: { width } }])
}

describe('the vehicle map', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    handlers.clear()
    sources.clear()
    layers.length = 0
    paint.clear()
    observers.length = 0
    globalThis.ResizeObserver = class {
      constructor(callback: (entries: Array<{ contentRect: { width: number } }>) => void) { observers.push(callback) }
      observe() {}
      unobserve() {}
      disconnect() {}
    } as never
  })

  it('offers zoom and expand as named controls a finger can hit', async () => {
    const wrapper = await draw()
    const labels = wrapper.findAll('.map-control').map((button) => button.attributes('aria-label'))
    expect(labels).toEqual(['Expand map', 'Zoom in', 'Zoom out'])
    i18n.global.locale.value = 'fr'
    await wrapper.vm.$nextTick()
    // The renderer's own control was labelled in English whatever the language.
    expect(wrapper.findAll('.map-control').map((button) => button.attributes('aria-label')))
      .toEqual(['Agrandir la carte', 'Zoomer', 'Dézoomer'])
  })

  it('keys the colours to the speeds it actually plotted', async () => {
    const wrapper = await draw()
    resizeMap(760)
    await wrapper.vm.$nextTick()
    const legend = wrapper.get('.map-legend')
    expect(legend.attributes('aria-label')).toBe('Speed scale for this route')
    expect(legend.element.tagName).toBe('DIV')
    /*
     * One label per colour, each saying its own range.
     *
     * The numbers used to sit on the boundaries with the top of the scale
     * closing the row, so three colours came with four numbers and a reader
     * counted five swatches against six values. A band says what it covers.
     */
    const bands = legend.findAll('.legend-band')
    expect(bands.map((band) => band.text())).toEqual(['0–31', '31–64', '64–118'])
    expect(legend.findAll('.legend-band i')).toHaveLength(bands.length)
    // The unit is said once, on the caption line rather than in every range.
    expect(legend.get('.legend-caption').text()).toBe('km/h')
  })

  it('collapses to a bar on a map too narrow to spend a third of on a key', async () => {
    const wrapper = await draw()
    resizeMap(360)
    await wrapper.vm.$nextTick()
    const legend = wrapper.get('.map-legend')
    // A button, because on a narrow map the key is something a reader operates.
    expect(legend.element.tagName).toBe('BUTTON')
    expect(legend.attributes('aria-label')).toBe('Speed scale, tap for ranges')
    expect(legend.attributes('aria-expanded')).toBe('false')
    // The ramp itself, then the two ends of the scale and the unit once.
    expect(legend.findAll('.legend-bar i')).toHaveLength(3)
    expect(legend.findAll('.legend-ends span').map((end) => end.text())).toEqual(['0', '118 km/h'])

    await legend.trigger('click')
    expect(wrapper.get('.map-legend').attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.map-legend').classes()).toContain('open')
    await legend.trigger('click')
    expect(wrapper.get('.map-legend').attributes('aria-expanded')).toBe('false')

    // Asking for the ranges is not remembered: a wider map is the full key
    // again, and coming back to a narrow one starts from the bar.
    await legend.trigger('click')
    resizeMap(760)
    await wrapper.vm.$nextTick()
    resizeMap(360)
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.map-legend').attributes('aria-expanded')).toBe('false')
  })

  it('offers no key when there is nothing for a colour to mean', async () => {
    const steady = trail.map((point) => ({ ...point, speed: 40 }))
    expect((await draw({ trail: steady })).find('.map-legend').exists()).toBe(false)
    expect((await draw({ trail: undefined, route: [[48.85, 2.35], [48.86, 2.36]] })).find('.map-legend').exists()).toBe(false)
  })

  it('says what a coloured segment means when a pointer asks', async () => {
    const wrapper = await draw()
    expect(wrapper.find('.map-reading').exists()).toBe(false)
    // A two-pixel line is not a target, so the trail carries a wide invisible one.
    expect(layers).toContain('carhibou-trail-hit')
    const hover = handlers.get('mousemove:carhibou-trail-hit')
    expect(hover, 'the trail carries a hit target').toBeTruthy()
    hover!({
      point: { x: 120, y: 90 },
      features: [{ properties: { speed: 64, at: '2026-08-27T08:20:00Z' } }],
    })
    await wrapper.vm.$nextTick()
    const readout = wrapper.get('.map-reading')
    expect(readout.text()).toContain('64 km/h')
    expect(readout.text()).toContain(new Date('2026-08-27T08:20:00Z').toLocaleString())
  })

  it('says so rather than inventing a speed the segment never carried', async () => {
    const wrapper = await draw()
    handlers.get('mousemove:carhibou-trail-hit')!({ point: { x: 10, y: 10 }, features: [{ properties: { speed: null, at: '' } }] })
    await wrapper.vm.$nextTick()
    expect(wrapper.get('.map-reading').text()).toContain('Speed not reported')
  })

  it('strokes a speed trail over its own casing rather than the ground halo', async () => {
    /*
     * The ramp is bright at both ends, so what it clears is the opaque dark
     * stroke under it; the plain accent route keeps the ground's own halo at
     * the translucency it has always had. The colours themselves are custom
     * properties, which a DOM without a stylesheet resolves to nothing, so
     * what is asserted here is which of the two treatments was asked for —
     * the colours are measured in the ramp test and seen in the screenshots.
     */
    await draw()
    expect(paint.get('carhibou-route-casing.line-opacity')).toBe(1)
    paint.clear()
    await draw({ trail: undefined, route: [[48.85, 2.35], [48.86, 2.36]] })
    expect(paint.get('carhibou-route-casing.line-opacity')).toBe(0.9)
  })

  it('carries its host context inside the frame, where the map goes', async () => {
    const wrapper = await draw({}, { context: () => h('p', { class: 'host-readout' }, '24.4 km') })
    expect(wrapper.get('.map-frame .map-context .host-readout').text()).toBe('24.4 km')
  })
})
