/** Cadence presets and the mobile-data cost of running one for a month. */

export interface Cadence {
  sampling_seconds: number
  upload_seconds: number
  parked_sampling_seconds: number
  parked_upload_seconds: number
}

export interface CadencePreset extends Cadence {
  key: string
}

/**
 * Sizes measured from the agent's own upload payload rather than guessed: one
 * sample carrying position and agent health serialises to about 350 bytes,
 * and each decoded profile signal adds roughly 25 more. A request costs its
 * JSON envelope, HTTP headers, and the server's acknowledgement of every sample
 * ID it carried, which is a UUID each.
 */
const BYTES_PER_SAMPLE = 350
const BYTES_PER_SIGNAL = 25
const BYTES_PER_ACKNOWLEDGEMENT = 40
const BYTES_PER_REQUEST = 800

/** The agent drains at most this many samples per request. */
const MAX_SAMPLES_PER_REQUEST = 500
const SECONDS_PER_MONTH = 30 * 24 * 60 * 60

/**
 * Starting points, not a menu: every field stays editable.
 *
 * Each preset uploads exactly as often as it samples, because the point of the
 * data is to watch it change. A sample sitting in the queue is a reading nobody
 * can see, and matching the two intervals is the only setting that adds no lag
 * at all: the dashboard is then as current as the data itself allows.
 *
 * Saving data therefore means lowering the resolution, not delaying it. That is
 * a real compromise — fewer readings — but it is the one that keeps what does
 * arrive worth looking at. The parked pair is where most of it is found, because
 * a vehicle is parked for the great majority of the month.
 */
export const CADENCE_PRESETS: CadencePreset[] = [
  { key: 'live', sampling_seconds: 1, upload_seconds: 1, parked_sampling_seconds: 30, parked_upload_seconds: 30 },
  { key: 'standard', sampling_seconds: 5, upload_seconds: 5, parked_sampling_seconds: 300, parked_upload_seconds: 300 },
  { key: 'saver', sampling_seconds: 15, upload_seconds: 15, parked_sampling_seconds: 600, parked_upload_seconds: 600 },
  { key: 'frugal', sampling_seconds: 45, upload_seconds: 45, parked_sampling_seconds: 900, parked_upload_seconds: 900 },
  { key: 'minimal', sampling_seconds: 180, upload_seconds: 180, parked_sampling_seconds: 3600, parked_upload_seconds: 3600 },
]

/** Hours a day the vehicle is in use, which the estimate is weighted by. */
export const DEFAULT_DRIVING_HOURS = 1

function windowBytes(
  seconds: number,
  samplingSeconds: number,
  uploadSeconds: number,
  signalCount: number,
): number {
  if (!(samplingSeconds > 0) || !(uploadSeconds > 0)) return 0
  const samples = seconds / samplingSeconds
  const perRequest = Math.min(MAX_SAMPLES_PER_REQUEST, Math.max(1, uploadSeconds / samplingSeconds))
  const sampleCost = BYTES_PER_SAMPLE + signalCount * BYTES_PER_SIGNAL + BYTES_PER_ACKNOWLEDGEMENT
  return samples * sampleCost + (samples / perRequest) * BYTES_PER_REQUEST
}

/**
 * Bytes an agent uploads over thirty days, split between driving and parked.
 *
 * The agent is assumed to be powered the whole month, which is the honest
 * assumption for hardware on permanent power: it samples at its parked cadence
 * whether or not the vehicle moves, and that is most of the bill. Only the hours
 * actually spent driving are charged at the driving cadence.
 */
export function monthlyUploadBytes(
  cadence: Cadence,
  signalCount = 0,
  drivingHoursPerDay = DEFAULT_DRIVING_HOURS,
): number {
  const drivingSeconds = Math.min(24, Math.max(0, drivingHoursPerDay)) * 60 * 60 * 30
  const parkedSeconds = SECONDS_PER_MONTH - drivingSeconds
  return (
    windowBytes(drivingSeconds, cadence.sampling_seconds, cadence.upload_seconds, signalCount) +
    windowBytes(
      parkedSeconds,
      cadence.parked_sampling_seconds,
      cadence.parked_upload_seconds,
      signalCount,
    )
  )
}

export function formatDataVolume(bytes: number, locale: string): string {
  const megabytes = bytes / 1_000_000
  if (megabytes >= 1000) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(megabytes / 1000)} GB`
  }
  const digits = megabytes < 10 ? 1 : 0
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(megabytes)} MB`
}

/**
 * How far behind the dashboard runs while the vehicle is driven.
 *
 * A reading cannot appear before it is taken, so this is the sample interval
 * plus whatever the upload interval delays it beyond that. Uploading exactly as
 * often as sampling adds nothing, which is what every preset does.
 */
export function drivingDelaySeconds(cadence: Cadence): number {
  return Math.max(0, cadence.sampling_seconds) + Math.max(0, cadence.upload_seconds - cadence.sampling_seconds)
}

export function formatDuration(seconds: number, locale: string): string {
  const format = (value: number, unit: Intl.RelativeTimeFormatUnit) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: value < 10 ? 1 : 0 }).format(value) +
    ' ' + new Intl.DisplayNames([locale], { type: 'dateTimeField' }).of(unit)
  if (seconds >= 3600) return format(seconds / 3600, 'hour')
  if (seconds >= 60) return format(seconds / 60, 'minute')
  return format(seconds, 'second')
}
