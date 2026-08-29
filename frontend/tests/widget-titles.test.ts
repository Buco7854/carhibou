import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { DashboardWidget, Vehicle } from '../src/api/types'
import { dashboardRuntimeKey } from '../src/widgets/dashboardContext'
import { needsSpecificData, widgetRegistry } from '../src/widgets/registry'
import { adminUser, mockApi, readings, vehicle } from './helpers'

vi.mock('../src/components/VehicleMap.vue', () => ({
  default: defineComponent({ setup: () => () => h('div', { class: 'vehicle-map-stub' }) }),
}))
vi.mock('../src/components/TimeSeriesChart.vue', () => ({
  default: defineComponent({ setup: () => () => h('div', { class: 'chart-stub' }) }),
}))

const EV = {
  ...vehicle,
  photo_url: null,
  state: { ...vehicle.state!, readings: readings({ 'battery.soc': 61, 'charging.power': 7, 'battery.power': -4 }) },
} as unknown as Vehicle

/** Mounts one widget and returns the text its head actually renders. */
async function head(type: string, config: Partial<DashboardWidget> = {}, current: Vehicle = EV): Promise<string> {
  mockApi({
    '/history': { vehicle_id: current.id, start: '', end: '', available_metrics: [], original_count: 0, points: [] },
    '/segments': { drives: [], charges: [] },
    default: [],
  })
  const host = defineComponent({
    setup() {
      provide(dashboardRuntimeKey, {
        vehicles: ref([current]), selectedVehicleId: ref(current.id), selectedSegment: ref(null),
        liveStatus: ref('open' as const), dataVersion: ref(0), selectVehicle: vi.fn(), selectSegment: vi.fn(),
      })
      return () => h(widgetRegistry[type]!.component, { widget: { id: 'w', type, x: 0, y: 0, w: 4, h: 3, ...config } })
    },
  })
  const wrapper = mount(host, { global: { plugins: [i18n] } })
  await flushPromises()
  return wrapper.get('.widget-head h2').text()
}

describe('opinionated cards name their data', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('titles a metric card by whatever it is bound to, raw key included', async () => {
    expect(await head('metric-card', { metric: 'battery.soc' })).toBe('Battery level')
    expect(await head('metric-card', { metric: 'vehicle.speed' })).toBe('Road speed')
    // An unknown key still announces itself rather than hiding behind a label.
    expect(await head('metric-card', { metric: 'custom.widget_count' })).toBe('custom.widget_count')
  })

  it('titles the energy gauge by the energy the vehicle actually reports', async () => {
    expect(await head('battery-gauge', {}, EV)).toBe('Battery level')
    const fuel = { ...EV, state: { ...EV.state!, readings: readings({ 'fuel.level': 48 }) } } as unknown as Vehicle
    expect(await head('battery-gauge', {}, fuel)).toBe('Fuel level')
    const bare = { ...EV, state: { ...EV.state!, readings: {} } } as unknown as Vehicle
    expect(await head('battery-gauge', {}, bare)).toBe('Energy level')
  })

  it('titles the time-series and multi-series by their metrics', async () => {
    expect(await head('time-series', { metric: 'vehicle.speed' })).toBe('Road speed')
    expect(await head('multi-series', { metrics: ['battery.soc', 'battery.power'] })).toBe('Battery level · Battery power')
    // Nothing bound yet, so the generic name rather than a blank head.
    expect(await head('multi-series', { metrics: [] })).toBe('Multi-series chart')
  })

  it('titles an x-y chart from both axes, whatever put them there', async () => {
    expect(await head('xy-chart', { x_metric: 'battery.soc', y_metric: 'battery.power' })).toBe('Battery power vs Battery level')
    expect(await head('xy-chart', { x_metric: 'vehicle.speed', y_metric: 'custom.draw' })).toBe('custom.draw vs Road speed')
    // The pair the default Overview creates is titled from its axes like any
    // other, with no concept name anywhere to borrow.
    expect(await head('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' })).toBe('Charge rate vs Battery level')
    // Unconfigured is the only case the generic name is honest.
    expect(await head('xy-chart', {})).toBe('X-Y chart')
  })

  it('says the photo card is a photo when there is no photo to speak for itself', async () => {
    expect(await head('vehicle-media', {}, EV)).toBe('Vehicle photo')
  })

  it('states the charging card explicitly', async () => {
    expect(await head('charging', {}, EV)).toBe('Charging')
  })

  it('lets a custom title win everywhere, because flagrancy is a default not a cage', async () => {
    const cases: Array<[string, Partial<DashboardWidget>]> = [
      ['metric-card', { metric: 'battery.soc' }],
      ['battery-gauge', {}],
      ['charging', {}],
      ['vehicle-media', {}],
      ['time-series', { metric: 'vehicle.speed' }],
      ['multi-series', { metrics: ['battery.soc'] }],
      ['xy-chart', { x_metric: 'battery.soc', y_metric: 'battery.power' }],
      ['xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' }],
    ]
    for (const [type, config] of cases) {
      expect(await head(type, { ...config, title: 'My card' }), type).toBe('My card')
    }
  })

  it('names every data-bound card in French too', async () => {
    i18n.global.locale.value = 'fr'
    expect(await head('metric-card', { metric: 'battery.soc' })).toBe('Niveau de batterie')
    expect(await head('battery-gauge', {}, EV)).toBe('Niveau de batterie')
    expect(await head('time-series', { metric: 'vehicle.speed' })).toBe('Vitesse')
    expect(await head('vehicle-media', {}, EV)).toBe('Photo du véhicule')
    expect(await head('xy-chart', { x_metric: 'battery.soc', y_metric: 'battery.power' }))
      .toBe('Puissance batterie en fonction de Niveau de batterie')
    expect(await head('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' }))
      .toBe('Puissance de charge en fonction de Niveau de batterie')
  })

  it('leaves no data-bound card able to render a title that names nothing', async () => {
    // Every specific card, configured as the Overview would, must render a head
    // that is neither blank nor the bare type name it shares with the picker.
    const cases: Array<[string, Partial<DashboardWidget>]> = [
      ['metric-card', { metric: 'battery.soc' }],
      ['battery-gauge', {}],
      ['charging', {}],
      ['vehicle-media', {}],
      ['time-series', { metric: 'battery.soc' }],
      ['multi-series', { metrics: ['battery.soc'] }],
      ['xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' }],
    ]
    for (const [type, config] of cases) {
      expect(needsSpecificData({ id: 'w', type, x: 0, y: 0, w: 4, h: 3, ...config }), type).toBe(true)
      const text = await head(type, config)
      expect(text.length, type).toBeGreaterThan(0)
      expect(text, type).not.toBe(i18n.global.t('dashboards.xyChart'))
    }
  })
})
