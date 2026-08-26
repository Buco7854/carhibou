import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppSelect from '../src/components/AppSelect.vue'
import i18n from '../src/i18n'
import TelemetryTable from '../src/components/TelemetryTable.vue'
import { jsonResponse } from './helpers'

const entries = [
  {
    id: 'e2', recorded_at: '2026-01-01T10:01:00Z', sequence: 2,
    latitude: 48.1, longitude: 2.1, altitude: 90, speed: 41, heading: 12, accuracy: 4,
    metrics: { 'battery.soc': 60, 'custom.oil_pressure': 3.4 }, device: { mobile_signal: -70 },
  },
  {
    id: 'e1', recorded_at: '2026-01-01T10:00:00Z', sequence: 1,
    latitude: 48.0, longitude: 2.0, altitude: 88, speed: 0, heading: null, accuracy: 5,
    metrics: { 'battery.soc': 90 }, device: { mobile_signal: -72 },
  },
]

function mountTable() {
  return mount(TelemetryTable, {
    props: { vehicleId: 'vehicle-1', days: 1 },
    global: { plugins: [i18n], stubs: { Teleport: true } },
  })
}

function lastRequest(fetchMock: ReturnType<typeof vi.fn>): URLSearchParams {
  return new URL(String(fetchMock.mock.calls.at(-1)?.[0]), 'http://localhost').searchParams
}

describe('telemetry table', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'en'
  })

  it('requests the latest entries first and builds a column per reported signal', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc', 'custom.oil_pressure'], device_keys: ['mobile_signal'], entries,
    })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountTable()
    await flushPromises()

    const params = lastRequest(fetchMock)
    expect(params.get('sort')).toBe('recorded_at')
    expect(params.get('direction')).toBe('desc')

    const headers = wrapper.findAll('thead th').map((cell) => cell.text())
    // A profile-only signal with no built-in label keeps its raw metric key.
    expect(headers.some((text) => text.includes('custom.oil_pressure'))).toBe(true)
    expect(headers.some((text) => text.includes('Battery level'))).toBe(true)
    expect(headers.some((text) => text.includes('Mobile signal'))).toBe(true)
    // A row missing that signal shows a dash rather than dropping out.
    expect(wrapper.findAll('tbody tr')[1]!.text()).toContain('—')
  })

  it('sorts on a metric column and sends a numeric range filter', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc'], device_keys: [], entries,
    })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountTable()
    await flushPromises()

    const header = wrapper.findAll('thead th button').find((button) => button.text().includes('Battery level'))!
    await header.trigger('click')
    await flushPromises()
    expect(lastRequest(fetchMock).get('sort')).toBe('metric:battery.soc')
    expect(lastRequest(fetchMock).get('direction')).toBe('asc')
    await header.trigger('click')
    await flushPromises()
    expect(lastRequest(fetchMock).get('direction')).toBe('desc')

    await wrapper.find('.filter-actions button').trigger('click')
    await flushPromises()
    wrapper.findAllComponents(AppSelect)[0]!.vm.$emit('update:modelValue', 'metric:battery.soc')
    await flushPromises()
    await wrapper.find('.entries-filter input[type="number"]').setValue('80')
    await flushPromises()
    expect(lastRequest(fetchMock).getAll('filter')).toEqual(['metric:battery.soc|80||'])
  })

  it('combines several filters in one request', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc'], device_keys: [], entries,
    })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountTable()
    await flushPromises()

    // A filter that narrows nothing yet is not sent, so each one only appears
    // once it carries a bound.
    await wrapper.find('.filter-actions button').trigger('click')
    await flushPromises()
    expect(lastRequest(fetchMock).getAll('filter')).toEqual([])

    await wrapper.findAll('.entries-filter input[type="number"]')[0]!.setValue('10')
    await flushPromises()
    await wrapper.find('.filter-actions button').trigger('click')
    await flushPromises()
    wrapper.findAllComponents(AppSelect)[1]!.vm.$emit('update:modelValue', 'metric:battery.soc')
    await flushPromises()
    await wrapper.findAll('.entries-filter input[type="number"]')[3]!.setValue('80')
    await flushPromises()

    expect(lastRequest(fetchMock).getAll('filter')).toEqual(['speed|10||', 'metric:battery.soc||80|'])

    // Removing one leaves the other in place.
    await wrapper.findAll('.remove-filter')[0]!.trigger('click')
    await flushPromises()
    expect(lastRequest(fetchMock).getAll('filter')).toEqual(['metric:battery.soc||80|'])
  })

  it('closes the column menu when the page is clicked elsewhere', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: [], device_keys: [], entries,
    }))))
    const wrapper = mount(TelemetryTable, {
      props: { vehicleId: 'vehicle-1', days: 1 },
      global: { plugins: [i18n], stubs: { Teleport: true } },
      attachTo: document.body,
    })
    await flushPromises()

    await wrapper.find('.entries-tools button').trigger('click')
    expect(wrapper.find('.columns-menu').exists()).toBe(true)

    // Clicking inside the menu keeps it open; only a click outside dismisses it.
    document.querySelector('.columns-menu')!.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('.columns-menu').exists()).toBe(true)

    document.body.dispatchEvent(new Event('pointerdown', { bubbles: true }))
    await flushPromises()
    expect(wrapper.find('.columns-menu').exists()).toBe(false)
    wrapper.unmount()
  })

  it('remembers hidden and reordered columns per vehicle', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc'], device_keys: [], entries,
    }))))
    const wrapper = mountTable()
    await flushPromises()
    await wrapper.find('.entries-tools button').trigger('click')

    const row = wrapper.findAll('.columns-menu li').find((item) => item.text().includes('Longitude'))!
    await row.find('input').setValue(false)
    await flushPromises()
    expect(wrapper.findAll('thead th').some((cell) => cell.text().includes('Longitude'))).toBe(false)

    const accuracy = wrapper.findAll('.columns-menu li').find((item) => item.text().includes('Accuracy'))!
    await accuracy.findAll('button')[0]!.trigger('click')
    await flushPromises()

    const stored = JSON.parse(localStorage.getItem('vehinode.history-columns.vehicle-1') ?? '{}')
    expect(stored.hidden).toContain('longitude')
    expect(stored.order.indexOf('accuracy')).toBeLessThan(stored.order.indexOf('heading'))

    // A different vehicle starts from the default column set.
    await wrapper.setProps({ vehicleId: 'vehicle-2' })
    await flushPromises()
    expect(wrapper.findAll('thead th').some((cell) => cell.text().includes('Longitude'))).toBe(true)
  })
})
