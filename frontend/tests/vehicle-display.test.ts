import { describe, expect, it } from 'vitest'
import type { Vehicle } from '../src/api/types'
import { defaultDashboardMetrics, energySummary, preferredHistoryMetric, propulsionFamily, secondaryReadings } from '../src/vehicleDisplay'
import { vehicle } from './helpers'

function asVehicle(propulsion_type: string, metrics: Record<string, unknown>): Vehicle {
  return { ...vehicle, propulsion_type, state: { ...vehicle.state!, position: null, metrics } }
}

describe('propulsion-aware vehicle display', () => {
  it('uses traction battery and charging data for electric vehicles', () => {
    const electric = asVehicle('electric', { 'battery.soc': 72, 'battery.power': -8.4, 'charging.active': false })
    expect(propulsionFamily(electric)).toBe('electric')
    expect(energySummary(electric)).toMatchObject({ key: 'battery.soc', value: 72, unit: '%' })
    expect(secondaryReadings(electric).map((row) => row.key)).toEqual(['battery.power', 'charging.active'])
  })

  it.each(['petrol', 'diesel'])('uses fuel and engine data for %s vehicles', (propulsion) => {
    const thermal = asVehicle(propulsion, { 'fuel.level': 58, 'engine.rpm': 1850, 'engine.coolant_temperature': 91 })
    expect(propulsionFamily(thermal)).toBe('thermal')
    expect(energySummary(thermal)).toMatchObject({ key: 'fuel.level', value: 58, unit: '%' })
    expect(secondaryReadings(thermal).map((row) => row.key)).toEqual(['engine.rpm', 'engine.coolant_temperature'])
    expect(preferredHistoryMetric(thermal, ['engine.rpm', 'fuel.level'], true)).toBe('fuel.level')
  })

  it('falls back between battery and fuel for hybrids without inventing a value', () => {
    const hybrid = asVehicle('hybrid', { 'fuel.level': 43, 'engine.rpm': 1100 })
    expect(energySummary(hybrid)).toMatchObject({ key: 'fuel.level', value: 43 })
    expect(defaultDashboardMetrics(hybrid)).toEqual(['fuel.level', 'engine.rpm'])

    const plugInHybrid = asVehicle('hybrid', { 'battery.soc': 61, 'fuel.level': 44 })
    expect(energySummary(plugInHybrid)).toMatchObject({ key: 'battery.soc', value: 61 })
    expect(secondaryReadings(plugInHybrid)[0]).toMatchObject({ key: 'fuel.level', value: 44 })
  })

  it('infers a useful family from canonical metrics for legacy unknown vehicles', () => {
    const legacy = asVehicle('unknown', { 'engine.rpm': 900 })
    expect(propulsionFamily(legacy)).toBe('thermal')
    expect(energySummary(legacy)).toMatchObject({ key: 'fuel.level', value: null, progress: 0 })
  })

  it('keeps a neutral empty energy state when neither type nor telemetry provides a clue', () => {
    const unknown = asVehicle('unknown', {})
    expect(energySummary(unknown)).toMatchObject({ key: '', value: null, labelKey: 'metrics.energyLevel' })
    expect(preferredHistoryMetric(unknown, ['custom.metric'], false)).toBe('custom.metric')
  })
})
