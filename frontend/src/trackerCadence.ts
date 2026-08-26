/** Cadence presets and the mobile-data cost of running one for a month. */

export interface CadencePreset {
  key: string
  samplingSeconds: number
  uploadSeconds: number
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

export const CADENCE_PRESETS: CadencePreset[] = [
  { key: 'live', samplingSeconds: 1, uploadSeconds: 10 },
  { key: 'standard', samplingSeconds: 5, uploadSeconds: 60 },
  { key: 'saver', samplingSeconds: 60, uploadSeconds: 600 },
  { key: 'minimal', samplingSeconds: 300, uploadSeconds: 3600 },
]

/**
 * Bytes a tracker uploads over thirty days of continuous operation.
 *
 * Continuous is the honest assumption to show: a tracker on permanent power
 * samples whether or not the vehicle moves, and a figure that quietly assumed
 * otherwise would understate the bill it is there to prevent.
 */
export function monthlyUploadBytes(
  samplingSeconds: number,
  uploadSeconds: number,
  signalCount = 0,
): number {
  if (!(samplingSeconds > 0) || !(uploadSeconds > 0)) return 0
  const samples = SECONDS_PER_MONTH / samplingSeconds
  const perRequest = Math.min(MAX_SAMPLES_PER_REQUEST, Math.max(1, uploadSeconds / samplingSeconds))
  const sampleCost = BYTES_PER_SAMPLE + signalCount * BYTES_PER_SIGNAL + BYTES_PER_ACKNOWLEDGEMENT
  return samples * sampleCost + (samples / perRequest) * BYTES_PER_REQUEST
}

export function formatDataVolume(bytes: number, locale: string): string {
  const megabytes = bytes / 1_000_000
  if (megabytes >= 1000) {
    return `${new Intl.NumberFormat(locale, { maximumFractionDigits: 1 }).format(megabytes / 1000)} GB`
  }
  const digits = megabytes < 10 ? 1 : 0
  return `${new Intl.NumberFormat(locale, { maximumFractionDigits: digits }).format(megabytes)} MB`
}
