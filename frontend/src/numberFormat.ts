export interface NumberFormatOptions {
  minimumFractionDigits?: number
  maximumFractionDigits?: number
  useGrouping?: boolean
}

/**
 * One formatter for measurements shown to people.
 *
 * Ordinary values use no more than two decimal places. Callers may ask for a
 * lower semantic precision (whole percentages, tenths of a kilowatt) or the
 * higher precision coordinates genuinely need. Inputs and machine-readable
 * values deliberately do not use this function.
 */
export function formatNumber(
  value: number,
  locale?: string,
  options: NumberFormatOptions = {},
): string {
  if (!Number.isFinite(value)) return '—'
  const maximumFractionDigits = Math.max(0, Math.min(20, options.maximumFractionDigits ?? 2))
  const minimumFractionDigits = Math.max(
    0,
    Math.min(maximumFractionDigits, options.minimumFractionDigits ?? 0),
  )
  return new Intl.NumberFormat(locale, {
    minimumFractionDigits,
    maximumFractionDigits,
    useGrouping: options.useGrouping ?? true,
  }).format(value)
}

/** A measurement whose declared precision should remain visible. */
export function formatFixedNumber(value: number, locale: string | undefined, fractionDigits: number): string {
  return formatNumber(value, locale, {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  })
}

/** Coordinates retain five decimals and use a stable separator. */
export function formatCoordinates(latitude: number, longitude: number): string {
  return `${latitude.toFixed(5)}, ${longitude.toFixed(5)}`
}
