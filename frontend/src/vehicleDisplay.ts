import type { Vehicle } from './api/types'

export interface MetricDefinition {
  key: string
  labelKey: string
  unit: string
  icon: string
  decimals: number
  kind: 'number' | 'boolean' | 'text'
}

export interface MetricReading extends MetricDefinition {
  value: number | boolean | null
}

export interface EnergySummary extends MetricReading {
  value: number | null
  progress: number
}

const metricDefinitions: Record<string, MetricDefinition> = {
  'battery.soc': {
    key: 'battery.soc', labelKey: 'metrics.batterySoc', unit: '%', icon: 'battery', decimals: 0, kind: 'number',
  },
  'fuel.level': {
    key: 'fuel.level', labelKey: 'metrics.fuelLevel', unit: '%', icon: 'fuel', decimals: 0, kind: 'number',
  },
  'battery.power': {
    key: 'battery.power', labelKey: 'metrics.batteryPower', unit: 'kW', icon: 'charging', decimals: 1, kind: 'number',
  },
  'battery.current': {
    key: 'battery.current', labelKey: 'metrics.packCurrent', unit: 'A', icon: 'battery', decimals: 1, kind: 'number',
  },
  'vehicle.odometer': {
    key: 'vehicle.odometer', labelKey: 'metrics.odometer', unit: 'km', icon: 'vehicle', decimals: 0, kind: 'number',
  },
  'charging.voltage': {
    key: 'charging.voltage', labelKey: 'metrics.chargerVoltage', unit: 'V', icon: 'charging', decimals: 0, kind: 'number',
  },
  'charging.current': {
    key: 'charging.current', labelKey: 'metrics.chargerCurrent', unit: 'A', icon: 'charging', decimals: 1, kind: 'number',
  },
  'battery.pack_voltage': {
    key: 'battery.pack_voltage', labelKey: 'metrics.packVoltage', unit: 'V', icon: 'battery', decimals: 1, kind: 'number',
  },
  'vehicle.door_open': {
    key: 'vehicle.door_open', labelKey: 'metrics.doorOpen', unit: '', icon: 'vehicle', decimals: 0, kind: 'boolean',
  },
  'vehicle.lights': {
    key: 'vehicle.lights', labelKey: 'metrics.lights', unit: '', icon: 'vehicle', decimals: 0, kind: 'text',
  },
  'vehicle.high_beam': {
    key: 'vehicle.high_beam', labelKey: 'metrics.highBeam', unit: '', icon: 'vehicle', decimals: 0, kind: 'boolean',
  },
  'vehicle.handbrake': {
    key: 'vehicle.handbrake', labelKey: 'metrics.handbrake', unit: '', icon: 'vehicle', decimals: 0, kind: 'boolean',
  },
  'tyre.warning': {
    key: 'tyre.warning', labelKey: 'metrics.tyreWarning', unit: '', icon: 'vehicle', decimals: 0, kind: 'boolean',
  },
  'vehicle.state': {
    key: 'vehicle.state', labelKey: 'metrics.vehicleState', unit: '', icon: 'vehicle', decimals: 0, kind: 'text',
  },
  'vehicle.range': {
    key: 'vehicle.range', labelKey: 'metrics.range', unit: 'km', icon: 'energy', decimals: 0, kind: 'number',
  },
  'charging.active': {
    key: 'charging.active', labelKey: 'metrics.charging', unit: '', icon: 'charging', decimals: 0, kind: 'boolean',
  },
  'charging.power': {
    key: 'charging.power', labelKey: 'metrics.chargingPower', unit: 'kW', icon: 'charging', decimals: 1, kind: 'number',
  },
  'engine.rpm': {
    key: 'engine.rpm', labelKey: 'metrics.engineRpm', unit: 'rpm', icon: 'speed', decimals: 0, kind: 'number',
  },
  'engine.coolant_temperature': {
    key: 'engine.coolant_temperature', labelKey: 'metrics.coolantTemperature', unit: '°C', icon: 'temperature', decimals: 0, kind: 'number',
  },
  'engine.load': {
    key: 'engine.load', labelKey: 'metrics.engineLoad', unit: '%', icon: 'speed', decimals: 0, kind: 'number',
  },
  'engine.throttle': {
    key: 'engine.throttle', labelKey: 'metrics.throttle', unit: '%', icon: 'speed', decimals: 0, kind: 'number',
  },
  'engine.intake_temperature': {
    key: 'engine.intake_temperature', labelKey: 'metrics.intakeTemperature', unit: '°C', icon: 'temperature', decimals: 0, kind: 'number',
  },
  'engine.maf': {
    key: 'engine.maf', labelKey: 'metrics.massAirFlow', unit: 'g/s', icon: 'signal', decimals: 1, kind: 'number',
  },
  'vehicle.speed': {
    key: 'vehicle.speed', labelKey: 'metrics.vehicleSpeed', unit: 'km/h', icon: 'speed', decimals: 0, kind: 'number',
  },
  'agent.input_voltage': {
    key: 'agent.input_voltage', labelKey: 'metrics.inputVoltage', unit: 'V', icon: 'battery', decimals: 1, kind: 'number',
  },
}

const unknownEnergy: MetricDefinition = {
  key: '', labelKey: 'metrics.energyLevel', unit: '%', icon: 'energy', decimals: 0, kind: 'number',
}

const WHEELS: Array<{ key: string; labelKey: string }> = [
  { key: 'front_left', labelKey: 'frontLeft' },
  { key: 'front_right', labelKey: 'frontRight' },
  { key: 'rear_right', labelKey: 'rearRight' },
  { key: 'rear_left', labelKey: 'rearLeft' },
]
for (const wheel of WHEELS) {
  metricDefinitions[`tyre.${wheel.key}_pressure`] = {
    key: `tyre.${wheel.key}_pressure`, labelKey: `metrics.${wheel.labelKey}Pressure`, unit: 'bar', icon: 'vehicle', decimals: 2, kind: 'number',
  }
  metricDefinitions[`tyre.${wheel.key}_temperature`] = {
    key: `tyre.${wheel.key}_temperature`, labelKey: `metrics.${wheel.labelKey}Temperature`, unit: '°C', icon: 'temperature', decimals: 0, kind: 'number',
  }
}

/** Whether the agent is reporting. This is about the agent, not the vehicle. */
export type AgentStatus = 'online' | 'stale' | 'never'

/** What the vehicle is doing, as far as the last report knows. */
export type VehicleActivity = 'driving' | 'charging' | 'parked' | 'unknown'

export function agentStatus(vehicle: Vehicle | null | undefined): AgentStatus {
  if (!vehicle?.state) return 'never'
  return vehicle.state.online ? 'online' : 'stale'
}

/**
 * What the vehicle is doing.
 *
 * Deliberately separate from the agent's status, which had been standing in for
 * it: an agent that has stopped reporting was shown as a parked car, which is a
 * claim about the vehicle made from evidence about the agent. A car towed away
 * with its agent unplugged is not parked; nobody knows what it is.
 */
export function vehicleActivity(vehicle: Vehicle | null | undefined): VehicleActivity {
  const state = vehicle?.state
  if (!state || !state.online) return 'unknown'
  const declared = state.metrics['vehicle.state']
  if (typeof declared === 'string') {
    if (declared === 'charging') return 'charging'
    if (declared === 'ready' || declared === 'driving' || declared === 'on') return 'driving'
  }
  if (chargingState(vehicle).active) return 'charging'
  if (state.agent['vehicle_in_use'] === true) return 'driving'
  return 'parked'
}

export function metricDefinition(key: string): MetricDefinition {
  return metricDefinitions[key] ?? { key, labelKey: '', unit: '', icon: 'signal', decimals: 1, kind: 'number' }
}

export function metricNumber(vehicle: Vehicle | null | undefined, key: string): number | null {
  const value = key === 'vehicle.speed'
    ? vehicle?.state?.position?.speed ?? vehicle?.state?.metrics[key]
    : vehicle?.state?.metrics[key]
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function metricReading(vehicle: Vehicle | null | undefined, key: string): MetricReading {
  const definition = metricDefinition(key)
  const raw = vehicle?.state?.metrics[key]
  const value = definition.kind === 'boolean'
    ? (typeof raw === 'boolean' ? raw : null)
    : metricNumber(vehicle, key)
  return { ...definition, value }
}

export function energySummary(vehicle: Vehicle | null | undefined): EnergySummary {
  const metrics = vehicle?.state?.metrics ?? {}
  let definition = unknownEnergy
  if ('battery.soc' in metrics) definition = metricDefinition('battery.soc')
  else if ('fuel.level' in metrics) definition = metricDefinition('fuel.level')
  const value = definition.key ? metricNumber(vehicle, definition.key) : null
  return { ...definition, value, progress: value === null ? 0 : Math.min(100, Math.max(0, value)) }
}

/**
 * Metric keys ordered by how universally a vehicle reports them.
 *
 * GNSS speed comes from the agent itself, so it is the only reading present on
 * every vehicle. The engine group is standard OBD-II Mode 01 (SAE J1979) and is
 * answered by almost every car built to that standard. Fuel level is in the same
 * standard but is frequently unimplemented. The battery group needs a vehicle
 * profile, because no OBD-II PID exposes traction-battery state.
 *
 * Presentation walks this list and shows only what is actually reported, so a
 * vehicle is never advertised as having a reading its agent cannot produce.
 */
const conventionalOrder = [
  'vehicle.speed',
  'engine.rpm',
  'engine.coolant_temperature',
  'engine.load',
  'engine.throttle',
  'engine.intake_temperature',
  'engine.maf',
  'fuel.level',
  'agent.input_voltage',
  'battery.soc',
  'battery.pack_voltage',
  'battery.power',
  'charging.active',
]

function reportedReadings(vehicle: Vehicle | null | undefined, exclude: string[] = []): MetricReading[] {
  const reported = new Set(Object.keys(vehicle?.state?.metrics ?? {}))
  if (metricNumber(vehicle, 'vehicle.speed') !== null) reported.add('vehicle.speed')
  const ordered = conventionalOrder.filter((key) => reported.has(key) && !exclude.includes(key))
  const extra = [...reported].filter((key) => !conventionalOrder.includes(key) && !exclude.includes(key)).sort()
  return [...ordered, ...extra].map((key) => metricReading(vehicle, key)).filter((row) => row.value !== null)
}

export function secondaryReadings(vehicle: Vehicle | null | undefined): MetricReading[] {
  return reportedReadings(vehicle, ['vehicle.speed', energySummary(vehicle).key]).slice(0, 2)
}

/**
 * The one reading a vehicle card leads with.
 *
 * An energy level wins when present because a percentage bar is meaningful for it;
 * otherwise the most conventional reading the vehicle actually reports is promoted,
 * rather than leaving a permanently empty gauge on every car without a profile.
 */
export function headlineReading(vehicle: Vehicle | null | undefined): EnergySummary | MetricReading | null {
  const energy = energySummary(vehicle)
  if (energy.value !== null) return energy
  return reportedReadings(vehicle, ['vehicle.speed'])[0] ?? null
}

export function isPercentage(reading: MetricReading): boolean {
  return reading.unit === '%' && typeof reading.value === 'number'
}

export interface ChargingState {
  /** Null when the vehicle reports nothing the state can be derived from. */
  active: boolean | null
  /** Charge rate in kW while charging, null when unknown. */
  power: number | null
}

/**
 * Whether the pack is taking charge, and how fast.
 *
 * No OBD-II PID reports charging directly, so an explicit `charging.active` from a
 * vehicle profile wins when present. Otherwise it is derived from battery power under
 * the convention this application applies everywhere: `battery.power` is positive while
 * the pack delivers energy and negative while it absorbs it.
 */
export function chargingState(vehicle: Vehicle | null | undefined): ChargingState {
  const metrics = vehicle?.state?.metrics ?? {}
  const declared = metrics['charging.active']
  const rate = metricNumber(vehicle, 'charging.power')
  const power = metricNumber(vehicle, 'battery.power')
  if (typeof declared === 'boolean') {
    return { active: declared, power: declared ? rate ?? (power === null ? null : Math.abs(power)) : null }
  }
  if (power === null) return { active: null, power: rate }
  return { active: power < 0, power: power < 0 ? rate ?? Math.abs(power) : null }
}

export function preferredHistoryMetric(vehicle: Vehicle | null | undefined, available: string[], hasSpeed: boolean): string {
  void vehicle
  const candidates = ['battery.soc', 'fuel.level', 'vehicle.speed', 'engine.rpm', 'battery.power', 'battery.pack_voltage', 'engine.coolant_temperature', 'engine.load']
  const options = new Set(available)
  if (hasSpeed) options.add('vehicle.speed')
  return candidates.find((key) => options.has(key)) ?? available[0] ?? candidates[0] ?? 'vehicle.speed'
}

export function defaultDashboardMetrics(vehicle: Vehicle | null | undefined): string[] {
  const available = Object.keys(vehicle?.state?.metrics ?? {})
  const hasSpeed = metricNumber(vehicle, 'vehicle.speed') !== null
  const primary = preferredHistoryMetric(vehicle, available, hasSpeed)
  const defaults = ['battery.soc', 'fuel.level', 'engine.rpm', 'battery.power', 'vehicle.speed']
  if (!available.length && !hasSpeed) return ['vehicle.speed']
  const options = new Set(available)
  if (hasSpeed) options.add('vehicle.speed')
  return [...new Set([primary, ...defaults])].filter((key) => options.has(key)).slice(0, 2)
}

export function formatMetricNumber(value: number, definition: MetricDefinition): string {
  return definition.decimals === 0 ? String(Math.round(value)) : value.toFixed(definition.decimals)
}

export function metricLabel(definition: MetricDefinition, translate: (key: string) => string): string {
  return definition.labelKey ? translate(definition.labelKey) : definition.key
}
