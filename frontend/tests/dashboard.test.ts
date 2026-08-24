import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import DashboardView from '../src/views/DashboardView.vue'
import { jsonResponse, vehicle } from './helpers'

describe('live dashboard', () => {
  it('renders current SOC, position-derived speed, and online status from the API', async () => {
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
  })
})
