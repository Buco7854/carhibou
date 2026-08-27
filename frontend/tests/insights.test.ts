import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { DashboardWidget, SelectedSegment, Vehicle } from '../src/api/types'
import { dashboardRuntimeKey } from '../src/widgets/dashboardContext'
import { widgetRegistry } from '../src/widgets/registry'
import { adminUser, charge, drive, jsonResponse, vehicle } from './helpers'

vi.mock('../src/components/VehicleMap.vue', () => ({
  default: defineComponent({
    props: { position: { type: Object, default: null }, trail: { type: Array, default: () => [] }, marks: { type: Array, default: () => [] } },
    emits: ['pick'],
    setup(props, { emit }) {
      return () => h('div', { class: 'vehicle-map-stub' }, (props.trail as unknown[]).map((_point, index) =>
        h('button', { class: 'trail-point', onClick: () => emit('pick', index) }, String(index))))
    },
  }),
}))

vi.mock('../src/components/TimeSeriesChart.vue', () => ({
  default: defineComponent({
    props: { series: { type: Array, default: () => [] }, xType: { type: String, default: 'time' }, xUnit: { type: String, default: '' } },
    setup(props) {
      return () => h('div', { class: 'chart-stub', 'data-x-type': props.xType, 'data-points': String((props.series as Array<{ data: unknown[] }>)[0]?.data.length ?? 0) })
    },
  }),
}))

const historyPoints = [
  { id: 'p1', recorded_at: '2026-08-27T08:00:00Z', latitude: 48.85, longitude: 2.35, speed: 10, heading: 90, metrics: { 'battery.soc': 82, 'charging.power': 2 } },
  { id: 'p2', recorded_at: '2026-08-27T08:20:00Z', latitude: 48.86, longitude: 2.36, speed: 64, heading: 90, metrics: { 'battery.soc': 77, 'charging.power': 11 } },
  { id: 'p3', recorded_at: '2026-08-27T08:40:00Z', latitude: 48.87, longitude: 2.37, speed: 30, heading: 90, metrics: { 'battery.soc': 71, 'charging.power': 6 } },
]

function mockApi(options: { segments?: unknown; history?: unknown; previous?: unknown } = {}) {
  let segmentCalls = 0
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url.includes('/segments')) {
      segmentCalls += 1
      const body = segmentCalls === 1 || options.previous === undefined ? options.segments ?? { drives: [], charges: [] } : options.previous
      return Promise.resolve(jsonResponse(body))
    }
    if (url.includes('/history')) {
      return Promise.resolve(jsonResponse(options.history ?? { vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 3, points: historyPoints }))
    }
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** Mounts one widget inside a stand-in for the dashboard runtime it injects. */
function mountWidget(type: string, widget: Partial<DashboardWidget> = {}, selected: SelectedSegment | null = null) {
  const selectedSegment = ref<SelectedSegment | null>(selected)
  const selectSegment = vi.fn((next: SelectedSegment | null) => { selectedSegment.value = next })
  const host = defineComponent({
    setup() {
      provide(dashboardRuntimeKey, {
        vehicles: ref<Vehicle[]>([vehicle as unknown as Vehicle]),
        selectedVehicleId: ref(vehicle.id),
        selectedSegment,
        liveStatus: ref('open' as const),
        selectVehicle: vi.fn(),
        selectSegment,
      })
      const definition = widgetRegistry[type]!
      return () => h(definition.component, { widget: { id: 'w1', type, x: 0, y: 0, w: 4, h: 3, ...widget } })
    },
  })
  const wrapper = mount(host, { global: { plugins: [i18n] } })
  return { wrapper, selectSegment, selectedSegment }
}

describe('driving insight widgets', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('registers every insight widget with a configurable range', () => {
    for (const type of ['route-map', 'activity-feed', 'segment-stats', 'charge-curve', 'period-stats']) {
      const definition = widgetRegistry[type]
      expect(definition, type).toBeDefined()
      expect(definition!.configSchema.fields).toContain('time_range_days')
      expect(definition!.needsMetric).toBe(false)
    }
    // Only widgets that can answer from current state offer hiding.
    expect(widgetRegistry['route-map']!.isEmpty).toBeTypeOf('function')
    expect(widgetRegistry['charge-curve']!.isEmpty).toBeTypeOf('function')
  })

  it('shows the activity feed empty, then merged newest first with a type filter', async () => {
    mockApi()
    const empty = mountWidget('activity-feed')
    await flushPromises()
    expect(empty.wrapper.get('.dashboard-widget-empty').text()).toContain('No drives or charges')

    mockApi({ segments: { drives: [drive()], charges: [charge()] } })
    const { wrapper } = mountWidget('activity-feed')
    await flushPromises()
    const rows = wrapper.findAll('.feed-row')
    expect(rows).toHaveLength(2)
    // The charge starts later in the day, so it leads the feed.
    expect(rows[0]!.classes()).toContain('charge')
    expect(rows[0]!.text()).toContain('12.5 kWh added')
    expect(rows[1]!.text()).toContain('24.4 km driven')

    await wrapper.findAll('.feed-filter button')[1]!.trigger('click')
    expect(wrapper.findAll('.feed-row')).toHaveLength(1)
    expect(wrapper.get('.feed-row').classes()).toContain('drive')
  })

  it('publishes the chosen segment from the feed and toggles it off again', async () => {
    mockApi({ segments: { drives: [drive()], charges: [] } })
    const { wrapper, selectSegment } = mountWidget('activity-feed')
    await flushPromises()

    await wrapper.get('.feed-row').trigger('click')
    expect(selectSegment).toHaveBeenCalledWith({ kind: 'drive', start: drive().start, end: drive().end })
    expect(wrapper.get('.feed-row').classes()).toContain('selected')
    await wrapper.get('.feed-row').trigger('click')
    expect(selectSegment).toHaveBeenLastCalledWith(null)
  })

  it('follows the selected segment in segment stats, falling back to the newest', async () => {
    mockApi({ segments: { drives: [drive()], charges: [charge()] } })
    const latest = mountWidget('segment-stats')
    await flushPromises()
    // Nothing selected: the newest segment is the charge.
    expect(latest.wrapper.get('.widget-head small').text()).toContain('Charge')
    expect(latest.wrapper.text()).toContain('12.5 kWh')
    expect(latest.wrapper.text()).toContain('40% → 80%')

    mockApi({ segments: { drives: [drive()], charges: [charge()] } })
    const followed = mountWidget('segment-stats', {}, { kind: 'drive', start: drive().start, end: drive().end })
    await flushPromises()
    expect(followed.wrapper.get('.widget-head small').text()).toContain('Drive')
    expect(followed.wrapper.text()).toContain('24.4 km')
    expect(followed.wrapper.text()).toContain('96 km/h')
  })

  it('omits segment stats the server could not derive', async () => {
    mockApi({ segments: { drives: [drive({ distance_km: undefined, energy_kwh: undefined, max_speed: undefined })], charges: [] } })
    const { wrapper } = mountWidget('segment-stats')
    await flushPromises()
    const labels = wrapper.findAll('.stat-grid dt').map((row) => row.text())
    expect(labels).toContain('Duration')
    expect(labels).not.toContain('Distance')
    expect(labels).not.toContain('Top speed')
  })

  it('plots the charge curve against state of charge', async () => {
    mockApi({ segments: { drives: [], charges: [charge()] } })
    const { wrapper } = mountWidget('charge-curve')
    await flushPromises()
    const chart = wrapper.get('.chart-stub')
    expect(chart.attributes('data-x-type')).toBe('value')
    expect(chart.attributes('data-points')).toBe('3')
    expect(wrapper.get('.widget-head small').text()).toContain('Peak 11.2 kW')
  })

  it('leaves the charge curve empty when the range holds no charge', async () => {
    mockApi({ segments: { drives: [drive()], charges: [] } })
    const { wrapper } = mountWidget('charge-curve')
    await flushPromises()
    expect(wrapper.find('.chart-stub').exists()).toBe(false)
    expect(wrapper.get('.dashboard-widget-empty').text()).toContain('No charge to plot')
  })

  it('reads two picked points on the route trail as an A to B leg', async () => {
    mockApi({ segments: { drives: [drive()], charges: [] } })
    const { wrapper } = mountWidget('route-map', { time_range_days: 1 })
    await flushPromises()
    expect(wrapper.find('.route-readout').exists()).toBe(false)

    const points = wrapper.findAll('.trail-point')
    expect(points).toHaveLength(3)
    await points[0]!.trigger('click')
    expect(wrapper.find('.route-readout').exists()).toBe(false)
    await points[2]!.trigger('click')

    const readout = wrapper.get('.route-readout')
    expect(readout.text()).toContain('Distance')
    expect(readout.text()).toContain('Duration')
    // 82% to 71% over a 16 kWh pack is 1.8 kWh.
    expect(readout.text()).toContain('11%')
    expect(readout.text()).toContain('1.8 kWh')
  })

  it('totals a period and compares it with the one before', async () => {
    mockApi({
      segments: { drives: [drive(), drive({ start: '2026-08-26T08:00:00Z', distance_km: 15.6, energy_kwh: 3.4 })], charges: [charge()] },
      previous: { drives: [drive({ distance_km: 20 })], charges: [charge({ energy_kwh: 10 })] },
    })
    const { wrapper } = mountWidget('period-stats', { time_range_days: 7 })
    await flushPromises()

    const stats = Object.fromEntries(wrapper.findAll('.stat-grid > div').map((row) => [row.get('dt').text(), row.get('dd').text()]))
    expect(stats.Distance).toContain('40 km')
    expect(stats.Drives).toContain('2')
    expect(stats['Energy charged']).toContain('12.5 kWh')
    // 40 km against 20 km in the period before.
    expect(stats.Distance).toContain('+100%')
  })

  it.each([
    ['a body with neither list', {}],
    ['an array body', []],
    ['a null body', null],
    ['a vehicle-shaped body', vehicle],
    ['lists that are not arrays', { drives: null, charges: 'none' }],
    ['rows without an instant', { drives: [{ distance_km: 4 }], charges: [{}] }],
  ])('renders without throwing when segments come back as %s', async (_label, body) => {
    mockApi({ segments: body, previous: body })
    for (const type of ['activity-feed', 'segment-stats', 'charge-curve', 'period-stats']) {
      const { wrapper } = mountWidget(type)
      await flushPromises()
      expect(wrapper.find('.widget-card').exists(), type).toBe(true)
      expect(wrapper.find('.dashboard-widget-empty').exists(), type).toBe(true)
      wrapper.unmount()
    }
    // The route map has no segment to follow, so it falls back to the whole range.
    mockApi({ segments: body, previous: body })
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    expect(wrapper.find('.route-map .map-stage').exists()).toBe(true)
    expect(wrapper.findAll('.trail-point')).toHaveLength(3)
  })

  it('degrades to the empty state when the segments request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => url.includes('/segments')
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(jsonResponse({ vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 0, points: [] }))))
    for (const type of ['activity-feed', 'segment-stats', 'charge-curve', 'route-map', 'period-stats']) {
      const { wrapper } = mountWidget(type)
      await flushPromises()
      expect(wrapper.find('.dashboard-widget-empty').exists(), type).toBe(true)
      wrapper.unmount()
    }
  })

  it('shows nothing for a period with no activity', async () => {
    mockApi({ segments: { drives: [], charges: [] }, previous: { drives: [], charges: [] } })
    const { wrapper } = mountWidget('period-stats')
    await flushPromises()
    expect(wrapper.get('.dashboard-widget-empty').text()).toContain('Nothing recorded')
  })
})
