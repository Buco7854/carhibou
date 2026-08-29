import { describe, expect, it } from 'vitest'
import type { Vehicle } from '../src/api/types'
import { formatAge, formatSpan, chargingState, defaultDashboardMetrics, energySummary, headlineReading, isFresh, metricReading, preferredHistoryMetric, reportedKeys, secondaryReadings, vehicleActivity } from '../src/vehicleDisplay'
import { readings, vehicle } from './helpers'

function withMetrics(values: Record<string, unknown>): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position: null, readings: readings(values) } }
}

/** The same vehicle, with one reading the server has marked past its freshness. */
function stale(values: Record<string, unknown>): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position: null, readings: readings(values, { fresh: false }) } }
}

describe('telemetry-driven vehicle display', () => {
  it('uses battery metrics when the agent reports them', () => {
    const current = withMetrics({ 'battery.soc': 72, 'battery.power': -8.4, 'charging.active': false })
    expect(energySummary(current)).toMatchObject({ key: 'battery.soc', value: 72, unit: '%' })
    expect(secondaryReadings(current).map((row) => row.key)).toEqual(['battery.power', 'charging.active'])
  })

  it('uses fuel and engine metrics when those are reported', () => {
    const current = withMetrics({ 'fuel.level': 58, 'engine.rpm': 1850, 'engine.coolant_temperature': 91 })
    expect(energySummary(current)).toMatchObject({ key: 'fuel.level', value: 58, unit: '%' })
    expect(secondaryReadings(current).map((row) => row.key)).toEqual(['engine.rpm', 'engine.coolant_temperature'])
    expect(preferredHistoryMetric(current, ['engine.rpm', 'fuel.level'], true)).toBe('fuel.level')
  })

  it('shows battery and fuel data together without classifying the vehicle', () => {
    const current = withMetrics({ 'battery.soc': 61, 'fuel.level': 44 })
    expect(energySummary(current)).toMatchObject({ key: 'battery.soc', value: 61 })
    expect(secondaryReadings(current)[0]).toMatchObject({ key: 'fuel.level', value: 44 })
    expect(defaultDashboardMetrics(current)).toEqual(['battery.soc', 'fuel.level'])
  })

  it('keeps a neutral empty state when no energy metric exists', () => {
    const current = withMetrics({})
    expect(energySummary(current)).toMatchObject({ key: '', value: null, labelKey: 'metrics.energyLevel' })
    expect(preferredHistoryMetric(current, ['custom.metric'], false)).toBe('custom.metric')
    expect(defaultDashboardMetrics(current)).toEqual(['vehicle.speed'])
  })

  it('leads with an energy level only when the vehicle reports one', () => {
    expect(headlineReading(withMetrics({ 'battery.soc': 72 }))).toMatchObject({ key: 'battery.soc', value: 72 })
    expect(headlineReading(withMetrics({ 'fuel.level': 58 }))).toMatchObject({ key: 'fuel.level', value: 58 })
  })

  it('promotes the most conventional reading when no energy metric exists', () => {
    // A standard OBD-II car with no profile: no traction-battery SOC, and many
    // never implement the optional fuel-level PID.
    const diesel = withMetrics({
      'engine.throttle': 24, 'engine.coolant_temperature': 88, 'engine.rpm': 2100, 'engine.load': 41,
    })
    expect(headlineReading(diesel)).toMatchObject({ key: 'engine.rpm', value: 2100 })
    expect(secondaryReadings(diesel).map((row) => row.key)).toEqual(['engine.rpm', 'engine.coolant_temperature'])
  })

  it('never offers a reading the vehicle has not reported', () => {
    const sparse = withMetrics({ 'engine.rpm': 900 })
    expect(secondaryReadings(sparse).map((row) => row.key)).toEqual(['engine.rpm'])
    expect(headlineReading(withMetrics({}))).toBeNull()
  })

  it('reads the resolved charging flag and never derives one', () => {
    // The server owns the derivation, including the power floor that keeps a
    // resting pack from reading as a charge. A widget deriving it separately is
    // how the same car came to be charging on one card and parked on another.
    expect(chargingState(withMetrics({ 'charging.active': true, 'charging.power': 6.6 })))
      .toEqual({ active: true, power: 6.6 })
    expect(chargingState(withMetrics({ 'charging.active': false, 'charging.power': 6.6 })))
      .toEqual({ active: false, power: null })
  })

  it('treats power on its own as no evidence at all', () => {
    // Whatever battery.power says, and however large, it is not a charging flag.
    for (const power of [-11.2, -1.4, -0.5, -0.2, 0, 8.4]) {
      expect(chargingState(withMetrics({ 'battery.power': power })), `${power} kW`)
        .toEqual({ active: null, power: null })
    }
  })

  it('reports charging as unknown once its evidence has gone stale', () => {
    // Charging is safety-sensitive: an expired reading is not a charge that is
    // probably still running, it is a charge nobody can vouch for.
    expect(chargingState(stale({ 'charging.active': true, 'charging.power': 6.6 })))
      .toEqual({ active: null, power: null })
    expect(chargingState(stale({ 'charging.active': false }))).toEqual({ active: null, power: null })
  })

  it('says charging without a rate when the rate was not resolved', () => {
    expect(chargingState(withMetrics({ 'charging.active': true }))).toEqual({ active: true, power: null })
  })

  it('reports unknown charging rather than guessing for a vehicle without battery data', () => {
    expect(chargingState(withMetrics({ 'engine.rpm': 1500 }))).toEqual({ active: null, power: null })
  })

  it('carries the server\u2019s provenance through to whatever renders the value', () => {
    const current = withMetrics({ 'battery.soc': 61 })
    const soc = metricReading(current, 'battery.soc')
    expect(soc.value).toBe(61)
    expect(soc.provenance).toMatchObject({ source_id: 'agent-1', source_kind: 'agent', channel: 'can', method: 'direct', fresh: true })
    expect(isFresh(current, 'battery.soc')).toBe(true)
    expect(isFresh(stale({ 'battery.soc': 61 }), 'battery.soc')).toBe(false)
    // A key with no reading has no provenance to show, and no value either.
    const absent = metricReading(current, 'engine.rpm')
    expect(absent.value).toBeNull()
    expect(absent.provenance).toBeNull()
  })

  it('renders a missing reading as absent rather than as zero or false', () => {
    const bare = withMetrics({})
    // A number nobody reported is not 0, and a flag nobody reported is not false.
    expect(metricReading(bare, 'battery.soc').value).toBeNull()
    expect(metricReading(bare, 'vehicle.handbrake').value).toBeNull()
    expect(energySummary(bare).value).toBeNull()
    expect(headlineReading(bare)).toBeNull()
  })

  it('keeps namespaced extension keys as ordinary readings', () => {
    // A connector passes through whatever its broker publishes. Those keys are
    // readings like any other, so generic cards can see the vehicle reports them.
    const current = withMetrics({ 'battery.soc': 61, 'teslamate.inside_temp': 21.5 })
    expect(reportedKeys(current)).toContain('teslamate.inside_temp')
    expect(metricReading(current, 'teslamate.inside_temp').value).toBe(21.5)
    expect(secondaryReadings(current).map((row) => row.key)).toContain('teslamate.inside_temp')
  })

  it('calls the vehicle parked only on evidence that it is at rest', () => {
    const online = (values: Record<string, unknown>, agent: Record<string, unknown> = {}) =>
      ({ ...vehicle, state: { ...vehicle.state!, online: true, position: null, readings: readings(values), agent } }) as Vehicle
    // Positive evidence of rest.
    expect(vehicleActivity(online({ 'vehicle.speed': 0 }))).toBe('parked')
    expect(vehicleActivity(online({}, { vehicle_in_use: false }))).toBe('parked')
    // Positive evidence of motion.
    expect(vehicleActivity(online({ 'vehicle.speed': 42 }))).toBe('driving')
    expect(vehicleActivity(online({ 'charging.active': true }))).toBe('charging')
    // No evidence either way. A car nobody can hear from is not a parked car,
    // and an unknown charging flag must not settle into "not charging".
    expect(vehicleActivity(online({}))).toBe('unknown')
    expect(vehicleActivity(online({ 'battery.power': -11.2 }))).toBe('unknown')
    // An agent that has stopped reporting says nothing about the vehicle at all.
    expect(vehicleActivity({ ...vehicle, state: { ...vehicle.state!, online: false } } as Vehicle)).toBe('unknown')
  })

  it('anchors an age to now and refuses to be handed a duration', () => {
    // The bug this pins: a fix taken 14 seconds before the upload that carried it
    // read "14 seconds ago" while sitting five minutes in the past. The gap
    // between two stored instants is a span; only distance from now is an age.
    const now = Date.parse('2026-08-29T18:20:00Z')
    const observed = '2026-08-29T18:15:27Z'
    const received = '2026-08-29T18:19:46Z'
    // The instant a reader sees is the instant the age describes.
    expect(formatAge(observed, 'en', now)).toBe('5 minutes ago')
    // Feeding it the upload instead is the whole defect, and it says so loudly.
    expect(formatAge(received, 'en', now)).not.toBe(formatAge(observed, 'en', now))
    // The intra-sample gap is fourteen seconds and is never an age.
    const gap = Math.round((Date.parse(received) - Date.parse(observed)) / 1000)
    expect(gap).toBe(259)
    expect(formatSpan(gap, 'en')).toBe('4 minutes')
    // A future instant does not become "in 3 minutes"; clocks disagree.
    expect(formatAge('2026-08-29T18:23:00Z', 'en', now)).toBe('now')
  })
})
