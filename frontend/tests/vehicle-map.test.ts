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

describe('the vehicle map', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    handlers.clear()
    sources.clear()
    layers.length = 0
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
    const legend = wrapper.get('.map-legend')
    expect(legend.attributes('aria-label')).toBe('Speed scale for this route')
    // Four points, so four edges plus the top of the scale, all from this drive.
    expect(legend.text()).toContain('0')
    expect(legend.text()).toContain('118')
    expect(legend.text()).toContain('km/h')
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

  it('carries its host context inside the frame, where the map goes', async () => {
    const wrapper = await draw({}, { context: () => h('p', { class: 'host-readout' }, '24.4 km') })
    expect(wrapper.get('.map-frame .map-context .host-readout').text()).toBe('24.4 km')
  })
})
