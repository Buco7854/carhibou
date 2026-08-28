import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { DashboardWidget, Vehicle } from '../src/api/types'
import AppSelect from '../src/components/AppSelect.vue'
import { historyValue, metricNumber, reportedChartMetrics, speedReading } from '../src/vehicleDisplay'
import DashboardsView from '../src/views/DashboardsView.vue'
import { STANDARD_METRICS, isGeneralChoice, needsSpecificData, widgetRegistry } from '../src/widgets/registry'
import { adminUser, jsonResponse, vehicle } from './helpers'

function speedy(metrics: Record<string, unknown>, positionSpeed: number | null): Vehicle {
  return {
    ...vehicle,
    state: { ...vehicle.state!, metrics, position: positionSpeed === null ? null : { latitude: 48, longitude: 2, altitude: null, speed: positionSpeed, heading: null, accuracy: null } },
  } as unknown as Vehicle
}

function withMetrics(metrics: Record<string, unknown>, position: unknown = null): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position, metrics } } as unknown as Vehicle
}

const dashboard = {
  id: 'd1', name: 'Overview', is_default: true,
  layout: { preset: 'overview-v8', widgets: [] }, created_at: '', updated_at: '',
}

function mountDashboards(vehicles: Vehicle[]) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
    if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
    if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse(vehicles))
    return Promise.resolve(jsonResponse([]))
  }))
  return mount(DashboardsView, { global: { plugins: [i18n], stubs: {
    Teleport: true, TimeSeriesChart: { template: '<div data-chart />' }, VehicleMap: { template: '<div data-map />' },
  } } })
}

/** The type picker is the first select the add-widget form renders. */
function typePicker(wrapper: ReturnType<typeof mountDashboards>) {
  const picker = wrapper.findAllComponents(AppSelect)[0]!
  expect(wrapper.findAll('.widget-modal-form label span')[0]!.text()).toBe('Type')
  return picker
}

async function openPicker(vehicles: Vehicle[]) {
  const wrapper = mountDashboards(vehicles)
  await flushPromises()
  await wrapper.get('.dashboard-menu-button').trigger('click')
  await wrapper.findAll('[role="menuitem"]').find((button) => button.text().includes('Edit dashboard'))!.trigger('click')
  await wrapper.findAll('.dashboard-editor-bar .button').find((button) => button.text().includes('Add widget'))!.trigger('click')
  await flushPromises()
  return wrapper
}

describe('the general and specific tiers', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('classifies every registered type exactly once', () => {
    for (const definition of Object.values(widgetRegistry)) {
      expect(typeof definition.general, definition.type).toBe('boolean')
      expect(isGeneralChoice(definition.type), definition.type).toBe(definition.general)
    }
  })

  it('groups the picker from that same classification', async () => {
    const wrapper = await openPicker([vehicle as unknown as Vehicle])
    const picker = typePicker(wrapper)
    await picker.get('.app-select-trigger').trigger('click')

    const groups = picker.findAll('[role="group"]')
    expect(groups).toHaveLength(2)
    const membership = Object.fromEntries(groups.map((group) => [
      group.attributes('aria-label'),
      group.findAll('[role="option"]').map((option) => option.text()),
    ]))
    const general = Object.values(widgetRegistry).filter((row) => row.general)
    const specific = Object.values(widgetRegistry).filter((row) => !row.general)
    expect(membership['Suits any vehicle']).toHaveLength(general.length)
    expect(membership['Needs specific data']).toHaveLength(specific.length)
    // The picker offers types and nothing else: no shortcut entry carrying a
    // concept name that the card it inserts would not answer to.
    const offered = [...membership['Suits any vehicle']!, ...membership['Needs specific data']!]
    expect(offered).toHaveLength(Object.keys(widgetRegistry).length)
    expect(offered).not.toContain('Charge curve')
    for (const definition of specific) {
      expect(membership['Needs specific data'], definition.type).toContain(i18n.global.t(definition.titleKey))
    }
    for (const definition of general) {
      expect(membership['Suits any vehicle'], definition.type).toContain(i18n.global.t(definition.titleKey))
    }
  })

  it('defaults hiding on for a data-bound choice and off for a general one', async () => {
    const wrapper = await openPicker([vehicle as unknown as Vehicle])
    const hidden = () => (wrapper.get('.widget-toggle input').element as HTMLInputElement).checked
    // Choosing a type remounts the form's conditional fields, so the picker is
    // looked up again each time rather than held across a render.
    const choose = async (value: string) => {
      typePicker(wrapper).vm.$emit('update:modelValue', value)
      await flushPromises()
    }

    await choose('route-map')
    expect(hidden(), 'route-map').toBe(false)
    await choose('metric-card')
    expect(hidden(), 'metric-card').toBe(true)
    await choose('period-stats')
    expect(hidden(), 'period-stats').toBe(false)
    await choose('xy-chart')
    expect(hidden(), 'xy-chart').toBe(true)

    // Still per-card: the toggle stays visible and the reader can overrule it.
    await wrapper.get('.widget-toggle input').setValue(false)
    expect(hidden()).toBe(false)
  })

  it('follows the chosen metric, not just the chosen type', async () => {
    // The fixture vehicle reports battery state, so a fresh metric card is bound
    // to it and counts as specific.
    const wrapper = await openPicker([vehicle as unknown as Vehicle])
    const hidden = () => (wrapper.get('.widget-toggle input').element as HTMLInputElement).checked
    typePicker(wrapper).vm.$emit('update:modelValue', 'metric-card')
    await flushPromises()
    expect(hidden()).toBe(true)

    // Rebinding the same card to standard data makes it general, with no need to
    // touch the toggle: a speed card belongs on any vehicle's dashboard.
    await wrapper.get('.widget-modal-form input.mono').setValue('vehicle.speed')
    await flushPromises()
    expect(hidden()).toBe(false)
  })
})

describe('generic chart axis defaults', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('lists only reported numeric metrics, dropping booleans', () => {
    const current = withMetrics({ 'battery.soc': 61, 'charging.active': true, 'battery.power': -4 })
    expect(reportedChartMetrics(current)).toEqual(['battery.soc', 'battery.power'])
    expect(reportedChartMetrics(withMetrics({}))).toEqual([])
  })

  it('seeds both axes when two distinct metrics are reported', async () => {
    const wrapper = await openPicker([withMetrics({ 'battery.soc': 61, 'battery.power': -4 })])
    typePicker(wrapper).vm.$emit('update:modelValue', 'xy-chart')
    await flushPromises()

    // Exactly the two axis fields, in the suggestion order, distinct from each other.
    const values = wrapper.findAll('.widget-modal-form input.mono').map((input) => (input.element as HTMLInputElement).value)
    expect(values).toEqual(['battery.soc', 'battery.power'])
  })

  it.each([
    ['one reported metric', { 'battery.soc': 61 }],
    ['no reported metric at all', {}],
  ])('leaves both axes empty with %s rather than guessing', async (_label, metrics) => {
    const wrapper = await openPicker([withMetrics(metrics)])
    const picker = typePicker(wrapper)
    picker.vm.$emit('update:modelValue', 'xy-chart')
    await flushPromises()
    const axes = wrapper.findAll('.widget-modal-form input.mono').map((input) => (input.element as HTMLInputElement).value)
    expect(axes.filter((value) => value !== '')).toEqual([])
  })

  it('never puts the same metric on both axes', async () => {
    for (const metrics of [{ 'battery.soc': 61 }, { 'battery.soc': 61, 'battery.power': -4 }, {}]) {
      const wrapper = await openPicker([withMetrics(metrics)])
      const picker = typePicker(wrapper)
      picker.vm.$emit('update:modelValue', 'xy-chart')
      await flushPromises()
      const axes = wrapper.findAll('.widget-modal-form input.mono').map((input) => (input.element as HTMLInputElement).value)
      const filled = axes.filter(Boolean)
      expect(new Set(filled).size, JSON.stringify(metrics)).toBe(filled.length)
    }
  })
})


describe('speed as standard, source-flexible data', () => {
  it('prefers the measured reading and falls back to the fix', () => {
    expect(speedReading(speedy({ 'vehicle.speed': 54 }, 47))).toBe(54)
    expect(speedReading(speedy({}, 47))).toBe(47)
    expect(speedReading(speedy({ 'vehicle.speed': 54 }, null))).toBe(54)
    expect(speedReading(speedy({}, null))).toBe(null)
    expect(speedReading(null)).toBe(null)
  })

  it('resolves the same way for any caller asking by key', () => {
    expect(metricNumber(speedy({}, 47), 'vehicle.speed')).toBe(47)
    // Only speed is special; every other key still reads the metric map alone.
    expect(metricNumber(speedy({ 'battery.soc': 61 }, 47), 'battery.soc')).toBe(61)
    expect(metricNumber(speedy({}, 47), 'battery.soc')).toBe(null)
  })

  it('resolves a history point across the metric map and the gps column', () => {
    const point = (metrics: Record<string, unknown>, speed: number | null) => ({ speed, metrics })
    expect(historyValue(point({ 'vehicle.speed': 54 }, 47), 'vehicle.speed')).toBe(54)
    expect(historyValue(point({}, 47), 'vehicle.speed')).toBe(47)
    expect(historyValue(point({}, null), 'vehicle.speed')).toBe(null)
    expect(historyValue(point({ 'battery.soc': 61 }, 47), 'battery.soc')).toBe(61)
    expect(historyValue(point({}, 47), 'battery.soc')).toBe(null)
  })
})

describe('needsSpecificData', () => {
  const at = (type: string, extra: Partial<DashboardWidget> = {}): DashboardWidget =>
    ({ id: 'w', type, x: 0, y: 0, w: 4, h: 3, ...extra })

  it('treats a standard binding as general and any other binding as specific', () => {
    expect([...STANDARD_METRICS]).toEqual(['vehicle.speed'])
    expect(needsSpecificData(at('metric-card', { metric: 'vehicle.speed' }))).toBe(false)
    expect(needsSpecificData(at('time-series', { metric: 'vehicle.speed' }))).toBe(false)
    expect(needsSpecificData(at('multi-series', { metrics: ['vehicle.speed'] }))).toBe(false)
    // The guard is not loosened for arbitrary metrics.
    expect(needsSpecificData(at('metric-card', { metric: 'battery.soc' }))).toBe(true)
    expect(needsSpecificData(at('multi-series', { metrics: ['vehicle.speed', 'battery.soc'] }))).toBe(true)
    expect(needsSpecificData(at('xy-chart', { x_metric: 'vehicle.speed', y_metric: 'battery.power' }))).toBe(true)
  })

  it('counts a type bound by its own nature as specific, with or without a metric', () => {
    for (const type of ['battery-gauge', 'charging', 'vehicle-media', 'xy-chart']) {
      expect(needsSpecificData(at(type)), type).toBe(true)
    }
    // An unbound metric card has chosen nothing yet, so it cannot claim standing.
    expect(needsSpecificData(at('metric-card'))).toBe(true)
  })

  it('leaves every general type general however it is configured', () => {
    for (const definition of Object.values(widgetRegistry).filter((row) => row.general)) {
      expect(needsSpecificData(at(definition.type, { metric: 'battery.soc' })), definition.type).toBe(false)
    }
  })
})
