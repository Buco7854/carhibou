import { describe, expect, it } from 'vitest'
import { suggestCanonicalKey } from '../src/canonicalHints'

const CANONICAL = [
  'battery.soc', 'battery.power', 'battery.pack_voltage', 'battery.current',
  'vehicle.speed', 'vehicle.odometer', 'vehicle.state',
  'charging.power', 'charging.active', 'engine.coolant_temperature',
]

const suggest = (key: string) => suggestCanonicalKey(key, CANONICAL)

describe('canonical near misses', () => {
  it('says nothing about a key that is already canonical', () => {
    for (const key of CANONICAL) expect(suggest(key), key).toBeNull()
  })

  it('recognises the same key written with other separators or in camel case', () => {
    expect(suggest('battery_soc')).toBe('battery.soc')
    expect(suggest('batterySoc')).toBe('battery.soc')
    expect(suggest('BATTERY-SOC')).toBe('battery.soc')
    expect(suggest('battery_pack_voltage')).toBe('battery.pack_voltage')
    expect(suggest('vehicleOdometer')).toBe('vehicle.odometer')
  })

  it('recognises a key written without its namespace', () => {
    expect(suggest('soc')).toBe('battery.soc')
    expect(suggest('speed')).toBe('vehicle.speed')
    expect(suggest('odometer')).toBe('vehicle.odometer')
    expect(suggest('pack_voltage')).toBe('battery.pack_voltage')
  })

  it('recognises a small slip of the fingers', () => {
    expect(suggest('batery.soc')).toBe('battery.soc')
    expect(suggest('vehicle.sped')).toBe('vehicle.speed')
    expect(suggest('odomter')).toBe('vehicle.odometer')
  })

  it('leaves a deliberately custom key alone', () => {
    // The whole point of the namespaced space: these are meant, not mistyped.
    expect(suggest('teslamate.sentry_mode')).toBeNull()
    expect(suggest('site.oil_pressure')).toBeNull()
    expect(suggest('custom.cabin_humidity')).toBeNull()
    expect(suggest('mqtt.raw_frame_count')).toBeNull()
  })

  it('says nothing about a fix, whose targets are canonical in their own right', () => {
    expect(suggest('position.latitude')).toBeNull()
    expect(suggest('position.speed')).toBeNull()
  })

  it('refuses to guess from too little to go on', () => {
    // Three characters land within one edit of far too much to be a signal.
    expect(suggest('soo')).toBeNull()
    expect(suggest('ab')).toBeNull()
    expect(suggest('')).toBeNull()
    expect(suggest('   ')).toBeNull()
  })

  it('always draws the same suggestion for an ambiguous stem', () => {
    // `power` is the tail of two canonical keys; the answer is stable either way.
    expect(suggest('power')).toBe(suggest('power'))
    expect(['battery.power', 'charging.power']).toContain(suggest('power'))
  })
})
