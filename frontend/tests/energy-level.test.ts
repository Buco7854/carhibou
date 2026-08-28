import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { Vehicle } from '../src/api/types'
import { energyTone } from '../src/vehicleDisplay'
import VehiclesView from '../src/views/VehiclesView.vue'
import BatteryGaugeWidget from '../src/widgets/BatteryGaugeWidget.vue'
import { dashboardRuntimeKey } from '../src/widgets/dashboardContext'
import { adminUser, jsonResponse, vehicle } from './helpers'

function withMetrics(metrics: Record<string, unknown>, overrides: Record<string, unknown> = {}): Vehicle {
  return { ...vehicle, ...overrides, state: { ...vehicle.state!, position: null, metrics } } as unknown as Vehicle
}

function mountCatalog(vehicles: Vehicle[]) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
    Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [] : vehicles))))
  return mount(VehiclesView, { global: { plugins: [i18n], stubs: { Teleport: true, RouterLink: { template: '<a><slot /></a>' } } } })
}

function mountGauge(current: Vehicle) {
  const host = defineComponent({
    setup() {
      provide(dashboardRuntimeKey, {
        vehicles: ref([current]),
        selectedVehicleId: ref(current.id),
        selectedSegment: ref(null),
        liveStatus: ref('open' as const), dataVersion: ref(0),
        selectVehicle: vi.fn(),
        selectSegment: vi.fn(),
      })
      return () => h(BatteryGaugeWidget, { widget: { id: 'w1', type: 'energy', x: 0, y: 0, w: 4, h: 3 } })
    },
  })
  return mount(host, { global: { plugins: [i18n] } })
}

/** The class the level bar's fill carries, empty string when it carries none. */
function fill(wrapper: { get: (selector: string) => { classes: () => string[] } }): string[] {
  return wrapper.get('.level-bar b').classes()
}

describe('energyTone', () => {
  it('puts both boundaries on the low side', () => {
    expect(energyTone(20)).toBe('danger')
    expect(energyTone(20.1)).toBe('warning')
    expect(energyTone(40)).toBe('warning')
    expect(energyTone(40.1)).toBe('success')
  })

  it('covers the range either side of the boundaries', () => {
    expect(energyTone(0)).toBe('danger')
    expect(energyTone(12)).toBe('danger')
    expect(energyTone(35)).toBe('warning')
    expect(energyTone(80)).toBe('success')
    expect(energyTone(100)).toBe('success')
  })

  it('stays neutral when there is no reading to tone', () => {
    expect(energyTone(null)).toBe('')
    expect(energyTone(undefined)).toBe('')
    expect(energyTone(Number.NaN)).toBe('')
  })
})

describe('the vehicle card level bar', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('tones the bar by battery level', async () => {
    for (const [soc, tone] of [[12, 'danger'], [35, 'warning'], [80, 'success']] as const) {
      const wrapper = mountCatalog([withMetrics({ 'battery.soc': soc, 'charging.active': false })])
      await flushPromises()
      expect(fill(wrapper), `${soc}%`).toContain(tone)
    }
  })

  it('tones a fuel level the same way, since it is the same reading', async () => {
    const wrapper = mountCatalog([withMetrics({ 'fuel.level': 12 })])
    await flushPromises()
    expect(wrapper.get('.vehicle-card').text()).toContain('Fuel level')
    expect(fill(wrapper)).toContain('danger')
  })

  it('leaves a card with no energy reading neutral', async () => {
    const wrapper = mountCatalog([withMetrics({ 'engine.load': 12 })])
    await flushPromises()
    // A percentage that is not an energy level still draws a bar, untoned: 12%
    // engine load is not a low battery.
    expect(wrapper.get('.vehicle-card').text()).toContain('Engine load')
    expect(fill(wrapper)).toEqual([])
  })

  it('keeps charging on the bar, whatever the level reads', async () => {
    const wrapper = mountCatalog([withMetrics({ 'battery.soc': 12, 'charging.active': true })])
    await flushPromises()
    expect(fill(wrapper)).toEqual(['is-charging'])
  })
})

describe('the energy gauge widget', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('tones the gauge by battery level', () => {
    for (const [soc, tone] of [[12, 'danger'], [35, 'warning'], [80, 'success']] as const) {
      expect(fill(mountGauge(withMetrics({ 'battery.soc': soc }))), `${soc}%`).toContain(tone)
    }
  })

  it('tones a fuel level the same way', () => {
    const wrapper = mountGauge(withMetrics({ 'fuel.level': 35 }))
    expect(wrapper.text()).toContain('Fuel level')
    expect(fill(wrapper)).toContain('warning')
  })

  it('draws no bar at all when nothing is reported', () => {
    const wrapper = mountGauge(withMetrics({}))
    expect(wrapper.find('.level-bar').exists()).toBe(false)
  })
})
