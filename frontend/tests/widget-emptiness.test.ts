import { describe, expect, it } from 'vitest'
import type { DashboardWidget, Vehicle } from '../src/api/types'
import { widgetRegistry } from '../src/widgets/registry'
import { readings, vehicle } from './helpers'

/**
 * What a widget must be asked before it may hide.
 *
 * Hiding means "this card has nothing at all to show", so the question has to go
 * to the data the card actually draws. A live-state card asks what the vehicle
 * is reporting now, stale included, because a retained reading is data. A card
 * over a time range cannot ask its range synchronously, so it asks the cheapest
 * honest proxy instead: has this vehicle ever reported, and is the card even
 * pointed at anything. Getting that backwards is what made a finished charge's
 * own graph disappear the moment its live value expired.
 */
type Rule = 'live-reading' | 'range' | 'vehicle-attribute' | 'agent-state' | 'never-hides'

const RULES: Record<string, Rule> = {
  'vehicle-selector': 'never-hides',
  'hook-activity': 'never-hides',
  'vehicle-media': 'vehicle-attribute',
  'agent-health': 'agent-state',
  'telemetry-list': 'live-reading',
  'metric-card': 'live-reading',
  'battery-gauge': 'live-reading',
  'charging': 'live-reading',
  'online-status': 'live-reading',
  'position-map': 'range',
  'route-map': 'range',
  'time-series': 'range',
  'multi-series': 'range',
  'xy-chart': 'range',
  'activity-feed': 'range',
  'segment-stats': 'range',
  'period-stats': 'range',
}

/** A configuration that points each card at something it could draw. */
const CONFIGURED: Record<string, Partial<DashboardWidget>> = {
  'metric-card': { metric: 'battery.soc' },
  'time-series': { metric: 'battery.soc' },
  'telemetry-list': { metrics: ['battery.soc'] },
  'multi-series': { metrics: ['battery.soc'] },
  'xy-chart': { x_metric: 'battery.soc', y_metric: 'charging.power' },
}

function widgetOf(type: string): DashboardWidget {
  return { id: 'w', type, x: 0, y: 0, w: 4, h: 3, ...CONFIGURED[type] }
}

function withState(state: Partial<NonNullable<Vehicle['state']>> | null, extra: Partial<Vehicle> = {}): Vehicle {
  return {
    ...vehicle, ...extra,
    state: state === null ? null : { ...vehicle.state!, position: null, agent: {}, readings: {}, ...state },
  } as Vehicle
}

const NEVER_REPORTED = withState(null, { photo_url: null })
const REPORTING = withState({ readings: readings({ 'battery.soc': 61, 'charging.active': false }) }, { photo_url: null })
const STALE_ONLY = withState({ readings: readings({ 'battery.soc': 61 }, { fresh: false }) }, { photo_url: null })
const OTHER_METRIC = withState({ readings: readings({ 'engine.rpm': 900 }) }, { photo_url: null })

function hides(type: string, current: Vehicle): boolean {
  return Boolean(widgetRegistry[type]!.isEmpty?.(widgetOf(type), current))
}

describe('what each widget asks before it hides', () => {
  it('classifies every registered widget, so a new one cannot arrive unclassified', () => {
    expect(Object.keys(RULES).sort()).toEqual(Object.keys(widgetRegistry).sort())
  })

  it('gives a hiding predicate to everything except the two that must never hide', () => {
    for (const [type, rule] of Object.entries(RULES)) {
      const declared = Boolean(widgetRegistry[type]!.isEmpty)
      expect(declared, type).toBe(rule !== 'never-hides')
    }
  })

  it('hides nothing at all for a vehicle that is reporting what the card wants', () => {
    for (const [type, rule] of Object.entries(RULES)) {
      if (rule === 'vehicle-attribute' || rule === 'agent-state') continue
      expect(hides(type, REPORTING), type).toBe(false)
    }
  })

  it('treats a retained reading as data, because a sleeping car still has a charge level', () => {
    // Every card that judges by a live reading must survive that reading going
    // stale: the value is still true, it is simply older than the freshness
    // window. Only charging is excepted, and the server excepts it for us by
    // dropping the flag rather than retaining it.
    for (const [type, rule] of Object.entries(RULES)) {
      if (rule !== 'live-reading' || type === 'charging') continue
      expect(hides(type, STALE_ONLY), type).toBe(false)
    }
  })

  it('keeps a range card while the vehicle has history, whatever the live value is doing', () => {
    // charging.power leaves live state the moment a charge ends. The graph of
    // that charge is still in the range and must still be there to look at.
    for (const [type, rule] of Object.entries(RULES)) {
      if (rule !== 'range') continue
      expect(hides(type, OTHER_METRIC), `${type} judged itself by a live value`).toBe(false)
    }
  })

  it('hides a live-reading card whose own reading is absent', () => {
    for (const [type, rule] of Object.entries(RULES)) {
      if (rule !== 'live-reading' || type === 'online-status' || type === 'telemetry-list') continue
      expect(hides(type, OTHER_METRIC), type).toBe(true)
    }
    // online-status reports the connection itself, so any state at all is data.
    expect(hides('online-status', OTHER_METRIC)).toBe(false)
  })

  it('hides every vehicle-scoped card for a vehicle that has never reported', () => {
    for (const [type, rule] of Object.entries(RULES)) {
      if (rule === 'never-hides') continue
      expect(hides(type, NEVER_REPORTED), type).toBe(true)
    }
  })

  it('hides a range card that has been pointed at nothing', () => {
    const unconfigured = (type: string) => Boolean(widgetRegistry[type]!.isEmpty?.({ id: 'w', type, x: 0, y: 0, w: 4, h: 3 }, REPORTING))
    for (const type of ['time-series', 'multi-series', 'xy-chart']) {
      expect(unconfigured(type), type).toBe(true)
    }
    // A map needs no configuration to know what to draw.
    for (const type of ['position-map', 'route-map']) {
      expect(unconfigured(type), type).toBe(false)
    }
  })

  it('judges the photo and the agent panel by their own subjects', () => {
    expect(hides('vehicle-media', withState({ readings: readings({ 'battery.soc': 61 }) }, { photo_url: null }))).toBe(true)
    expect(hides('vehicle-media', withState(null, { photo_url: '/media/car.jpg' }))).toBe(false)
    expect(hides('agent-health', REPORTING)).toBe(true)
    expect(hides('agent-health', withState({ agent: { mobile_signal: -70 } }, { photo_url: null }))).toBe(false)
  })
})
