import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppSelect from '../src/components/AppSelect.vue'
import i18n from '../src/i18n'
import TelemetryTable from '../src/components/TelemetryTable.vue'
import { resetMetricKeys } from '../src/metricRegistry'
import { jsonResponse } from './helpers'

const entries = [
  {
    id: 'e2', recorded_at: '2026-01-01T10:01:00Z', sequence: 2,
    latitude: 48.1, longitude: 2.1, altitude: 90, speed: 41, heading: 12, accuracy: 4,
    metrics: { 'battery.soc': 60, 'custom.oil_pressure': 3.4 }, agent: { mobile_signal: -70 },
  },
  {
    id: 'e1', recorded_at: '2026-01-01T10:00:00Z', sequence: 1,
    latitude: 48.0, longitude: 2.0, altitude: 88, speed: 0, heading: null, accuracy: 5,
    metrics: { 'battery.soc': 90 }, agent: { mobile_signal: -72 },
  },
]

function mountTable() {
  return mount(TelemetryTable, {
    props: { vehicleId: 'vehicle-1', days: 1 },
    global: { plugins: [i18n], stubs: { Teleport: true } },
  })
}

/** The table also asks for the metric registry, which carries no query at all. */
function lastRequest(fetchMock: ReturnType<typeof vi.fn>): URLSearchParams {
  const url = fetchMock.mock.calls.map((call) => String(call[0])).filter((path) => path.includes('/entries')).at(-1)
  return new URL(String(url), 'http://localhost').searchParams
}

describe('telemetry table', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'en'
  })

  it('requests the latest entries first and builds a column per reported signal', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc', 'custom.oil_pressure'], agent_keys: ['mobile_signal'], entries,
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
    // The agent's own readings are not readings from the car, and there are
    // enough of them to bury the ones that are, so they start hidden.
    expect(headers.some((text) => text.includes('Mobile signal'))).toBe(false)
    const offered = wrapper.findAll('.columns-menu li').map((item) => item.text())
    expect(offered.length === 0 || offered.some((text) => text.includes('Mobile signal'))).toBe(true)
    // A row missing that signal shows a dash rather than dropping out.
    expect(wrapper.findAll('tbody tr')[1]!.text()).toContain('—')
  })

  it('sorts on a metric column and sends a numeric range filter', async () => {
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc'], agent_keys: [], entries,
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
      metric_keys: ['battery.soc'], agent_keys: [], entries,
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

  it('keeps the canonical name reachable behind the friendly label', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: ['battery.soc', 'battery.current'], agent_keys: ['mobile_signal'], entries,
    }))))
    const wrapper = mountTable()
    await flushPromises()

    // A profile, a hook and a filter are all written against the canonical name,
    // so a label that replaced it entirely would hide what the column is.
    const header = wrapper.findAll('thead th button').find((button) => button.text().includes('Battery level'))!
    expect(header.attributes('title')).toContain('battery.soc')

    // Where a note exists it explains something the label cannot. "Pack current"
    // cannot say which way round the sign runs; the note has to.
    const current = wrapper.findAll('thead th button').find((button) => button.text().includes('Pack current'))!
    expect(current.attributes('title')).toContain('battery.current')
    expect(current.attributes('title')).toContain('charging')

    // An agent column is hidden by default, so its name is reached through the
    // column menu rather than through a header that is not there.
    await wrapper.get('.entries-tools button').trigger('click')
    const agentColumn = wrapper.findAll('.columns-menu label').find((item) => item.text().includes('Mobile signal'))!
    expect(agentColumn.attributes('title')).toContain('mobile_signal')
  })

  it('takes a metric note from the server, and lets a locale sharpen it', async () => {
    resetMetricKeys()
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/metrics/registry')) return Promise.resolve(jsonResponse({ metrics: [
        { key:'battery.soc', unit:'%', meaning:'traction-battery state of charge from zero to one hundred', kind:'state', value_type:'number', retained:true, freshness_seconds:900 },
        { key:'vehicle.range', unit:'km', meaning:'estimated remaining vehicle range', kind:'state', value_type:'number', retained:true, freshness_seconds:900 },
      ] }))
      return Promise.resolve(jsonResponse({
        vehicle_id:'vehicle-1', start:'', end:'', total:2, limit:50, offset:0,
        metric_keys:['battery.soc', 'vehicle.range'], agent_keys:['queue_depth'], entries,
      }))
    }))
    const wrapper = mountTable()
    await flushPromises()
    // Found by canonical name rather than by label, because the point of the
    // title is that the canonical name stays reachable.
    const titleFor = (key: string) => wrapper.findAll('thead th button')
      .map((button) => button.attributes('title') ?? '')
      .find((title) => title.startsWith(key)) ?? ''

    // battery.soc has a note of its own, which is a sharper sentence than the
    // registry's wording, so the note wins.
    expect(titleFor('battery.soc')).toContain('Charge remaining in the traction battery.')
    // vehicle.range has none, so rather than showing the bare key the column
    // says what the server says it means.
    expect(titleFor('vehicle.range')).toContain('estimated remaining vehicle range')

    // An agent key is not a registry metric and keeps its own note.
    await wrapper.get('.entries-tools button').trigger('click')
    const queue = wrapper.findAll('.columns-menu label').find((item) => item.text().includes('Queue'))
    expect(queue?.attributes('title')).toContain('still holding until Carhibou confirms')
  })

  it('closes the column menu when the page is clicked elsewhere', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse({
      vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0,
      metric_keys: [], agent_keys: [], entries,
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
      metric_keys: ['battery.soc'], agent_keys: [], entries,
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

    const stored = JSON.parse(localStorage.getItem('carhibou.history-columns.vehicle-1') ?? '{}')
    expect(stored.hidden).toContain('longitude')
    expect(stored.order.indexOf('accuracy')).toBeLessThan(stored.order.indexOf('heading'))

    // A different vehicle starts from the default column set.
    await wrapper.setProps({ vehicleId: 'vehicle-2' })
    await flushPromises()
    expect(wrapper.findAll('thead th').some((cell) => cell.text().includes('Longitude'))).toBe(true)
  })

  it('shows where one row\u2019s values came from, without giving up the grid', async () => {
    // /entries is the only endpoint that sorts and filters, and it carries no
    // provenance, so provenance is fetched per row rather than by swapping the
    // grid onto /observations and losing both.
    const sample = {
      id: 'e2', sequence: 2, recorded_at: '2026-01-01T10:01:00Z', received_at: '2026-01-01T10:01:20Z',
      source_id: 'agent-1', source_kind: 'agent', reporting_interval: 5, event_driven: false,
      position: {
        value: { latitude: 48.1, longitude: 2.1, altitude: 90, speed: 41, heading: 12, accuracy: 4 },
        observed_at: '2026-01-01T10:00:55Z', source_id: 'agent-1', source_kind: 'agent',
        channel: 'gnss', method: 'direct',
      },
      observations: [
        { key: 'battery.soc', value: 60, observed_at: '2026-01-01T10:01:00Z', source_id: 'agent-1', source_kind: 'agent', channel: 'can', method: 'direct' },
        { key: 'engine.rpm', value: 1400, observed_at: '2026-01-01T10:01:00Z', source_id: 'agent-1', source_kind: 'agent', channel: 'obd', method: 'direct' },
      ],
      agent: {},
    }
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(String(url).includes('/observations')
        ? { vehicle_id: 'vehicle-1', start: '', end: '', total: 1, limit: 500, offset: 0, samples: [sample] }
        : { vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0, metric_keys: [], agent_keys: [], entries })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountTable()
    await flushPromises()

    await wrapper.findAll('tbody .expand-cell button')[0]!.trigger('click')
    await flushPromises()
    const detail = wrapper.get('.provenance')
    // Which source, and the two instants that are not the same fact.
    expect(detail.text()).toContain('agent-1')
    expect(detail.text()).toContain('Received')
    // One sample can carry several channels; that is the whole point of showing it.
    expect(detail.text()).toContain('CAN')
    expect(detail.text()).toContain('OBD-II')
    expect(detail.text()).toContain('GNSS')
    // The grid keeps its own request; provenance is a second, narrower one.
    const observationCall = fetchMock.mock.calls.map((call) => String(call[0])).find((url) => url.includes('/observations'))!
    expect(observationCall).toContain('limit=500')
    expect(new URL(observationCall, 'http://localhost').searchParams.get('start')).toBe('2026-01-01T10:01:00.000Z')
  })

  it('closes the detail again without refetching the grid', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(String(url).includes('/observations')
        ? { vehicle_id: 'vehicle-1', start: '', end: '', total: 0, limit: 500, offset: 0, samples: [] }
        : { vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0, metric_keys: [], agent_keys: [], entries })))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mountTable()
    await flushPromises()
    const toggle = wrapper.findAll('tbody .expand-cell button')[0]!
    await toggle.trigger('click')
    await flushPromises()
    // No sample came back for that second, which is said rather than left blank.
    expect(wrapper.text()).toContain('Nothing was recorded about where this reading came from')
    await toggle.trigger('click')
    await flushPromises()
    expect(wrapper.find('.provenance-row').exists()).toBe(false)
  })

  it('draws the column picker outside the panel that would clip it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() =>
      Promise.resolve(jsonResponse({ vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0, metric_keys: [], agent_keys: [], entries }))))
    const wrapper = mountTable()
    await flushPromises()

    await wrapper.get('.entries-tools button').trigger('click')
    const menu = wrapper.get('.columns-menu')
    // Fixed rather than absolute: the entries panel hides its own overflow to
    // keep the table's corners, which cut an absolutely positioned menu off.
    expect(menu.attributes('style')).toContain('top')
    expect(getComputedStyle(menu.element).position).not.toBe('absolute')
  })

  it('never dates a carried value from anything but the instant it shows', async () => {
    // The bug: a fix taken seconds before the upload that carried it was labelled
    // with that gap as though it were an age, while sitting minutes in the past.
    const observed = '2026-01-01T10:00:46Z'
    const sample = {
      id: 'e2', sequence: 2, recorded_at: '2026-01-01T10:01:00Z', received_at: '2026-01-01T10:05:00Z',
      source_id: 'agent-1', source_kind: 'agent', reporting_interval: 5, event_driven: false,
      position: {
        value: { latitude: 48.1, longitude: 2.1, altitude: 90, speed: 41, heading: 12, accuracy: 4 },
        observed_at: observed, source_id: 'agent-1', source_kind: 'agent', channel: 'gnss', method: 'direct',
      },
      observations: [],
      agent: {},
    }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(String(url).includes('/observations')
        ? { vehicle_id: 'vehicle-1', start: '', end: '', total: 1, limit: 500, offset: 0, samples: [sample] }
        : { vehicle_id: 'vehicle-1', start: '', end: '', total: 2, limit: 50, offset: 0, metric_keys: [], agent_keys: [], entries }))))
    const wrapper = mountTable()
    await flushPromises()
    await wrapper.findAll('tbody .expand-cell button')[0]!.trigger('click')
    await flushPromises()

    const positionRow = wrapper.get('.provenance-table tbody tr')
    // The gap between the fix and its report is fourteen seconds, and it is named
    // as a gap rather than dressed up as a distance from now.
    expect(positionRow.text()).toContain('14 seconds before the report')
    expect(positionRow.text()).not.toContain('ago')
    // Observed and received are four minutes apart and both said plainly.
    expect(wrapper.get('.provenance-facts').text()).toContain('4 minutes in flight')
  })
})
