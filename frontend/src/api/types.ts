export interface Position {
  latitude: number
  longitude: number
  altitude: number | null
  speed: number | null
  heading: number | null
  accuracy: number | null
}

export interface VehicleState {
  updated_at: string
  online: boolean
  position: Position | null
  metrics: Record<string, unknown>
  device: Record<string, unknown>
}

export interface Vehicle {
  id: string
  name: string
  manufacturer: string
  model: string
  year: number | null
  battery_nominal_capacity_kwh: number | null
  vehicle_profile: string | null
  timezone: string
  color: string
  icon: string
  photo_url: string | null
  state: VehicleState | null
  created_at: string
  updated_at: string
}

export type ProfileDataType = 'uint8' | 'uint16' | 'uint32' | 'int8' | 'int16' | 'int32' | 'bytes' | 'boolean'
export interface VehicleProfileSignal {
  name: string
  display_name?: string
  source: { type: 'can'; can_id: number }
  decoder: {
    byte_offset: number
    data_type: ProfileDataType
    endianness?: 'big' | 'little'
    scale?: number
    offset?: number
    length?: number | null
    bit?: number | null
  }
  unit?: string | null
  minimum?: number | null
  maximum?: number | null
}

export interface VehicleProfile {
  id: string
  name: string
  description: string
  built_in: boolean
  definition: {
    id: string
    name: string
    version: number
    description?: string
    signals: VehicleProfileSignal[]
    computed_metrics?: Array<Record<string, unknown>>
  }
  created_at: string | null
  updated_at: string | null
}

export interface User {
  id: string
  email: string
  display_name: string
  permissions: Record<string, boolean>
}

export interface HistoryPoint {
  id: string
  recorded_at: string
  latitude: number | null
  longitude: number | null
  speed: number | null
  heading: number | null
  metrics: Record<string, unknown>
}

export interface History {
  vehicle_id: string
  start: string
  end: string
  available_metrics: string[]
  original_count: number
  points: HistoryPoint[]
}

export interface HistoryEntry {
  id: string
  recorded_at: string
  sequence: number
  latitude: number | null
  longitude: number | null
  altitude: number | null
  speed: number | null
  heading: number | null
  accuracy: number | null
  metrics: Record<string, unknown>
  device: Record<string, unknown>
}

export interface HistoryEntries {
  vehicle_id: string
  start: string
  end: string
  total: number
  limit: number
  offset: number
  metric_keys: string[]
  device_keys: string[]
  entries: HistoryEntry[]
}

export interface DashboardWidget {
  id: string
  type: string
  vehicle_id?: string
  metric?: string
  metrics?: string[]
  title?: string
  unit?: string
  time_range_days?: number
  settings?: Record<string, unknown>
  x: number
  y: number
  w: number
  h: number
}

export interface Dashboard {
  id: string
  name: string
  is_default: boolean
  layout: { widgets: DashboardWidget[]; preset?: string }
  created_at: string
  updated_at: string
}

export interface HookExecution {
  id: string
  hook_id: string
  trigger_id: string
  telemetry_id: string | null
  dry_run: boolean
  status: string
  started_at: string | null
  finished_at: string | null
  duration_seconds: number | null
  logs: Array<Record<string, unknown>>
  error: string | null
  created_at: string
}

export interface Hook {
  id: string
  name: string
  description: string
  enabled: boolean
  trigger_type: string
  vehicle_id: string | null
  source: string
  timeout_seconds: number
  revision: number
  created_at: string
  updated_at: string
}

export interface HookRevision {
  id: string
  revision: number
  source: string
  created_by: string
  created_at: string
}

export interface Diagnostics {
  version: string
  database: string
  pending_jobs: number
  failed_jobs: number
  hook_failures: number
  stale_devices: number
  workers: Array<{ id: string; version: string; seen_at: string }>
}

export interface BrowserSession {
  id: string
  created_at: string
  last_seen_at: string
  expires_at: string
  current: boolean
  ip_address: string | null
  user_agent: string | null
}

export interface UserAccount {
  id: string
  email: string
  display_name: string
  is_active: boolean
  is_admin: boolean
  created_at: string
}
