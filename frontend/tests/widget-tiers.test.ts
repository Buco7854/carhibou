import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { Vehicle } from '../src/api/types'
import AppSelect from '../src/components/AppSelect.vue'
import { reportedChartMetrics } from '../src/vehicleDisplay'
import DashboardsView from '../src/views/DashboardsView.vue'
import { isGeneralChoice, widgetPresets, widgetRegistry } from '../src/widgets/registry'
import { adminUser, jsonResponse, vehicle } from './helpers'

function withMetrics(metrics: Record<string, unknown>, position: unknown = null): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position, metrics } } as unknown as Vehicle
}

const dashboard = {
  id: 'd1', name: 'Overview', is_default: true,
  layout: { preset: 'overview-v7', widgets: [] }, created_at: '', updated_at: '',
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

  it('classifies every registered type exactly once, and never a preset as general', () => {
    for (const definition of Object.values(widgetRegistry)) {
      expect(typeof definition.general, definition.type).toBe('boolean')
      expect(isGeneralChoice(definition.type), definition.type).toBe(definition.general)
    }
    for (const preset of widgetPresets) {
      expect(isGeneralChoice(`preset:${preset.id}`), preset.id).toBe(false)
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
    expect(membership['Needs specific data']).toHaveLength(specific.length + widgetPresets.length)
    // The opinionated presets sit with the data-bound cards, under their own names.
    for (const preset of widgetPresets) {
      expect(membership['Needs specific data']).toContain(i18n.global.t(preset.titleKey))
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
    await choose('preset:charge-curve')
    expect(hidden(), 'charge-curve preset').toBe(true)

    // Still per-card: the toggle stays visible and the reader can overrule it.
    await wrapper.get('.widget-toggle input').setValue(false)
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
