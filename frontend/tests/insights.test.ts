import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, provide, ref } from 'vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import type { DashboardWidget, SelectedSegment, Vehicle } from '../src/api/types'
import { dashboardRuntimeKey } from '../src/widgets/dashboardContext'
import { widgetRegistry } from '../src/widgets/registry'
import { unreportedSpan } from '../src/widgets/segments'
import { adminUser, charge, drive, jsonResponse, mockApi, readings, vehicle } from './helpers'

/*
 * The map, as far as a widget test is concerned: the trail as clickable points,
 * and the context a host renders inside the frame. The context slot is not
 * decoration — it is where a host's own readout lives, so that it travels with
 * the frame when the map is expanded, and a stub without it would test a
 * component that no longer exists.
 */
vi.mock('../src/components/VehicleMap.vue', () => ({
  default: defineComponent({
    props: { position: { type: Object, default: null }, trail: { type: Array, default: () => [] }, marks: { type: Array, default: () => [] }, heading: { type: String, default: '' } },
    emits: ['pick'],
    setup(props, { emit, slots }) {
      return () => h('div', { class: 'vehicle-map-stub' }, [
        ...(props.trail as unknown[]).map((_point, index) =>
          h('button', { class: 'trail-point', onClick: () => emit('pick', index) }, String(index))),
        h('div', { class: 'map-context-stub' }, slots.context?.()),
      ])
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
        liveStatus: ref('open' as const), dataVersion: ref(0),
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
    const labels = wrapper.findAll('.segment-facts dt').map((row) => row.text())
    expect(labels).toContain('Duration')
    expect(labels).not.toContain('Distance')
    expect(labels).not.toContain('Top speed')
  })

  it('plots the y metric against the x metric', async () => {
    api({ segments: { drives: [], charges: [charge()] } })
    const { wrapper } = mountWidget('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' })
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
    const { wrapper } = mountWidget('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' })
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

    // Inside the map's own frame, not in the card around it: the frame is what
    // fills the viewport when the map is expanded, and a readout left in the
    // card went behind the expanded map with it.
    const readout = wrapper.get('.map-context-stub .route-readout')
    expect(readout.text()).toContain('Distance')
    expect(readout.text()).toContain('Duration')
    // 82% to 71% over a 16 kWh pack is 1.8 kWh.
    expect(readout.text()).toContain('11%')
    expect(readout.text()).toContain('1.8 kWh')
  })

  it('keeps the picking hint with the map rather than with the card head', async () => {
    api({ segments: { drives: [drive()], charges: [] } })
    const { wrapper } = mountWidget('route-map')
    await flushPromises()
    // Nothing picked yet, so the strip inside the frame says what picking does.
    expect(wrapper.get('.map-context-stub').text()).toContain('Tap two points')
    expect(wrapper.get('.widget-head').text()).not.toContain('Tap two points')
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

  it('omits the energy row for a vehicle that never charges, and keeps it once it has', async () => {
    api({ segments: { drives: [drive()], charges: [] }, previous: { drives: [], charges: [] } })
    const petrol = mountWidget('period-stats', { time_range_days: 7 })
    await flushPromises()
    const petrolStats = petrol.wrapper.findAll('.stat-grid > div').map((row) => row.get('dt').text())
    expect(petrolStats).toContain('Distance')
    expect(petrolStats).toContain('Drives')
    // Nothing charged this vehicle, so it is not told it charged 0.0 kWh.
    expect(petrolStats).not.toContain('Energy charged')

    api({ segments: { drives: [drive()], charges: [charge({ energy_kwh: 0 })] }, previous: { drives: [], charges: [] } })
    const electric = mountWidget('period-stats', { time_range_days: 7 })
    await flushPromises()
    // A charge that drew nothing measurable is still a charge, and says so.
    const electricStats = Object.fromEntries(electric.wrapper.findAll('.stat-grid > div').map((row) => [row.get('dt').text(), row.get('dd').text()]))
    expect(electricStats['Energy charged']).toContain('0.0 kWh')
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
    const chart = mountWidget('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' })
    await flushPromises()
    expect(chart.wrapper.find('.chart-stub').exists()).toBe(true)
  })

  it.each([
    ['route-map', {}],
    ['segment-stats', {}],
    ['xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' }],
  ] as const)(
    'says so in %s when the selection is outside its own range',
    async (type, config) => {
      // A selection the range cannot show is stated, not quietly swapped for another.
      api({ segments: { drives: [drive()], charges: [charge()] } })
      const { wrapper } = mountWidget(type, config, { kind: 'drive', start: '2020-01-01T00:00:00Z', end: '2020-01-01T01:00:00Z' })
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
    const { wrapper } = mountWidget('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' })
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
    const parked = { ...vehicle, state: { ...vehicle.state, position: null, readings: {} } } as unknown as Vehicle
    // The route map is about where the vehicle went, which a live snapshot cannot
    // answer either way, so it stays and lets its own range decide.
    expect(widgetRegistry['route-map']!.isEmpty?.({ id: 'w', type: 'route-map', x: 0, y: 0, w: 4, h: 3 }, parked)).toBe(false)
  })

  it('hides an x-y chart only when the vehicle reports neither of its axes', () => {
    const chart = (extra: Partial<DashboardWidget>, metrics: Record<string, unknown>) =>
      widgetRegistry['xy-chart']!.isEmpty?.(
        { id: 'w', type: 'xy-chart', x: 0, y: 0, w: 4, h: 3, ...extra },
        { ...vehicle, state: { ...vehicle.state, position: null, readings: readings(metrics) } } as unknown as Vehicle,
      )
    // A chart plots a range, so a live value that has gone is not an empty
    // chart. charging.power leaves live state the moment a charge ends, and the
    // finished charge's own graph must still be there to look at.
    const curve = { x_metric: 'battery.soc', y_metric: 'charging.power' }
    expect(chart(curve, { 'battery.soc': 61 })).toBe(false)
    expect(chart(curve, { 'charging.power': 7 })).toBe(false)
    expect(chart(curve, { 'engine.rpm': 900 })).toBe(false)
    expect(chart(curve, {})).toBe(false)
    // Axes the vehicle has never carried are still worth a card: the range
    // decides, and the widget says for itself when the window holds nothing.
    expect(chart({ x_metric: 'vehicle.speed', y_metric: 'engine.rpm' }, { 'battery.soc': 61 })).toBe(false)
    // A chart with no axes chosen plots nothing at all, so it hides rather than
    // falling back to metrics the vehicle was never asked about.
    expect(chart({}, { 'battery.soc': 61, 'charging.power': 7 })).toBe(true)
  })

  it('gives every data widget a hiding predicate, and says why two have none', () => {
    // The editor only offers the hide toggle where isEmpty can answer, so a
    // widget without one silently loses the feature.
    const without = Object.values(widgetRegistry).filter((definition) => !definition.isEmpty).map((definition) => definition.type)
    // vehicle-selector drives every other card; hook-activity is not scoped to a
    // vehicle, and isEmpty is handed nothing else to judge from.
    expect(without.sort()).toEqual(['hook-activity', 'vehicle-selector'])
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
    const { wrapper } = mountWidget('xy-chart', { x_metric: 'battery.soc', y_metric: 'charging.power' }, { kind: 'drive', start: '2020-01-01T00:00:00Z', end: '2020-01-01T01:00:00Z' })
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

describe('time a segment could not account for', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  /*
   * The case from the field: a 1 h 41 min drive of 30 real km, of which 5916 s
   * were the agent saying nothing. Told to the minute, because rounded to one
   * unit both figures came out "2 hours" and the caption qualified nothing.
   */
  it('formats the unreported share in both locales', () => {
    expect(unreportedSpan({ unreported_seconds: 5916 }, 'en')).toBe('1 hr 39 min')
    // Intl joins French units with non-breaking spaces, which is the point of
    // going through the formatter rather than assembling the string here.
    expect(unreportedSpan({ unreported_seconds: 5916 }, 'fr')).toBe('1\u202fh 39\u00a0min')
    expect(unreportedSpan({ unreported_seconds: 2340 }, 'en')).toBe('39 min')
  })

  it('says nothing when the source covered the whole segment', () => {
    // Zero is the ordinary case, and a caption on every row would be noise.
    expect(unreportedSpan({ unreported_seconds: 0 }, 'en')).toBeNull()
    expect(unreportedSpan({}, 'en')).toBeNull()
    expect(unreportedSpan(null, 'en')).toBeNull()
    // A server that sends nonsense is a server with nothing to say.
    expect(unreportedSpan({ unreported_seconds: Number.NaN }, 'en')).toBeNull()
  })

  it('qualifies the feed caption without touching the duration or the distance', async () => {
    api({ segments: { drives: [drive({ duration_seconds: 6060, unreported_seconds: 5916, distance_km: 30 })], charges: [] } })
    const { wrapper } = mountWidget('activity-feed')
    await flushPromises()
    const row = wrapper.get('.feed-row')
    // The odometer still owns the distance and the edges still own the span.
    expect(row.text()).toContain('30.0 km driven')
    // The two figures now differ, which is the whole point of the caption: most
    // of the drive went unheard, and the span is not two hours of driving.
    expect(row.get('small').text()).toContain('1 hr 41 min · 1 hr 39 min unreported')
  })

  it('leaves the caption off a segment its source described throughout', async () => {
    api({ segments: { drives: [drive()], charges: [] } })
    const { wrapper } = mountWidget('activity-feed')
    await flushPromises()
    expect(wrapper.get('.feed-row').text()).not.toContain('unreported')
  })

  it('carries the same wording into the followed segment card and the route subtitle', async () => {
    api({ segments: { drives: [drive({ duration_seconds: 6060, unreported_seconds: 5916 })], charges: [] } })
    const stats = mountWidget('segment-stats')
    await flushPromises()
    // The card's own duration fact is told at the same precision as the caption.
    expect(stats.wrapper.find('.segment-facts').text()).toContain('1 hr 41 min')
    expect(stats.wrapper.get('.segment-unreported').text()).toBe('1 hr 39 min unreported')

    api({ segments: { drives: [drive({ duration_seconds: 6060, unreported_seconds: 5916 })], charges: [] } })
    const map = mountWidget('route-map')
    await flushPromises()
    expect(map.wrapper.get('.widget-head span').text()).toContain('1 hr 39 min unreported')
    // Nothing on the map changes: the trail is still the positions that arrived.
    expect(map.wrapper.findAll('.trail-point')).toHaveLength(3)
  })

  it('explains the caption once, in the feed head, rather than on every row', async () => {
    api({ segments: { drives: [drive({ unreported_seconds: 5916 })], charges: [] } })
    const { wrapper } = mountWidget('activity-feed')
    await flushPromises()
    await wrapper.get('.widget-head .app-help-button').trigger('click')
    await flushPromises()
    expect(document.body.textContent).toContain('the distance still comes from the odometer')
  })
})

describe('pairing two axes that never arrive together', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  /** The real car: one CAN frame carries the level, another the power. */
  function alternating(count: number, spacingMs: number) {
    const start = Date.parse('2026-08-27T20:00:00Z')
    return Array.from({ length: count }, (_, index) => ({
      id: `p${index}`,
      recorded_at: new Date(start + index * spacingMs).toISOString(),
      latitude: null, longitude: null, speed: null, heading: null,
      metrics: index % 2 === 0 ? { 'battery.soc': 40 + index * 0.5 } : { 'charging.power': 2.2 + (index % 5) * 0.2 },
    }))
  }

  const curve = { x_metric: 'battery.soc', y_metric: 'charging.power', time_range_days: 7 }

  it('pairs sparse axes that alternate between samples', async () => {
    // Neither metric ever shares a sample with the other, which is the shape the
    // simulator never produced and the car always does.
    const points = alternating(40, 8_000)
    expect(points.every((point) => Object.keys(point.metrics).length === 1)).toBe(true)
    api({ history: { vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: points.length, points } })
    const { wrapper } = mountWidget('xy-chart', curve)
    await flushPromises()

    const plotted = Number(wrapper.get('.chart-stub').attributes('data-points'))
    expect(plotted).toBeGreaterThan(1)
    expect(wrapper.text()).not.toContain('No paired readings')
  })

  it('refuses to pair readings taken hours apart', async () => {
    // A level from this morning against a power from tonight is a point that
    // never existed, so the card says it has nothing rather than drawing it.
    const start = Date.parse('2026-08-27T06:00:00Z')
    const points = [
      { id: 'a', recorded_at: new Date(start).toISOString(), latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 61 } },
      { id: 'b', recorded_at: new Date(start + 5 * 3_600_000).toISOString(), latitude: null, longitude: null, speed: null, heading: null, metrics: { 'charging.power': 7 } },
      { id: 'c', recorded_at: new Date(start + 10 * 3_600_000).toISOString(), latitude: null, longitude: null, speed: null, heading: null, metrics: { 'battery.soc': 64 } },
    ]
    api({ history: { vehicle_id: vehicle.id, start: '', end: '', available_metrics: [], original_count: 3, points } })
    const { wrapper } = mountWidget('xy-chart', curve)
    await flushPromises()

    expect(wrapper.find('.chart-stub').exists()).toBe(false)
    expect(wrapper.text()).toContain('No paired readings')
  })

  it('still pairs when both axes do share a sample', async () => {
    // The simulator's shape must keep working; the bound only drops stale ends.
    api()
    const { wrapper } = mountWidget('xy-chart', { ...curve, time_range_days: 30 })
    await flushPromises()
    expect(Number(wrapper.get('.chart-stub').attributes('data-points'))).toBeGreaterThan(1)
  })
})
