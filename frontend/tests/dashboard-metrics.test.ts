import { describe, expect, it } from 'vitest'
import { metricsForCard, presentationAllowsMany, resolveMetricPatterns } from '../src/dashboardMetrics'

const available = ['battery.soc', 'battery.power', 'tyre.front_left_pressure', 'tyre.rear_left_pressure', 'vehicle.speed']

describe('dashboard metric selection', () => {
  it('takes an exact name or a prefix', () => {
    expect(resolveMetricPatterns(['battery.soc'], available)).toEqual(['battery.soc'])
    // A prefix keeps a card correct when a profile gains a signal, so a tyre card
    // shows a fourth wheel without being edited.
    expect(resolveMetricPatterns(['tyre.*'], available)).toEqual([
      'tyre.front_left_pressure', 'tyre.rear_left_pressure',
    ])
  })

  it('follows the order the card asked for, and names a metric once', () => {
    expect(resolveMetricPatterns(['vehicle.speed', 'battery.*'], available)).toEqual([
      'vehicle.speed', 'battery.power', 'battery.soc',
    ])
    // Matched by both an exact name and a prefix, it still appears once.
    expect(resolveMetricPatterns(['battery.soc', 'battery.*'], available)).toEqual([
      'battery.soc', 'battery.power',
    ])
  })

  it('asks for nothing the vehicle does not report', () => {
    expect(resolveMetricPatterns(['engine.rpm', 'tyre.*'], ['vehicle.speed'])).toEqual([])
  })

  it('knows which presentations are a list and which are one value', () => {
    // A gauge is a proportion of one thing and a reading is one number; neither
    // has an arrangement for a second.
    expect(presentationAllowsMany('gauge')).toBe(false)
    expect(presentationAllowsMany('reading')).toBe(false)
    expect(presentationAllowsMany('table')).toBe(true)
    expect(presentationAllowsMany('chart')).toBe(true)
  })

  it('gives a single-value card one metric even when its patterns match more', () => {
    // The first the patterns named, so the choice stays the author's rather than
    // whatever order the vehicle reported in.
    expect(metricsForCard(['battery.*'], available, 'gauge')).toEqual(['battery.power'])
    expect(metricsForCard(['battery.soc', 'battery.*'], available, 'gauge')).toEqual(['battery.soc'])
    expect(metricsForCard(['battery.*'], available, 'table')).toEqual(['battery.power', 'battery.soc'])
  })
})
