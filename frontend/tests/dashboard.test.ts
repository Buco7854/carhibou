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
})
