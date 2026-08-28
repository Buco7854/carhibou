import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import { useLiveRefresh } from '../src/api/live'
import TelemetryTable from '../src/components/TelemetryTable.vue'
import DashboardsView from '../src/views/DashboardsView.vue'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import { TestEventSource } from './setup'
import { adminUser, agentIdentity, agentImplementations, jsonResponse, vehicle } from './helpers'

/** Push a vehicle.states frame down the one open stream. */
function emitVehicleState(vehicles: unknown[] = [vehicle]): void {
  const source = TestEventSource.instances.at(-1)!
  source.emit('vehicle.states', JSON.stringify({
    type: 'vehicle.states', version: 1, occurred_at: new Date().toISOString(), vehicles,
  }))
}

function setHidden(hidden: boolean): void {
  Object.defineProperty(document, 'hidden', { configurable: true, value: hidden })
  document.dispatchEvent(new Event('visibilitychange'))
}

function host(refresh: () => unknown, options?: { pollMs?: number }) {
  return mount(defineComponent({
    setup() {
      useLiveRefresh(refresh, options)
      return () => h('div')
    },
  }))
}

describe('useLiveRefresh', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    TestEventSource.instances.length = 0
    setHidden(false)
  })
  afterEach(() => vi.useRealTimers())

  it('refetches on a state event, then throttles a burst into one trailing run', async () => {
    const refresh = vi.fn()
    const wrapper = host(refresh)
    await flushPromises()

    emitVehicleState([{ ...vehicle, name: 'first' }])
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(1)

    // A vehicle uploading continuously emits about once a second. None of these
    // may run on their own; together they owe exactly one trailing refetch.
    for (let tick = 0; tick < 4; tick += 1) {
      vi.advanceTimersByTime(1000)
      emitVehicleState([{ ...vehicle, name: `burst-${tick}` }])
      await flushPromises()
    }
    expect(refresh).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(5000)
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('refetches nothing while the tab is hidden, and settles up on return', async () => {
    const refresh = vi.fn()
    const wrapper = host(refresh)
    await flushPromises()

    setHidden(true)
    emitVehicleState([{ ...vehicle, name: 'unseen' }])
    await flushPromises()
    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(refresh).not.toHaveBeenCalled()

    setHidden(false)
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(1)
    wrapper.unmount()
  })

  it('polls for records the stream says nothing about, on the same throttle', async () => {
    const refresh = vi.fn()
    const wrapper = host(refresh, { pollMs: 10_000 })
    await flushPromises()

    vi.advanceTimersByTime(10_000)
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(1)

    vi.advanceTimersByTime(10_000)
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(2)

    // A hidden tab polls nothing either.
    setHidden(true)
    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(refresh).toHaveBeenCalledTimes(2)
    wrapper.unmount()
  })

  it('stops listening once the page using it is gone', async () => {
    const refresh = vi.fn()
    const wrapper = host(refresh, { pollMs: 1000 })
    await flushPromises()
    wrapper.unmount()

    vi.advanceTimersByTime(60_000)
    await flushPromises()
    expect(refresh).not.toHaveBeenCalled()
  })
})

describe('the telemetry table under new data', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
    setHidden(false)
  })

  function entriesPage(offset: number, total = 120) {
    return {
      vehicle_id: vehicle.id, start: '', end: '', total, limit: 50, offset,
      metric_keys: ['battery.soc'], agent_keys: [],
      entries: [{ id: `e-${offset}`, recorded_at: '2026-08-27T08:00:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 61 }, agent: {} }],
    }
  }

  function mountTable() {
    let offset = 0
    const calls = { count: 0 }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/history/entries')) {
        calls.count += 1
        offset = Number(new URL(url, 'http://x').searchParams.get('offset'))
        return Promise.resolve(jsonResponse(entriesPage(offset)))
      }
      return Promise.resolve(jsonResponse([]))
    }))
    const wrapper = mount(TelemetryTable, {
      props: { vehicleId: vehicle.id, days: 1 },
      global: { plugins: [i18n], stubs: { Teleport: true } },
    })
    return { wrapper, calls }
  }

  it('refetches in place on the first page, where the newest rows already are', async () => {
    const { wrapper, calls } = mountTable()
    await flushPromises()
    const initial = calls.count

    emitVehicleState()
    await flushPromises()
    expect(calls.count).toBe(initial + 1)
    expect(wrapper.find('.entries-fresh').exists()).toBe(false)
    wrapper.unmount()
  })

  it('offers new data instead of yanking the table out from under a reader', async () => {
    const { wrapper, calls } = mountTable()
    await flushPromises()
    await wrapper.findAll('.entries-foot button').find((button) => button.text().includes('Next'))!.trigger('click')
    await flushPromises()
    const afterPaging = calls.count

    emitVehicleState()
    await flushPromises()
    // Nothing refetched: the page the reader is on is left exactly as it was.
    expect(calls.count).toBe(afterPaging)
    const notice = wrapper.get('.entries-fresh')
    expect(notice.text()).toContain('New telemetry has arrived')

    await notice.get('button').trigger('click')
    await flushPromises()
    expect(calls.count).toBe(afterPaging + 1)
    expect(wrapper.find('.entries-fresh').exists()).toBe(false)
    wrapper.unmount()
  })
})

describe('the data sources page', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
    setHidden(false)
  })
  afterEach(() => vi.useRealTimers())

  it('shows an agent enrolled elsewhere without anybody reloading the page', async () => {
    let agents: unknown[] = []
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse(agents))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      return Promise.resolve(jsonResponse([]))
    }))
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Garage agent')

    // The enrollment happened on another device: no event carries it, so the
    // page has to ask again of its own accord.
    agents = [{
      id: 'agent-1', vehicle_id: vehicle.id, name: 'Garage agent', hostname: 'garage-pi',
      hardware: { model: 'pi' }, status: 'online', last_seen_at: new Date().toISOString(),
      created_at: '', updated_at: '', ...agentIdentity,
    }]
    vi.advanceTimersByTime(10_000)
    await flushPromises()
    await flushPromises()
    expect(wrapper.text()).toContain('Garage agent')
  })
})

describe('segment-fed dashboard widgets', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
    setHidden(false)
  })

  it('refetches their own queries on the one throttled signal', async () => {
    const segmentCalls = { count: 0 }
    const dashboard = {
      id: 'd1', name: 'Overview', is_default: true, created_at: '', updated_at: '',
      layout: { preset: 'overview-v7', widgets: [
        { id: 'feed', type: 'activity-feed', x: 0, y: 0, w: 4, h: 3, time_range_days: 7 },
        { id: 'stats', type: 'period-stats', x: 4, y: 0, w: 4, h: 3, time_range_days: 7 },
      ] },
    }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.includes('/segments')) {
        segmentCalls.count += 1
        return Promise.resolve(jsonResponse({ drives: [], charges: [] }))
      }
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      return Promise.resolve(jsonResponse([]))
    }))
    const wrapper = mount(DashboardsView, { global: { plugins: [i18n], stubs: {
      Teleport: true, TimeSeriesChart: { template: '<div data-chart />' }, VehicleMap: { template: '<div data-map />' },
    } } })
    await flushPromises()
    const initial = segmentCalls.count
    expect(initial).toBeGreaterThan(0)

    emitVehicleState([{ ...vehicle, name: 'moved' }])
    await flushPromises()
    // Every segment-fed widget asked again, once, off the same counter.
    expect(segmentCalls.count).toBeGreaterThan(initial)
    wrapper.unmount()
  })
})
