import type { Vehicle } from './api/types'

export type PropulsionFamily = 'electric' | 'hybrid' | 'thermal' | 'unknown'

export interface MetricDefinition {
  key: string
  labelKey: string
  unit: string
  icon: string
  decimals: number
  kind: 'number' | 'boolean'
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
  'battery.pack_voltage': {
    key: 'battery.pack_voltage', labelKey: 'metrics.packVoltage', unit: 'V', icon: 'battery', decimals: 1, kind: 'number',
  },
  'charging.active': {
    key: 'charging.active', labelKey: 'metrics.charging', unit: '', icon: 'charging', decimals: 0, kind: 'boolean',
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
  'device.input_voltage': {
    key: 'device.input_voltage', labelKey: 'metrics.inputVoltage', unit: 'V', icon: 'battery', decimals: 1, kind: 'number',
  },
}

const unknownEnergy: MetricDefinition = {
  key: '', labelKey: 'metrics.energyLevel', unit: '%', icon: 'energy', decimals: 0, kind: 'number',
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

export function propulsionFamily(vehicle: Vehicle | null | undefined): PropulsionFamily {
  if (vehicle?.propulsion_type === 'electric') return 'electric'
  if (vehicle?.propulsion_type === 'hybrid') return 'hybrid'
  if (vehicle?.propulsion_type === 'petrol' || vehicle?.propulsion_type === 'diesel') return 'thermal'
  if (metricNumber(vehicle, 'battery.soc') !== null || metricNumber(vehicle, 'battery.power') !== null) return 'electric'
  if (metricNumber(vehicle, 'fuel.level') !== null || metricNumber(vehicle, 'engine.rpm') !== null) return 'thermal'
  return 'unknown'
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
  const family = propulsionFamily(vehicle)
  let definition = unknownEnergy
  if (family === 'electric') definition = metricDefinition('battery.soc')
  else if (family === 'thermal') definition = metricDefinition('fuel.level')
  else if (family === 'hybrid') {
    definition = metricNumber(vehicle, 'battery.soc') !== null || metricNumber(vehicle, 'fuel.level') === null
      ? metricDefinition('battery.soc')
      : metricDefinition('fuel.level')
  }
  const value = definition.key ? metricNumber(vehicle, definition.key) : null
  return { ...definition, value, progress: value === null ? 0 : Math.min(100, Math.max(0, value)) }
}

export function secondaryReadings(vehicle: Vehicle | null | undefined): MetricReading[] {
  const family = propulsionFamily(vehicle)
  const candidates = family === 'electric'
    ? ['battery.power', 'charging.active', 'battery.pack_voltage']
    : family === 'thermal'
      ? ['engine.rpm', 'engine.coolant_temperature', 'engine.load', 'engine.throttle']
      : family === 'hybrid'
        ? ['engine.rpm', 'battery.power', 'fuel.level', 'charging.active', 'engine.coolant_temperature']
        : ['engine.rpm', 'battery.power', 'engine.coolant_temperature', 'battery.pack_voltage']
  const primaryEnergyKey = energySummary(vehicle).key
  const readings = candidates.filter((key) => key !== primaryEnergyKey).map((key) => metricReading(vehicle, key))
  const available = readings.filter((row) => row.value !== null)
  const missing = readings.filter((row) => row.value === null)
  return [...available, ...missing].slice(0, 2)
}

export function preferredHistoryMetric(vehicle: Vehicle | null | undefined, available: string[], hasSpeed: boolean): string {
  const family = propulsionFamily(vehicle)
  const candidates = family === 'electric'
    ? ['battery.soc', 'battery.power', 'battery.pack_voltage', 'vehicle.speed']
    : family === 'thermal'
      ? ['fuel.level', 'engine.rpm', 'engine.coolant_temperature', 'engine.load', 'vehicle.speed']
      : family === 'hybrid'
        ? ['battery.soc', 'fuel.level', 'battery.power', 'engine.rpm', 'engine.coolant_temperature', 'vehicle.speed']
        : ['battery.soc', 'fuel.level', 'vehicle.speed', 'engine.rpm', 'battery.power']
  const options = new Set(available)
  if (hasSpeed) options.add('vehicle.speed')
  return candidates.find((key) => options.has(key)) ?? available[0] ?? candidates[0] ?? 'vehicle.speed'
}

export function defaultDashboardMetrics(vehicle: Vehicle | null | undefined): string[] {
  const available = Object.keys(vehicle?.state?.metrics ?? {})
  const hasSpeed = metricNumber(vehicle, 'vehicle.speed') !== null
  const primary = preferredHistoryMetric(vehicle, available, hasSpeed)
  const family = propulsionFamily(vehicle)
  const defaults = family === 'electric'
    ? ['battery.soc', 'battery.power']
    : family === 'thermal'
      ? ['fuel.level', 'engine.rpm']
      : family === 'hybrid'
        ? ['battery.soc', 'fuel.level', 'engine.rpm']
        : ['vehicle.speed']
  if (!available.length && !hasSpeed) return defaults
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
