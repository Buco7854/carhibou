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
 * sample carrying position and tracker health serialises to about 350 bytes,
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
 * Two things shape them. A vehicle is parked for most of the month, so the
 * parked pair dominates the bill however fast the driving pair is. And uploading
 * as often as you sample doubles the cost for nothing, because each request
 * carries a fixed overhead that only disappears once samples are batched: at
 * one-second sampling, moving the upload from one second to five saves nearly
 * half the traffic, and past about thirty seconds there is almost nothing left
 * to save. So the upload interval is always the slower of the pair, and beyond
 * that point it buys freshness rather than data.
 */
export const CADENCE_PRESETS: CadencePreset[] = [
  { key: 'live', sampling_seconds: 1, upload_seconds: 5, parked_sampling_seconds: 15, parked_upload_seconds: 300 },
  { key: 'standard', sampling_seconds: 5, upload_seconds: 60, parked_sampling_seconds: 60, parked_upload_seconds: 900 },
  { key: 'saver', sampling_seconds: 15, upload_seconds: 900, parked_sampling_seconds: 600, parked_upload_seconds: 1800 },
  { key: 'minimal', sampling_seconds: 60, upload_seconds: 900, parked_sampling_seconds: 900, parked_upload_seconds: 3600 },
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
 * Bytes a tracker uploads over thirty days, split between driving and parked.
 *
 * The tracker is assumed to be powered the whole month, which is the honest
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
 * How far behind the server can be while the vehicle is driven.
 *
 * This is what a long upload interval actually costs, and it is worth showing
 * beside the data figure: past about thirty seconds the interval stops saving
 * data and only trades away freshness.
 */
export function drivingDelaySeconds(cadence: Cadence): number {
  return Math.max(0, cadence.upload_seconds)
}

export function formatDuration(seconds: number, locale: string): string {
  const format = (value: number, unit: Intl.RelativeTimeFormatUnit) =>
    new Intl.NumberFormat(locale, { maximumFractionDigits: value < 10 ? 1 : 0 }).format(value) +
    ' ' + new Intl.DisplayNames([locale], { type: 'dateTimeField' }).of(unit)
  if (seconds >= 3600) return format(seconds / 3600, 'hour')
  if (seconds >= 60) return format(seconds / 60, 'minute')
  return format(seconds, 'second')
}
