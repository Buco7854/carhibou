import { computed, ref } from 'vue'

export type ThemeMode = 'light' | 'dark' | 'auto'

const stored = localStorage.getItem('vehinode.theme')
export const themeMode = ref<ThemeMode>(
  stored === 'light' || stored === 'dark' || stored === 'auto' ? stored : 'auto',
)
const systemDark = ref(matchMedia('(prefers-color-scheme: dark)').matches)
export const resolvedTheme = computed<'light' | 'dark'>(() =>
  themeMode.value === 'auto' ? (systemDark.value ? 'dark' : 'light') : themeMode.value,
)

function applyTheme(): void {
  document.documentElement.dataset.theme = resolvedTheme.value
  document.documentElement.style.colorScheme = resolvedTheme.value
  document.querySelector<HTMLMetaElement>('meta[name="theme-color"]')?.setAttribute(
    'content', resolvedTheme.value === 'dark' ? '#06100d' : '#f3f7f5',
  )
}

export function setTheme(mode: ThemeMode): void {
  themeMode.value = mode
  localStorage.setItem('vehinode.theme', mode)
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
