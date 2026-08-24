import { describe, expect, it } from 'vitest'
import type { Vehicle } from '../src/api/types'
import { defaultDashboardMetrics, energySummary, preferredHistoryMetric, secondaryReadings } from '../src/vehicleDisplay'
import { vehicle } from './helpers'

function withMetrics(metrics: Record<string, unknown>): Vehicle {
  return { ...vehicle, state: { ...vehicle.state!, position: null, metrics } }
}

describe('telemetry-driven vehicle display', () => {
  it('uses battery metrics when the tracker reports them', () => {
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
})
