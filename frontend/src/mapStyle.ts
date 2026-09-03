export type MapTone = 'light' | 'dark'
export type MapStyleMode = 'follow-interface' | 'fixed'

export interface MapStyleDefinition {
  id: string
  label: string
  tone: MapTone
}

export interface MapProviderDefinition {
  id: string
  label: string
  styles: readonly MapStyleDefinition[]
  defaults: Record<MapTone, string>
  styleUrl: (styleId: string) => string
}

export interface MapPreferences {
  providerId: string
  mode: MapStyleMode
  lightStyleId: string
  darkStyleId: string
  fixedStyleId: string
}

/*
 * Provider-specific knowledge stops here. VehicleMap consumes one resolved URL
 * and Settings consumes provider/style metadata; neither knows how OpenFreeMap
 * names endpoints. Adding a provider means adding one adapter, not branching in
 * the renderer or persistence layer.
 *
 * OpenFreeMap's public MapLibre endpoint documents Liberty, Positron, Bright,
 * Dark and Fiord. Liberty/Positron/Bright are light families; Dark and Fiord
 * are genuinely dark cartographies. Attribution comes from the provider's
 * TileJSON and MapLibre renders it.
 */
const OPENFREEMAP_TILES = 'https://tiles.openfreemap.org'

const openFreeMap: MapProviderDefinition = {
  id: 'openfreemap',
  label: 'OpenFreeMap',
  styles: [
    { id: 'liberty', label: 'Liberty', tone: 'light' },
    { id: 'positron', label: 'Positron', tone: 'light' },
    { id: 'bright', label: 'Bright', tone: 'light' },
    { id: 'dark', label: 'Dark', tone: 'dark' },
    { id: 'fiord', label: 'Fiord', tone: 'dark' },
  ],
  defaults: { light: 'liberty', dark: 'dark' },
  styleUrl: (styleId) => `${OPENFREEMAP_TILES}/styles/${styleId}`,
}

export const MAP_PROVIDERS: readonly MapProviderDefinition[] = [openFreeMap]

export const DEFAULT_MAP_PREFERENCES: MapPreferences = {
  providerId: openFreeMap.id,
  mode: 'follow-interface',
  lightStyleId: openFreeMap.defaults.light,
  darkStyleId: openFreeMap.defaults.dark,
  fixedStyleId: openFreeMap.defaults.light,
}

export function providerFor(id: string): MapProviderDefinition {
  return MAP_PROVIDERS.find((provider) => provider.id === id) ?? openFreeMap
}

export function stylesFor(providerId: string, tone?: MapTone): readonly MapStyleDefinition[] {
  const styles = providerFor(providerId).styles
  return tone ? styles.filter((style) => style.tone === tone) : styles
}

function validStyle(provider: MapProviderDefinition, styleId: unknown, tone?: MapTone): string | null {
  if (typeof styleId !== 'string') return null
  const style = provider.styles.find((candidate) => candidate.id === styleId)
  return style && (!tone || style.tone === tone) ? style.id : null
}

export function normalizeMapPreferences(raw: unknown): MapPreferences {
  const values = raw && typeof raw === 'object' ? raw as Partial<MapPreferences> : {}
  const provider = providerFor(typeof values.providerId === 'string' ? values.providerId : '')
  const mode = values.mode === 'fixed' ? 'fixed' : 'follow-interface'
  return {
    providerId: provider.id,
    mode,
    lightStyleId: validStyle(provider, values.lightStyleId, 'light') ?? provider.defaults.light,
    darkStyleId: validStyle(provider, values.darkStyleId, 'dark') ?? provider.defaults.dark,
    fixedStyleId: validStyle(provider, values.fixedStyleId) ?? provider.defaults.light,
  }
}

export function resolveMapStyle(
  preferences: MapPreferences,
  interfaceTheme: MapTone,
): { provider: MapProviderDefinition; style: MapStyleDefinition; url: string } {
  const normalized = normalizeMapPreferences(preferences)
  const provider = providerFor(normalized.providerId)
  const styleId = normalized.mode === 'fixed'
    ? normalized.fixedStyleId
    : interfaceTheme === 'dark' ? normalized.darkStyleId : normalized.lightStyleId
  const style = provider.styles.find((candidate) => candidate.id === styleId)
    ?? provider.styles.find((candidate) => candidate.id === provider.defaults[interfaceTheme])
    ?? provider.styles[0]!
  return { provider, style, url: provider.styleUrl(style.id) }
}
