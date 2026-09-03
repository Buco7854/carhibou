import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

const stored = localStorage.getItem('carhibou.theme')
export const themeMode = ref<ThemeMode>(
  stored === 'light' || stored === 'dark' || stored === 'auto' ? stored : 'auto',
)
const systemDark = ref(matchMedia('(prefers-color-scheme: dark)').matches)
export const resolvedTheme = computed<'light' | 'dark'>(() =>
  themeMode.value === 'auto' ? (systemDark.value ? 'dark' : 'light') : themeMode.value,
)

/*
 * The map's own ground, which need not follow the interface.
 *
 * A dark interface at night is a preference; a dark map is sometimes a
 * different one, because the map is read against daylight out of a windscreen.
 * Auto follows the app, which is what almost everyone wants and so is default.
 */
const storedMap = localStorage.getItem('carhibou.map-theme')
export const mapThemeMode = ref<ThemeMode>(
  storedMap === 'light' || storedMap === 'dark' || storedMap === 'auto' ? storedMap : 'auto',
)

export const resolvedMapTheme = computed<'light' | 'dark'>(() =>
  mapThemeMode.value === 'auto' ? resolvedTheme.value : mapThemeMode.value,
)

export function setMapTheme(mode: ThemeMode): void {
  mapThemeMode.value = mode
  localStorage.setItem('carhibou.map-theme', mode)
}

function applyTheme(): void {
  document.documentElement.dataset.theme = resolvedTheme.value
  document.documentElement.style.colorScheme = resolvedTheme.value
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute(
    'content', resolvedTheme.value === 'dark' ? '#10100f' : '#f7f7f5',
  )
}

export function setTheme(mode: ThemeMode): void {
  themeMode.value = mode
  localStorage.setItem('carhibou.theme', mode)
  applyTheme()
}

export function initializeTheme(): void {
  const media = matchMedia('(prefers-color-scheme: dark)')
  systemDark.value = media.matches
  media.addEventListener('change', (event) => {
    systemDark.value = event.matches
    if (themeMode.value === 'auto') applyTheme()
  })
  applyTheme()
}
