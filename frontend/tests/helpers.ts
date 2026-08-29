import { vi, type Mock } from 'vitest'
import type { DOMWrapper } from '@vue/test-utils'
import type { PositionFix, Provenance, Reading, ResolvedPosition } from '../src/api/types'

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

export const adminUser = {
  id: 'admin-1', email: 'admin@example.com', display_name: 'Admin', permissions: { 'system.admin': true },
}

export const memberUser = {
  id: 'member-1', email: 'member@example.com', display_name: 'Member', permissions: {},
}

export const vehicle = {
  id: 'vehicle-1',
  name: 'Éclair',
  manufacturer: 'Citroën',
  model: 'C-Zero',
  year: 2018,
  battery_nominal_capacity_kwh: 16,
  timezone: 'UTC',
  color: '#65e0ad',
  icon: 'car',
  photo_url: null,
  access: 'operate' as const,
  state: {
    updated_at: new Date().toISOString(),
    online: true,
    position: resolvedPosition(),
    readings: readings({ 'battery.soc': 70, 'battery.power': -11.1 }),
    agent: { mobile_signal: -82 },
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

/**
 * A resolved reading map from plain values.
 *
 * Live state carries provenance on every metric now, and a test that spells all
 * six fields out per key says nothing about what it is testing. Defaults are a
 * fresh direct reading from one agent; pass overrides to make one stale or to
 * give it a different channel.
 */
export function readings(
  values: Record<string, unknown>,
  overrides: Partial<Reading> = {},
): Record<string, Reading> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, {
    value,
    observed_at: '2026-08-28T12:00:00Z',
    source_id: 'agent-1',
    source_kind: 'agent' as const,
    channel: 'can' as const,
    method: 'direct' as const,
    fresh: true,
    ...overrides,
  }]))
}

/** A resolved position: the fix plus the provenance the server chose it with. */
export function resolvedPosition(fix: Partial<PositionFix> = {}, overrides: Partial<Provenance> = {}): ResolvedPosition {
  return {
    latitude: 48, longitude: 2, altitude: 20, speed: 42, heading: 90, accuracy: 5,
    observed_at: '2026-08-28T12:00:00Z',
    source_id: 'agent-1',
    source_kind: 'agent',
    channel: 'gnss',
    method: 'direct',
    fresh: true,
    ...fix,
    ...overrides,
  }
}

export const agentImplementations = [
  {
    id: 'carhibou.go', name: 'Carhibou Go agent',
    hardware: 'Raspberry Pi and other Linux boards (ARMv6, ARMv7, ARM64, AMD64)',
    protocol_version: 2, setup_kind: 'command' as const, docs_url: 'https://carhibou.example/agent',
  },
  {
    id: 'custom', name: 'Custom agent',
    hardware: 'Any hardware supported by your implementation',
    protocol_version: 2, setup_kind: 'guided' as const, docs_url: '',
  },
]

/** The identity and compatibility fields every agent row now carries. */
export const agentIdentity = {
  implementation_id: 'carhibou.go', protocol_version: 2, agent_version: '0.1.0',
  compatibility: 'compatible' as const, vehicle_profile: null as string | null,
}

export const connectorKinds = [
  {
    id: 'teslamate.mqtt', name: 'TeslaMate (MQTT)',
    description: 'Subscribe to the MQTT broker TeslaMate publishes to.',
    docs_url: 'https://carhibou.example/connectors/teslamate',
  },
]

/** A connector row as GET /connectors returns it, password never included. */
export function connectorRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 'connector-1', vehicle_id: 'vehicle-1', name: 'Garage broker', kind: 'teslamate.mqtt',
    enabled: true, masked: '••••••••', mapping_profile: 'teslamate-mqtt-v1', config_version: 1, status: 'connected', last_connected_at: '2026-01-01T00:00:00Z',
    last_message_at: '2026-01-01T00:05:00Z', last_sample_at: '2026-01-01T00:05:00Z', last_error: '',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    config: {
      host: 'mqtt.local', port: 1883, tls: false, tls_accept_invalid_certs: false,
      username: 'carhibou', namespace: '', car_id: 1, sample_seconds: 10,
    },
    ...overrides,
  }
}

export const canProfile = {
  id: 'citroen-c-zero-v1', name: 'C-Zero', description: '', type: 'can' as const, built_in: true, editable: false,
  definition: { id: 'citroen-c-zero-v1', name: 'C-Zero', version: 1, type: 'can' as const, signals: [{ name: 'battery.soc', source: { type: 'can' as const, can_id: 884 }, decoder: { byte_offset: 0, data_type: 'uint8' as const } }] },
  created_at: null, updated_at: null,
}

export const mappingProfile = {
  id: 'teslamate-mqtt-v1', name: 'TeslaMate (MQTT)', description: 'Bundled mapping', type: 'mapping' as const, built_in: true, editable: false,
  definition: {
    id: 'teslamate-mqtt-v1', name: 'TeslaMate (MQTT)', version: 1, type: 'mapping' as const,
    passthrough_prefix: 'teslamate', ignore: ['latitude', 'longitude'],
    rules: [
      { match: 'battery_level', target: 'battery.soc' },
      { match: 'charging_state', target: 'charging.active', transform: { enum: { Charging: true, '*': false } } },
    ],
  },
  created_at: null, updated_at: null,
}

export function drive(overrides: Record<string, unknown> = {}) {
  return {
    start: '2026-08-27T08:00:00Z', end: '2026-08-27T08:40:00Z', duration_seconds: 2400,
    start_position: { latitude: 48.85, longitude: 2.35 }, end_position: { latitude: 48.87, longitude: 2.37 },
    distance_km: 24.4, avg_speed: 37, max_speed: 96, soc_start: 82, soc_end: 71, energy_kwh: 4.6, ...overrides,
  }
}

export function charge(overrides: Record<string, unknown> = {}) {
  return {
    start: '2026-08-27T19:00:00Z', end: '2026-08-27T21:00:00Z', duration_seconds: 7200,
    position: { latitude: 48.85, longitude: 2.35 },
    soc_start: 40, soc_end: 80, energy_kwh: 12.5, peak_power: 11.2, avg_power: 6.3, ...overrides,
  }
}

/** An agent row as GET /agents returns it. */
export function agentRow(overrides: Record<string, unknown> = {}) {
  return {
    id: 'agent-1', vehicle_id: vehicle.id, name: 'Pi', credential_version: 1, ...agentIdentity,
    hostname: 'pi', hardware: {}, sampling_seconds: 5, upload_seconds: 5,
    parked_sampling_seconds: 300, parked_upload_seconds: 300, online: true, last_seen_at: null,
    last_config_sync_at: null, config_version: 1, revoked_at: null, created_at: '2026-01-01T00:00:00Z',
    ...overrides,
  }
}

type Routes = Record<string, unknown | ((url: string, options?: RequestInit) => unknown)>

/**
 * Stubs fetch from a suffix-to-body map. Keys are matched by `endsWith` first and
 * `includes` second, so `/agents` beats `/agent-implementations` only when spelled
 * exactly; `default` answers anything unmatched.
 */
export function mockApi(routes: Routes) {
  const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
    const key = Object.keys(routes).find((route) => route !== 'default' && url.endsWith(route))
      ?? Object.keys(routes).find((route) => route !== 'default' && url.includes(route))
    const entry = key ? routes[key] : routes.default
    const body = typeof entry === 'function' ? (entry as (u: string, o?: RequestInit) => unknown)(url, options) : entry
    return Promise.resolve(body instanceof Response ? body : jsonResponse(body ?? []))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The labelled field inside `root`, by the text of its own span. */
export function field(wrapper: { findAll: (selector: string) => DOMWrapper<Element>[] }, root: string, label: string): DOMWrapper<Element> {
  const target = wrapper.findAll(`${root} .field`).find((item) => item.find('span').exists() && item.get('span').text() === label)
  if (!target) throw new Error(`no field labelled "${label}"`)
  return target
}

export function lastBody(fetchMock: Mock, method: string, fragment = ''): Record<string, unknown> {
  const call = fetchMock.mock.calls
    .filter((entry) => entry[1]?.method === method && String(entry[0]).includes(fragment))
    .at(-1)
  if (!call) throw new Error(`no ${method} call${fragment ? ` to ${fragment}` : ''}`)
  return JSON.parse(call[1]?.body as string)
}
