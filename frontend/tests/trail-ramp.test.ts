import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'
import { TRAIL_BAND_COUNT } from '../src/mapSpeedScale'

/**
 * The speed ramp, measured rather than admired.
 *
 * Two single-hue ramps were tried before this one. The first measured 8.5
 * ΔE2000 between neighbouring bands, the second 18.8, and a reader on a phone
 * could separate neither: at two pixels wide a line has very little lightness
 * channel to spend. This one spends hue instead — a cold-to-hot sweep — and the
 * numbers are the test, because a screenshot cannot catch the separation
 * shrinking again.
 *
 * The trail is stroked over its own dark casing rather than over the
 * cartography, so the casing is what each band has to clear, and the casing is
 * what has to clear the pale basemap. The grounds are the two basemaps the trail
 * is drawn on: OpenFreeMap's light cartographies land at about #f7f4f0 and the
 * dark ones at about #141414.
 */
const LIGHT_GROUND = '#f7f4f0'
const DARK_GROUND = '#141414'
const MIN_ADJACENT_DELTA_E = 30
const MIN_HUE_GAP = 45
const MIN_CONTRAST = 3

const source = readFileSync('src/components/VehicleMap.vue', 'utf8')

/** A custom property's declared value, from the frame's own block. */
function token(name: string): string {
  const match = new RegExp(`--${name}:\\s*(#[0-9a-f]{6})`).exec(source)
  if (!match) throw new Error(`no --${name} declared`)
  return match[1]!
}

/** The ramp as declared, slowest band first. */
function ramp(): string[] {
  return Array.from({ length: TRAIL_BAND_COUNT }, (_, index) => token(`trail-${index + 1}`))
}

function channels(hex: string): [number, number, number] {
  const value = hex.replace('#', '')
  return [0, 2, 4].map((at) => parseInt(value.slice(at, at + 2), 16) / 255) as [number, number, number]
}

function linear(channel: number): number {
  return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
}

/** CIE XYZ under D65, the space both of the measures below are defined in. */
function xyz(hex: string): [number, number, number] {
  const [r, g, b] = channels(hex).map(linear) as [number, number, number]
  return [
    0.4124564 * r + 0.3575761 * g + 0.1804375 * b,
    0.2126729 * r + 0.7151522 * g + 0.0721750 * b,
    0.0193339 * r + 0.1191920 * g + 0.9503041 * b,
  ]
}

/** WCAG 2 relative-luminance contrast, as SC 1.4.11 measures a graphical object. */
function contrast(left: string, right: string): number {
  const [lighter, darker] = [xyz(left)[1], xyz(right)[1]].sort((one, two) => two - one)
  return (lighter! + 0.05) / (darker! + 0.05)
}

function lab(hex: string): [number, number, number] {
  const white = [0.95047, 1, 1.08883]
  const f = (value: number) => (value > 216 / 24389 ? Math.cbrt(value) : ((24389 / 27) * value + 16) / 116)
  const [fx, fy, fz] = xyz(hex).map((value, axis) => f(value / white[axis]!)) as [number, number, number]
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)]
}

/** CIEDE2000, in Sharma, Wu and Dalal's formulation of CIE 142:2001. */
function deltaE2000(left: string, right: string): number {
  const [l1, a1, b1] = lab(left)
  const [l2, a2, b2] = lab(right)
  const c1 = Math.hypot(a1, b1)
  const c2 = Math.hypot(a2, b2)
  const meanC = (c1 + c2) / 2
  const g = 0.5 * (1 - Math.sqrt(meanC ** 7 / (meanC ** 7 + 25 ** 7)))
  const a1p = (1 + g) * a1
  const a2p = (1 + g) * a2
  const c1p = Math.hypot(a1p, b1)
  const c2p = Math.hypot(a2p, b2)
  const degrees = (radians: number) => (radians * 180) / Math.PI
  const h1p = (degrees(Math.atan2(b1, a1p)) + 360) % 360
  const h2p = (degrees(Math.atan2(b2, a2p)) + 360) % 360
  let deltaHueDegrees = 0
  if (c1p * c2p !== 0) {
    deltaHueDegrees = h2p - h1p
    if (deltaHueDegrees > 180) deltaHueDegrees -= 360
    else if (deltaHueDegrees < -180) deltaHueDegrees += 360
  }
  const deltaH = 2 * Math.sqrt(c1p * c2p) * Math.sin((deltaHueDegrees * Math.PI) / 360)
  const meanL = (l1 + l2) / 2
  const meanCp = (c1p + c2p) / 2
  let meanHp = h1p + h2p
  if (c1p * c2p !== 0) meanHp = Math.abs(h1p - h2p) > 180 ? (h1p + h2p + 360) / 2 : (h1p + h2p) / 2
  const t = 1
    - 0.17 * Math.cos(((meanHp - 30) * Math.PI) / 180)
    + 0.24 * Math.cos((2 * meanHp * Math.PI) / 180)
    + 0.32 * Math.cos(((3 * meanHp + 6) * Math.PI) / 180)
    - 0.20 * Math.cos(((4 * meanHp - 63) * Math.PI) / 180)
  const sl = 1 + (0.015 * (meanL - 50) ** 2) / Math.sqrt(20 + (meanL - 50) ** 2)
  const sc = 1 + 0.045 * meanCp
  const sh = 1 + 0.015 * meanCp * t
  const rt = -Math.sin((2 * 30 * Math.exp(-(((meanHp - 275) / 25) ** 2)) * Math.PI) / 180)
    * 2 * Math.sqrt(meanCp ** 7 / (meanCp ** 7 + 25 ** 7))
  const dl = (l2 - l1) / sl
  const dc = (c2p - c1p) / sc
  const dh = deltaH / sh
  return Math.sqrt(dl ** 2 + dc ** 2 + dh ** 2 + rt * dc * dh)
}

const RAMP = ramp()
const CASING = token('trail-casing')

/** OKLCH hue in degrees, which is the channel this ramp encodes order in. */
function hue(hex: string): number {
  const [r, g, b] = channels(hex).map(linear) as [number, number, number]
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b)
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b)
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b)
  const a = 1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s
  const b2 = 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s
  return ((Math.atan2(b2, a) * 180) / Math.PI + 360) % 360
}

describe('the speed trail ramp', () => {
  it('steps every band clear of its neighbour', () => {
    const gaps = RAMP.slice(1).map((hex, index) => deltaE2000(hex, RAMP[index]!))
    for (const [index, gap] of gaps.entries()) {
      expect(gap, `band ${index + 1}→${index + 2}: ${RAMP[index]} vs ${RAMP[index + 1]}`)
        .toBeGreaterThanOrEqual(MIN_ADJACENT_DELTA_E)
    }
  })

  it('sweeps cold to hot, one way, with a real gap at every step', () => {
    const hues = RAMP.map(hue)
    for (let index = 1; index < hues.length; index += 1) {
      // Blue through cyan and green to amber and red: the hue falls, so the
      // order reads as temperature and not as a set of five unrelated colours.
      expect(hues[index - 1]! - hues[index]!, `band ${index + 1} hue`).toBeGreaterThanOrEqual(MIN_HUE_GAP)
    }
    // The ends are the ends: a blue slowest band and a red fastest one.
    expect(hues[0]).toBeGreaterThan(240)
    expect(hues.at(-1)).toBeLessThan(45)
  })

  it('holds every band against the casing it is stroked over', () => {
    for (const hex of RAMP) {
      expect(contrast(hex, CASING), `${hex} on its casing ${CASING}`).toBeGreaterThanOrEqual(MIN_CONTRAST)
    }
  })

  it('makes the casing carry the ground, since the bands no longer can', () => {
    // This is the trade the cold-to-hot ramp is bought with: an amber band
    // cannot clear a near-white basemap, so the stroke under it does.
    expect(contrast(CASING, LIGHT_GROUND), 'casing on the pale basemap').toBeGreaterThanOrEqual(MIN_CONTRAST)
    // On a dark basemap the casing disappears into the ground, so there the
    // bands answer for themselves — which, being bright, they can.
    for (const hex of RAMP) {
      expect(contrast(hex, DARK_GROUND), `${hex} on the dark basemap`).toBeGreaterThanOrEqual(MIN_CONTRAST)
    }
  })

  it('keeps direction off the channel the ramp encodes speed in', () => {
    // The chevrons were the accent blue, 6.6 ΔE2000 from the slowest band.
    const chevron = token('map-chevron-ink')
    for (const hex of RAMP) {
      expect(contrast(chevron, hex), `chevron ink on ${hex}`).toBeGreaterThanOrEqual(MIN_CONTRAST)
    }
  })

  it('runs one ramp for both basemaps, and as many steps as the scale has bands', () => {
    expect(RAMP).toHaveLength(TRAIL_BAND_COUNT)
    // A per-ground ramp would mean the same speed wearing two colours.
    expect(source.match(/--trail-1:/g) ?? []).toHaveLength(1)
  })
})
