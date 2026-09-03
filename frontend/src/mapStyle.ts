import type { ThemeMode } from './theme'

/*
 * The ground the map is drawn on.
 *
 * OpenFreeMap serves OpenMapTiles vector tiles from a public instance with no
 * key, no registration and no request limit, financed by donations, with the
 * whole production setup published. That last part is why it is here rather
 * than a keyed provider: if the public instance ever goes away, sovereignty is
 * a change to the constant below, not a migration.
 *
 * Positron and Dark are two real cartographies rather than one filtered into
 * two. The CSS filter that used to make "dark" out of a light basemap is gone:
 * turning a white map down gave grey, not dark, which is exactly the washed
 * look a reader reported.
 *
 * Their documented endpoint shape is /styles/{name}. Attribution is required
 * and, as their integration guide says, MapLibre adds it on its own: the
 * TileJSON at /planet carries "OpenFreeMap (c) OpenMapTiles Data from
 * OpenStreetMap", so the attribution control shows it without being told. That
 * is why nothing here passes a custom attribution string; writing one by hand
 * would duplicate what the source already declares and drift from it.
 */
const TILES = 'https://tiles.openfreemap.org'

export const MAP_STYLES = {
  light: `${TILES}/styles/positron`,
  dark: `${TILES}/styles/dark`,
} as const

export function styleFor(theme: 'light' | 'dark'): string {
  return MAP_STYLES[theme]
}

export type { ThemeMode }
