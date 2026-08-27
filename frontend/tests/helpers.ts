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
    device: { mobile_signal: -82 },
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

/** The identity and compatibility fields every device row now carries. */
export const deviceIdentity = {
  implementation_id: 'carhibou.go', protocol_version: 1, agent_version: '0.1.0',
  compatibility: 'compatible' as const,
}
