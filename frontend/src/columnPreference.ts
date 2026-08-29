import { computed, ref, type ComputedRef, type Ref } from 'vue'

export interface ColumnChoice {
  key: string
  label: string
  /** Shown as the row's title in the picker, where one exists. */
  hint?: string
}

export interface ColumnPreference {
  order: string[]
  hidden: string[]
}

/**
 * Which columns a table shows, and in what order, remembered per vehicle.
 *
 * Two tables read the same history and neither should inherit the other's
 * layout, so each passes its own storage key. Columns discovered after a
 * preference was saved append rather than disappear, because a vehicle that
 * starts reporting a new metric should show it.
 */
export function useColumnPreference(storageKey: Ref<string>, columns: Ref<ColumnChoice[]>) {
  const preference = ref<ColumnPreference>({ order: [], hidden: [] })

  const ordered: ComputedRef<ColumnChoice[]> = computed(() => {
    const byKey = new Map(columns.value.map((column) => [column.key, column]))
    const known = preference.value.order.flatMap((key) => {
      const column = byKey.get(key)
      return column ? [column] : []
    })
    const seen = new Set(known.map((column) => column.key))
    return [...known, ...columns.value.filter((column) => !seen.has(column.key))]
  })

  const visible = computed(() => ordered.value.filter((column) => !preference.value.hidden.includes(column.key)))
  const hiddenCount = computed(() => ordered.value.length - visible.value.length)

  function save(): void {
    preference.value.order = ordered.value.map((column) => column.key)
    localStorage.setItem(storageKey.value, JSON.stringify(preference.value))
  }

  /** Returns false when nothing was stored, so a caller can apply its defaults. */
  function load(): boolean {
    preference.value = { order: [], hidden: [] }
    try {
      const stored = JSON.parse(localStorage.getItem(storageKey.value) ?? 'null') as ColumnPreference | null
      if (stored && Array.isArray(stored.order) && Array.isArray(stored.hidden)) {
        preference.value = stored
        return true
      }
    } catch {
      // A malformed preference falls back to showing every column.
    }
    return false
  }

  function toggle(key: string): void {
    const hidden = preference.value.hidden
    preference.value.hidden = hidden.includes(key) ? hidden.filter((value) => value !== key) : [...hidden, key]
    save()
  }

  function move(key: string, offsetBy: -1 | 1): void {
    const order = ordered.value.map((column) => column.key)
    const index = order.indexOf(key)
    const target = index + offsetBy
    if (index < 0 || target < 0 || target >= order.length) return
    order.splice(target, 0, ...order.splice(index, 1))
    preference.value.order = order
    localStorage.setItem(storageKey.value, JSON.stringify(preference.value))
  }

  function reset(): void {
    preference.value = { order: [], hidden: [] }
    localStorage.removeItem(storageKey.value)
  }

  return { preference, ordered, visible, hiddenCount, load, save, toggle, move, reset }
}
