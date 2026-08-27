import { describe, expect, it } from 'vitest'
import type { Vehicle } from '../src/api/types'
import { chargingState, defaultDashboardMetrics, energySummary, headlineReading, preferredHistoryMetric, secondaryReadings } from '../src/vehicleDisplay'
import { vehicle } from './helpers'

function withMetrics(metrics: Record<string, unknown>): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position: null, metrics } }
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

  it('derives charging from battery power when the vehicle does not report it', () => {
    // Convention: battery power is negative while the pack absorbs energy.
    expect(chargingState(withMetrics({ 'battery.power': -11.2 }))).toEqual({ active: true, power: 11.2 })
    expect(chargingState(withMetrics({ 'battery.power': 8.4 }))).toEqual({ active: false, power: null })
  })

  it('prefers an explicitly reported charging flag and rate', () => {
    expect(chargingState(withMetrics({ 'charging.active': true, 'charging.power': 6.6, 'battery.power': 2 })))
      .toEqual({ active: true, power: 6.6 })
    expect(chargingState(withMetrics({ 'charging.active': false, 'battery.power': -3 })))
      .toEqual({ active: false, power: null })
  })

  it('reports unknown charging rather than guessing for a vehicle without battery data', () => {
    expect(chargingState(withMetrics({ 'engine.rpm': 1500 }))).toEqual({ active: null, power: null })
  })
})
