import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import HistoryView from '../src/views/HistoryView.vue'
import { adminUser, mockApi, vehicle } from './helpers'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'vehicle-1' } }),
  RouterLink: defineComponent({ setup: (_props, { slots }) => () => h('a', slots.default?.()) }),
}))

vi.mock('../src/components/VehicleMap.vue', () => ({
  default: defineComponent({ setup: () => () => h('div', { class: 'vehicle-map-stub' }) }),
}))

vi.mock('../src/components/TimeSeriesChart.vue', () => ({
  default: defineComponent({ setup: () => () => h('div', { class: 'chart-stub' }) }),
}))

const emptyHistory = {
  vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 0, points: [],
}

const populatedHistory = {
  vehicle_id: vehicle.id, start: '', end: '', available_metrics: ['battery.soc'], original_count: 2,
  points: [
    { id: 'p1', recorded_at: '2026-08-27T08:00:00Z', latitude: 48.85, longitude: 2.35, speed: 12, heading: 90, metrics: { 'battery.soc': 80 } },
    { id: 'p2', recorded_at: '2026-08-27T08:10:00Z', latitude: 48.86, longitude: 2.36, speed: 20, heading: 92, metrics: { 'battery.soc': 78 } },
  ],
}

function mountHistory(history: unknown) {
  mockApi({
    '/history/entries': { vehicle_id: vehicle.id, start: '', end: '', total: 0, limit: 50, offset: 0, metric_keys: [], agent_keys: [], entries: [] },
    '/history': history,
    default: vehicle,
  })
  return mount(HistoryView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
}

describe('history view with no telemetry', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('stands the metric picker down instead of offering an empty list', async () => {
    const wrapper = mountHistory(emptyHistory)
    await flushPromises()

    const metricSelect = wrapper.findAllComponents(AppSelect)[0]!
    const trigger = metricSelect.get('.app-select-trigger')
    // The defect: an empty label on a control that looks usable but cannot open.
    expect(trigger.text()).toBe('No metrics recorded')
    expect(trigger.attributes('disabled')).toBeDefined()

    await trigger.trigger('click')
    expect(wrapper.find('.app-select-menu').exists()).toBe(false)
    expect(wrapper.get('.panel.empty').text()).toBe('No telemetry in this range.')
  })

  it('keeps the range picker usable so the reader can look further back', async () => {
    const wrapper = mountHistory(emptyHistory)
    await flushPromises()

    const rangeSelect = wrapper.findAllComponents(AppSelect)[1]!
    expect(rangeSelect.get('.app-select-trigger').attributes('disabled')).toBeUndefined()
    expect(rangeSelect.get('.app-select-trigger').text()).toBe('24 hours')
  })

  it('offers the recorded metrics once there is data', async () => {
    const wrapper = mountHistory(populatedHistory)
    await flushPromises()

    const metricSelect = wrapper.findAllComponents(AppSelect)[0]!
    const trigger = metricSelect.get('.app-select-trigger')
    expect(trigger.attributes('disabled')).toBeUndefined()
    expect(trigger.text()).toContain('battery.soc')

    await trigger.trigger('click')
    const options = metricSelect.findAll('[role="option"]').map((option) => option.text())
    expect(options).toHaveLength(2)
    expect(options.join(' ')).toContain('battery.soc')
    expect(options.join(' ')).toContain('vehicle.speed')
  })
})
