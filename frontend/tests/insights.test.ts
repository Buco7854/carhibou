import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { DashboardWidget, SelectedSegment, Vehicle } from '../src/api/types'
import { dashboardRuntimeKey } from '../src/widgets/dashboardContext'
import { widgetRegistry } from '../src/widgets/registry'
import { adminUser, charge, drive, jsonResponse, mockApi, vehicle } from './helpers'

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

function api(options: { segments?: unknown; history?: unknown; previous?: unknown } = {}) {
  let segmentCalls = 0
  return mockApi({
    '/segments': () => {
      segmentCalls += 1
      return segmentCalls === 1 || options.previous === undefined ? options.segments ?? { drives: [], charges: [] } : options.previous
    },
    '/history': options.history ?? { vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 3, points: historyPoints },
    default: [],
  })
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
    for (const type of ['route-map', 'activity-feed', 'segment-stats', 'xy-chart', 'period-stats']) {
      const definition = widgetRegistry[type]
      expect(definition, type).toBeDefined()
      expect(definition!.configSchema.fields).toContain('time_range_days')
      expect(definition!.needsMetric).toBe(false)
    }
    // Only widgets that can answer from current state offer hiding.
    expect(widgetRegistry['route-map']!.isEmpty).toBeTypeOf('function')
    expect(widgetRegistry['xy-chart']!.isEmpty).toBeTypeOf('function')
  })

  it('shows the activity feed empty, then merged newest first with a type filter', async () => {
    api()
    const empty = mountWidget('activity-feed')
    await flushPromises()
    expect(empty.wrapper.get('.dashboard-widget-empty').text()).toContain('No drives or charges')

    api({ segments: { drives: [drive()], charges: [charge()] } })
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
    api({ segments: { drives: [drive()], charges: [] } })
    const { wrapper, selectSegment } = mountWidget('activity-feed')
    await flushPromises()

    await wrapper.get('.feed-row').trigger('click')
    expect(selectSegment).toHaveBeenCalledWith({ kind: 'drive', start: drive().start, end: drive().end })
    expect(wrapper.get('.feed-row').classes()).toContain('selected')
    await wrapper.get('.feed-row').trigger('click')
    expect(selectSegment).toHaveBeenLastCalledWith(null)
  })

  it('follows the selected segment in segment stats, falling back to the newest', async () => {
    api({ segments: { drives: [drive()], charges: [charge()] } })
    const latest = mountWidget('segment-stats')
    await flushPromises()
    // Nothing selected: the newest segment is the charge.
    expect(latest.wrapper.get('.widget-head small').text()).toContain('Charge')
    expect(latest.wrapper.text()).toContain('12.5 kWh')
    expect(latest.wrapper.text()).toContain('40% → 80%')

    api({ segments: { drives: [drive()], charges: [charge()] } })
    const followed = mountWidget('segment-stats', {}, { kind: 'drive', start: drive().start, end: drive().end })
    await flushPromises()
    expect(followed.wrapper.get('.widget-head small').text()).toContain('Drive')
    expect(followed.wrapper.text()).toContain('24.4 km')
    expect(followed.wrapper.text()).toContain('96 km/h')
  })

  it('omits segment stats the server could not derive', async () => {
    api({ segments: { drives: [drive({ distance_km: undefined, energy_kwh: undefined, max_speed: undefined })], charges: [] } })
    const { wrapper } = mountWidget('segment-stats')
    await flushPromises()
    const labels = wrapper.findAll('.stat-grid dt').map((row) => row.text())
    expect(labels).toContain('Duration')
    expect(labels).not.toContain('Distance')
    expect(labels).not.toContain('Top speed')
  })

  it('plots the y metric against the x metric', async () => {
    api({ segments: { drives: [], charges: [charge()] } })
    const { wrapper } = mountWidget('xy-chart')
    await flushPromises()
    const chart = wrapper.get('.chart-stub')
    expect(chart.attributes('data-x-type')).toBe('value')
    expect(chart.attributes('data-points')).toBe('3')
    // Derived from the plotted series, since a generic Y has no server figure.
    expect(wrapper.get('.widget-head small').text()).toContain('Peak 11.0 kW')
  })

  it('leaves the chart empty when one of the two metrics never reports', async () => {
    const noPower = {
      vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 1,
      points: [{ id: 'a', recorded_at: '2026-08-27T08:00:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 40 } }],
    }
    api({ segments: { drives: [drive()], charges: [] }, history: noPower })
    const { wrapper } = mountWidget('xy-chart')
    await flushPromises()
    expect(wrapper.find('.chart-stub').exists()).toBe(false)
    expect(wrapper.get('.dashboard-widget-empty').text()).toContain('No paired readings')
  })

  it('reads two picked points on the route trail as an A to B leg', async () => {
    api({ segments: { drives: [drive()], charges: [] } })
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
    api({
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
    api({ segments: body, previous: body })
    for (const type of ['activity-feed', 'segment-stats', 'period-stats']) {
      const { wrapper } = mountWidget(type)
      await flushPromises()
      expect(wrapper.find('.widget-card').exists(), type).toBe(true)
      expect(wrapper.find('.dashboard-widget-empty').exists(), type).toBe(true)
      wrapper.unmount()
    }
    // Route map and x-y chart have no segment to follow, so both plot the range.
    api({ segments: body, previous: body })
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    expect(wrapper.find('.route-map-widget .map-stage').exists()).toBe(true)
    expect(wrapper.findAll('.trail-point')).toHaveLength(3)

    api({ segments: body, previous: body })
    const chart = mountWidget('xy-chart')
    await flushPromises()
    expect(chart.wrapper.find('.chart-stub').exists()).toBe(true)
  })

  it.each(['route-map', 'segment-stats', 'xy-chart'])(
    'says so in %s when the selection is outside its own range',
    async (type) => {
      // A selection the range cannot show is stated, not quietly swapped for another.
      api({ segments: { drives: [drive()], charges: [charge()] } })
      const { wrapper } = mountWidget(type, {}, { kind: 'drive', start: '2020-01-01T00:00:00Z', end: '2020-01-01T01:00:00Z' })
      await flushPromises()
      expect(wrapper.get('.dashboard-widget-empty').text()).toContain('outside this range')
      expect(wrapper.find('.route-map-widget .map-stage').exists()).toBe(false)
    },
  )

  it('shares the default range across the feed and its followers', () => {
    for (const type of ['route-map', 'activity-feed', 'segment-stats', 'xy-chart']) {
      expect(widgetRegistry[type]!.configSchema.fields, type).toContain('time_range_days')
    }
  })

  it('pairs a sparse series by carrying each reading forward', async () => {
    // A connector reports one key per message, so no single point carries both.
    const sparse = {
      vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 4,
      points: [
        { id: 'a', recorded_at: '2026-08-27T19:00:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 40 } },
        { id: 'b', recorded_at: '2026-08-27T19:10:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'charging.power': 11 } },
        { id: 'c', recorded_at: '2026-08-27T19:40:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 60 } },
        { id: 'd', recorded_at: '2026-08-27T20:10:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'charging.power': 7 } },
      ],
    }
    api({ segments: { drives: [], charges: [charge()] }, history: sparse })
    const { wrapper } = mountWidget('xy-chart')
    await flushPromises()
    expect(wrapper.get('.chart-stub').attributes('data-points')).toBe('3')
  })

  it('scales the A to B distance to the drive the server measured', async () => {
    api({ segments: { drives: [drive()], charges: [] } })
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    const points = wrapper.findAll('.trail-point')
    await points[0]!.trigger('click')
    await points[2]!.trigger('click')
    // The trail is downsampled, so the raw haversine is scaled onto the drive's 24.4 km.
    expect(wrapper.get('.route-readout').text()).toContain('24.4 km')
    expect(wrapper.get('.route-readout').text()).toContain('Distance')
    expect(wrapper.get('.route-readout').text()).not.toContain('estimated')
  })

  it('labels the readout an estimate with no drive to scale against', async () => {
    api({ segments: { drives: [], charges: [] } })
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    const points = wrapper.findAll('.trail-point')
    await points[0]!.trigger('click')
    await points[2]!.trigger('click')
    expect(wrapper.get('.route-readout').text()).toContain('estimated')
  })

  it('keeps ranged widgets visible for a vehicle with no live reading', () => {
    const parked = { ...vehicle, state: { ...vehicle.state, position: null, metrics: {} } } as unknown as Vehicle
    for (const type of ['route-map', 'xy-chart']) {
      expect(widgetRegistry[type]!.isEmpty?.({ id: 'w', type, x: 0, y: 0, w: 4, h: 3 }, parked), type).toBe(false)
    }
  })

  it('carries an x metric and a y metric through to the chart', async () => {
    const sparse = {
      vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 4,
      points: [
        { id: 'a', recorded_at: '2026-08-27T08:00:00Z', latitude: null, longitude: null, speed: 10, heading: null, metrics: {} },
        { id: 'b', recorded_at: '2026-08-27T08:05:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.power': -4 } },
        { id: 'c', recorded_at: '2026-08-27T08:10:00Z', latitude: null, longitude: null, speed: 40, heading: null, metrics: {} },
        { id: 'd', recorded_at: '2026-08-27T08:15:00Z', latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.power': -18 } },
      ],
    }
    api({ segments: { drives: [], charges: [] }, history: sparse })
    const { wrapper } = mountWidget('xy-chart', { x_metric: 'vehicle.speed', y_metric: 'battery.power' })
    await flushPromises()
    // Forward fill pairs b, c and d; a has no y yet.
    expect(wrapper.get('.chart-stub').attributes('data-points')).toBe('3')
    expect(wrapper.get('.chart-stub').attributes('data-x-type')).toBe('value')
  })

  it('says so when the selected segment is outside an x-y chart range', async () => {
    api({ segments: { drives: [drive()], charges: [charge()] } })
    const { wrapper } = mountWidget('xy-chart', {}, { kind: 'drive', start: '2020-01-01T00:00:00Z', end: '2020-01-01T01:00:00Z' })
    await flushPromises()
    expect(wrapper.get('.dashboard-widget-empty').text()).toContain('outside this range')
    expect(wrapper.find('.chart-stub').exists()).toBe(false)
  })

  it('degrades to the empty state when the segments request fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => url.includes('/segments')
      ? Promise.reject(new Error('offline'))
      : Promise.resolve(jsonResponse({ vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 0, points: [] }))))
    for (const type of ['activity-feed', 'segment-stats', 'xy-chart', 'period-stats']) {
      const { wrapper } = mountWidget(type)
      await flushPromises()
      expect(wrapper.find('.dashboard-widget-empty').exists(), type).toBe(true)
      wrapper.unmount()
    }
    // The route map replaced position-map on the Overview, so a known position
    // still draws even when no route or segment can be had.
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    expect(wrapper.find('.dashboard-widget-empty').exists()).toBe(false)
    expect(wrapper.find('.vehicle-map-stub').exists()).toBe(true)
    expect(wrapper.findAll('.trail-point')).toHaveLength(0)
  })

  it('shows nothing for a period with no activity', async () => {
    api({ segments: { drives: [], charges: [] }, previous: { drives: [], charges: [] } })
    const { wrapper } = mountWidget('period-stats')
    await flushPromises()
    expect(wrapper.get('.dashboard-widget-empty').text()).toContain('Nothing recorded')
  })
})
