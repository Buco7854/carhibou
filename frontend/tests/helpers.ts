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
  vehicle_profile: 'citroen-c-zero-v1',
  timezone: 'UTC',
  color: '#65e0ad',
  icon: 'car',
  photo_url: null,
  access: 'operate' as const,
  state: {
    updated_at: new Date().toISOString(),
    online: true,
    position: { latitude: 48, longitude: 2, altitude: 20, speed: 42, heading: 90, accuracy: 5 },
    metrics: { 'battery.soc': 70, 'battery.power': -11.1 },
    agent: { mobile_signal: -82 },
  },
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
}

export const agentImplementations = [
  {
    id: 'carhibou.go', name: 'Carhibou Go agent',
    hardware: 'Raspberry Pi and other Linux boards (ARMv6, ARMv7, ARM64, AMD64)',
    protocol_version: 1, setup_kind: 'command' as const, docs_url: 'https://carhibou.example/agent',
  },
  {
    id: 'custom', name: 'Custom agent',
    hardware: 'Any hardware supported by your implementation',
    protocol_version: 1, setup_kind: 'guided' as const, docs_url: '',
  },
]

/** The identity and compatibility fields every agent row now carries. */
export const agentIdentity = {
  implementation_id: 'carhibou.go', protocol_version: 1, agent_version: '0.1.0',
  compatibility: 'compatible' as const,
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
    enabled: true, masked: '••••••••', config_version: 1, status: 'connected', last_connected_at: '2026-01-01T00:00:00Z',
    last_message_at: '2026-01-01T00:05:00Z', last_sample_at: '2026-01-01T00:05:00Z', last_error: '',
    created_at: '2026-01-01T00:00:00Z', updated_at: '2026-01-01T00:00:00Z',
    config: {
      host: 'mqtt.local', port: 1883, tls: false, tls_accept_invalid_certs: false,
      username: 'carhibou', namespace: '', car_id: 1, sample_seconds: 10,
    },
    ...overrides,
  }
}
