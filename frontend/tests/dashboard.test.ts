import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import DashboardView from '../src/views/DashboardView.vue'
import { jsonResponse, vehicle } from './helpers'
import { TestEventSource } from './setup'

describe('live dashboard', () => {
  it('renders current SOC, position-derived speed, and online status from the API', async () => {
    TestEventSource.instances = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/history')) return Promise.resolve(jsonResponse({ vehicle_id: vehicle.id, start: '', end: '', available_metrics: ['battery.soc'], original_count: 1, points: [{ id:'s1',recorded_at:new Date().toISOString(),latitude:48,longitude:2,speed:42,heading:90,metrics:{'battery.soc':70} }] }))
      return Promise.resolve(jsonResponse([vehicle]))
    }))
    const wrapper = mount(DashboardView, {
      global: { plugins: [i18n], stubs: { RouterLink: { template:'<a><slot /></a>' }, VehicleMap: { template:'<div data-map />' }, TimeSeriesChart: { template:'<div data-chart />' } } },
    })
    await flushPromises()
    expect(wrapper.text()).toContain('70')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.text()).toContain('Online')
    expect(wrapper.find('[data-map]').exists()).toBe(true)
    const stream = TestEventSource.instances.at(-1)
    expect(stream?.url).toBe('/api/v1/events/stream')
    stream?.open()
    stream?.emit('vehicle.states', JSON.stringify({
      type: 'vehicle.states',
      version: 1,
      occurred_at: new Date().toISOString(),
      vehicles: [{ ...vehicle, state: { ...vehicle.state, updated_at: new Date().toISOString(), metrics: { ...vehicle.state?.metrics, 'battery.soc': 64 } } }],
    }))
    await flushPromises()
    expect(wrapper.text()).toContain('Live updates')
    expect(wrapper.text()).toContain('64')
    wrapper.unmount()
    expect(stream?.closed).toBe(true)
  })

  it('renders fuel and engine telemetry instead of EV concepts for combustion vehicles', async () => {
    TestEventSource.instances = []
    const thermalVehicle = {
      ...vehicle,
      id: 'thermal-1',
      name: 'Touring',
      manufacturer: 'Peugeot',
      model: '508',
      propulsion_type: 'diesel',
      battery_nominal_capacity_kwh: null,
      vehicle_profile: null,
      state: {
        ...vehicle.state,
        metrics: { 'fuel.level': 58, 'engine.rpm': 1850, 'engine.coolant_temperature': 91 },
      },
    }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/history')) return Promise.resolve(jsonResponse({
        vehicle_id: thermalVehicle.id,
        start: '',
        end: '',
        available_metrics: ['engine.rpm', 'fuel.level'],
        original_count: 1,
        points: [{ id: 's1', recorded_at: new Date().toISOString(), latitude: 48, longitude: 2, speed: 88, heading: 90, metrics: { 'fuel.level': 58, 'engine.rpm': 1850 } }],
      }))
      return Promise.resolve(jsonResponse([thermalVehicle]))
    }))
    const wrapper = mount(DashboardView, {
      global: { plugins: [i18n], stubs: { RouterLink: { template:'<a><slot /></a>' }, VehicleMap: { template:'<div data-map />' }, TimeSeriesChart: { template:'<div data-chart />' } } },
    })
    await flushPromises()

    expect(wrapper.get('.energy-state').text()).toContain('Fuel level')
    expect(wrapper.get('.energy-state strong').text()).toBe('58')
    expect(wrapper.get('.telemetry-ledger').text()).toContain('Engine speed')
    expect(wrapper.get('.telemetry-ledger').text()).toContain('1850')
    expect(wrapper.get('.telemetry-ledger').text()).toContain('Coolant temperature')
    expect(wrapper.text()).not.toContain('Traction battery')
    expect(wrapper.text()).not.toContain('Battery power')
    wrapper.unmount()
  })
})
