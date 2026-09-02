/** How a source obtained a value, as opposed to which source it was. */
export type ReadingChannel = 'can' | 'obd' | 'gnss' | 'mqtt' | 'derived'

/** Whether the value was observed as such, or computed from other observations. */
export type ReadingMethod = 'direct' | 'derived'

export type SourceKind = 'agent' | 'connector'

/**
 * Which source a resolved value came from, and whether it still counts.
 *
 * Source identity and acquisition channel are separate facts: one agent may
 * report the same metric over CAN and over GNSS, and the server picks between
 * them. `fresh` is the server's verdict on the candidate's age; the client never
 * recomputes it, because expiry is evaluated when state is read and only the
 * server knows each metric's freshness policy.
 */
export interface Provenance {
  observed_at: string
  source_id: string
  source_kind: SourceKind
  channel: ReadingChannel
  method: ReadingMethod
  fresh: boolean
}

/** One resolved metric: the server's choice among competing candidates. */
export interface Reading<T = unknown> extends Provenance {
  value: T
}

export interface PositionFix {
  latitude: number
  longitude: number
  altitude: number | null
  speed: number | null
  heading: number | null
  accuracy: number | null
}

/**
 * The resolved fix. Provenance applies to the whole fix rather than to each
 * field, because a position is observed atomically.
 */
export interface ResolvedPosition extends Provenance, PositionFix {}

export interface VehicleState {
  updated_at: string
  online: boolean
  position: ResolvedPosition | null
  /**
   * Every metric the server resolved for this vehicle, canonical and namespaced
   * alike. A key that is absent has no evidence behind it, which is not the same
   * as a value of zero or false.
   */
  readings: Record<string, Reading>
  agent: Record<string, unknown>
}

export type VehicleAccessLevel = 'view' | 'operate'

export interface Vehicle {
  id: string
  name: string
  manufacturer: string
  model: string
  year: number | null
  battery_nominal_capacity_kwh: number | null
  timezone: string
  color: string
  icon: string
  photo_url: string | null
  state: VehicleState | null
  access: VehicleAccessLevel
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

export type ProfileType = 'can' | 'mapping'

/** `boolean` and `json` are flags, not values; `enum` takes "*" as its default. */
export interface MappingTransform {
  scale?: number
  offset?: number
  enum?: Record<string, string | number | boolean>
  boolean?: boolean
  json?: boolean
}

export interface MappingRule {
  match: string
  target: string
  transform?: MappingTransform
}

export interface ProfileDefinition {
  id: string
  name: string
  version: number
  description?: string
  type?: ProfileType
  /** CAN profiles only. */
  signals?: VehicleProfileSignal[]
  computed_metrics?: Array<Record<string, unknown>>
  /** Mapping profiles only. */
  passthrough_prefix?: string
  ignore?: string[]
  rules?: MappingRule[]
}

export interface VehicleProfile {
  id: string
  name: string
  description: string
  type: ProfileType
  built_in: boolean
  editable: boolean
  definition: ProfileDefinition
  created_at: string | null
  updated_at: string | null
}

export interface SegmentPosition {
  latitude: number
  longitude: number
}

interface SegmentBase {
  start: string
  end: string
  duration_seconds: number
  soc_start?: number
  soc_end?: number
  energy_kwh?: number
}

export interface DriveSegment extends SegmentBase {
  start_position?: SegmentPosition
  end_position?: SegmentPosition
  distance_km?: number
  avg_speed?: number
  max_speed?: number
}

export interface ChargeSegment extends SegmentBase {
  position?: SegmentPosition
  peak_power?: number
  avg_power?: number
}

export interface Segments {
  drives: DriveSegment[]
  charges: ChargeSegment[]
}

export type SegmentKind = 'drive' | 'charge'
/** The API returns no segment id, so the kind and start instant identify one. */
export type SelectedSegment = { kind: SegmentKind; start: string; end: string }

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
  agent: Record<string, unknown>
}

export interface HistoryEntries {
  vehicle_id: string
  start: string
  end: string
  total: number
  limit: number
  offset: number
  metric_keys: string[]
  agent_keys: string[]
  entries: HistoryEntry[]
}

/** One observation exactly as a source reported it, with where it came from. */
export interface RecordedObservation extends Omit<Provenance, 'fresh'> {
  key: string
  value: unknown
}

export interface RecordedPosition extends Omit<Provenance, 'fresh'> {
  value: PositionFix
}

/**
 * One uploaded sample, unresolved.
 *
 * `recorded_at` is when the source says it took the reading and `received_at` is
 * when the server got it, so the two together are the upload lag. A sample is an
 * envelope: its observations each carry their own channel and instant, which is
 * how a Pi reading CAN and a broker relaying MQTT stay distinguishable.
 */
export interface HistoryObservationSample {
  id: string
  sequence: number
  recorded_at: string
  received_at: string
  source_id: string
  source_kind: SourceKind
  reporting_interval: number | null
  event_driven: boolean
  position: RecordedPosition | null
  observations: RecordedObservation[]
  agent: Record<string, unknown>
}

export interface HistoryObservations {
  vehicle_id: string
  start: string
  end: string
  total: number
  limit: number
  offset: number
  samples: HistoryObservationSample[]
}

/**
 * One row of the snapshot table: the whole car as of `bucket_end`.
 *
 * The server forward-fills, so a reading whose `observed_at` predates
 * `bucket_start` was carried rather than measured in this bucket. It also
 * collapses consecutive identical rows and reports how many buckets one row
 * stands for, which is what keeps a quiet night cheap to ask for.
 */
export interface HistoryTableRow {
  bucket_start: string
  bucket_end: string
  collapsed_buckets: number
  reports: number
  readings: Record<string, Reading>
  position: ResolvedPosition | null
  agent: Record<string, unknown>
}

export interface HistoryTable {
  vehicle_id: string
  start: string
  end: string
  step_seconds: number
  total: number
  limit: number
  offset: number
  rows: HistoryTableRow[]
}

export interface DashboardWidget {
  id: string
  type: string
  vehicle_id?: string
  metric?: string
  metrics?: string[]
  x_metric?: string
  y_metric?: string
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
  stale_agents: number
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
  can_create_profiles: boolean
  created_at: string
}

export interface VehicleGrant {
  user_id: string
  email: string
  display_name: string
  level: VehicleAccessLevel
}

export interface DefaultAccessGrant {
  vehicle_id: string
  level: VehicleAccessLevel
}

export interface DefaultAccess {
  profiles_create: boolean
  grants: DefaultAccessGrant[]
}

export interface AuthMethods {
  password: boolean
  oidc: { enabled: boolean; name: string }
}

/**
 * One canonical metric key, as published by the server so that hook and profile
 * authors do not have to read the registry source or guess a name and land in
 * the namespaced extension space where nothing understands it.
 */
export interface MetricRegistryEntry {
  key: string
  unit: string | null
  meaning: string
  kind: string
  value_type: string
  retained: boolean
  freshness_seconds: number
}

/**
 * A fix is one observation rather than six metrics, so the registry describes it
 * separately. Optional because a server that predates the descriptor answers
 * without it, and the reference then says nothing rather than inventing a copy.
 */
export interface PositionFieldDescriptor {
  key: string
  unit: string
  meaning: string
}

export interface PositionDescriptor {
  meaning: string
  fields: PositionFieldDescriptor[]
}

export interface MetricRegistry {
  metrics: MetricRegistryEntry[]
  position?: PositionDescriptor
}
