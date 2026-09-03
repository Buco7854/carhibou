import { computed, ref } from 'vue'
import {
  DEFAULT_MAP_PREFERENCES,
  normalizeMapPreferences,
  resolveMapStyle,
  type MapPreferences,
} from './mapStyle'
import { resolvedTheme } from './theme'

const STORAGE_KEY = 'carhibou.map-preferences'

function storedPreferences(): MapPreferences {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return normalizeMapPreferences(stored ? JSON.parse(stored) : DEFAULT_MAP_PREFERENCES)
  } catch {
    return { ...DEFAULT_MAP_PREFERENCES }
  }
}

export const mapPreferences = ref<MapPreferences>(storedPreferences())

export const resolvedMapStyle = computed(() =>
  resolveMapStyle(mapPreferences.value, resolvedTheme.value),
)

export function setMapPreferences(patch: Partial<MapPreferences>): void {
  const next = normalizeMapPreferences({ ...mapPreferences.value, ...patch })
  mapPreferences.value = next
  localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
}
