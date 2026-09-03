import { describe, expect, it } from 'vitest'
import { formatCoordinates, formatFixedNumber, formatNumber } from '../src/numberFormat'

describe('display number formatting', () => {
  it('rounds ordinary values to at most two decimal places', () => {
    expect(formatNumber(12.34567, 'en-US')).toBe('12.35')
    expect(formatNumber(12, 'en-US')).toBe('12')
  })

  it('uses the reader’s decimal separator', () => {
    expect(formatNumber(12.345, 'fr-FR')).toBe('12,35')
  })

  it('allows deliberate lower and fixed precision', () => {
    expect(formatNumber(12.56, 'en-US', { maximumFractionDigits: 0 })).toBe('13')
    expect(formatFixedNumber(12, 'en-US', 1)).toBe('12.0')
  })

  it('keeps the precision needed to identify a location', () => {
    expect(formatCoordinates(48.97750935, 1.99083135)).toBe('48.97751, 1.99083')
  })
})
