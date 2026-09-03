import { describe, expect, it } from 'vitest'
import {
  DEFAULT_MAP_PREFERENCES,
  normalizeMapPreferences,
  resolveMapStyle,
  stylesFor,
} from '../src/mapStyle'

describe('map provider styles', () => {
  it('follows the interface with Liberty for light and Dark for dark by default', () => {
    const light = resolveMapStyle(DEFAULT_MAP_PREFERENCES, 'light')
    const dark = resolveMapStyle(DEFAULT_MAP_PREFERENCES, 'dark')

    expect(light.style.id).toBe('liberty')
    expect(light.url).toBe('https://tiles.openfreemap.org/styles/liberty')
    expect(dark.style.id).toBe('dark')
    expect(dark.url).toBe('https://tiles.openfreemap.org/styles/dark')
  })

  it('offers real light and dark families in their respective selectors', () => {
    expect(stylesFor('openfreemap', 'light').map((style) => style.id))
      .toEqual(['liberty', 'positron', 'bright'])
    expect(stylesFor('openfreemap', 'dark').map((style) => style.id))
      .toEqual(['dark', 'fiord'])
  })

  it('keeps a fixed provider style independent of the interface theme', () => {
    const preferences = { ...DEFAULT_MAP_PREFERENCES, mode: 'fixed' as const, fixedStyleId: 'fiord' }
    expect(resolveMapStyle(preferences, 'light').style.id).toBe('fiord')
    expect(resolveMapStyle(preferences, 'dark').style.id).toBe('fiord')
  })

  it('normalizes unknown providers and styles to that provider defaults', () => {
    expect(normalizeMapPreferences({
      providerId: 'missing',
      mode: 'follow-interface',
      lightStyleId: 'dark',
      darkStyleId: 'liberty',
      fixedStyleId: 'missing',
    })).toEqual(DEFAULT_MAP_PREFERENCES)
  })
})
