<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { HistoryEntries, HistoryEntry } from '../api/types'
import { metricDefinition, metricLabel } from '../vehicleDisplay'
import AppIcon from './AppIcon.vue'
import AppSelect from './AppSelect.vue'

interface TableColumn {
  key: string
  label: string
  numeric: boolean
  unit: string
  decimals: number
}

interface ColumnPreference {
  order: string[]
  hidden: string[]
}

const props = defineProps<{ vehicleId: string; days: number }>()
const { t } = useI18n()

const FIXED: Array<{ key: string; labelKey: string; unit: string; decimals: number }> = [
  { key: 'recorded_at', labelKey: 'history.columns.recordedAt', unit: '', decimals: 0 },
  { key: 'speed', labelKey: 'history.columns.speed', unit: 'km/h', decimals: 1 },
  { key: 'latitude', labelKey: 'history.columns.latitude', unit: '°', decimals: 5 },
  { key: 'longitude', labelKey: 'history.columns.longitude', unit: '°', decimals: 5 },
  { key: 'altitude', labelKey: 'history.columns.altitude', unit: 'm', decimals: 1 },
  { key: 'heading', labelKey: 'history.columns.heading', unit: '°', decimals: 1 },
  { key: 'accuracy', labelKey: 'history.columns.accuracy', unit: 'm', decimals: 1 },
  { key: 'sequence', labelKey: 'history.columns.sequence', unit: '', decimals: 0 },
]
const PAGE_SIZES = [50, 100, 200]

const data = ref<HistoryEntries | null>(null)
const loading = ref(false)
const error = ref('')
const sort = ref('recorded_at')
const direction = ref<'asc' | 'desc'>('desc')
const limit = ref(50)
const offset = ref(0)
const filterColumn = ref('')
const filterMin = ref('')
const filterMax = ref('')
const filterPresent = ref(false)
const columnsOpen = ref(false)
const preference = ref<ColumnPreference>({ order: [], hidden: [] })
let request = 0

const storageKey = computed(() => `vehinode.history-columns.${props.vehicleId}`)

function humanize(key: string): string {
  const text = key.replaceAll('_', ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Every column the range can produce, in discovery order: fixed, then metrics, then device. */
const allColumns = computed<TableColumn[]>(() => {
  const columns: TableColumn[] = FIXED.map((column) => ({
    key: column.key,
    label: t(column.labelKey),
    numeric: column.key !== 'recorded_at',
    unit: column.unit,
    decimals: column.decimals,
  }))
  for (const name of data.value?.metric_keys ?? []) {
    const definition = metricDefinition(name)
    columns.push({
      key: `metric:${name}`,
      label: definition.labelKey ? metricLabel(definition, t) : name,
      numeric: true,
      unit: definition.unit,
      decimals: definition.decimals,
    })
  }
  for (const name of data.value?.device_keys ?? []) {
    columns.push({ key: `device:${name}`, label: humanize(name), numeric: true, unit: '', decimals: 1 })
  }
  return columns
})

/** Saved order first; columns discovered later append rather than disappear. */
const orderedColumns = computed<TableColumn[]>(() => {
  const byKey = new Map(allColumns.value.map((column) => [column.key, column]))
  const ordered = preference.value.order.flatMap((key) => {
    const column = byKey.get(key)
    return column ? [column] : []
  })
  const seen = new Set(ordered.map((column) => column.key))
  return [...ordered, ...allColumns.value.filter((column) => !seen.has(column.key))]
})

const visibleColumns = computed(() =>
  orderedColumns.value.filter((column) => !preference.value.hidden.includes(column.key)),
)
const hiddenCount = computed(() => orderedColumns.value.length - visibleColumns.value.length)
const filterable = computed(() => orderedColumns.value.filter((column) => column.numeric))
const total = computed(() => data.value?.total ?? 0)
const rangeStart = computed(() => (total.value ? offset.value + 1 : 0))
const rangeEnd = computed(() => Math.min(offset.value + limit.value, total.value))
const filterActive = computed(() =>
  Boolean(filterColumn.value) && (filterPresent.value || filterMin.value !== '' || filterMax.value !== ''),
)

function loadPreference(): void {
  preference.value = { order: [], hidden: [] }
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey.value) ?? 'null') as ColumnPreference | null
    if (stored && Array.isArray(stored.order) && Array.isArray(stored.hidden)) preference.value = stored
  } catch {
    // A malformed preference falls back to showing every column.
  }
}

function savePreference(): void {
  preference.value.order = orderedColumns.value.map((column) => column.key)
  localStorage.setItem(storageKey.value, JSON.stringify(preference.value))
}

function toggleColumn(key: string): void {
  const hidden = preference.value.hidden
  preference.value.hidden = hidden.includes(key)
    ? hidden.filter((value) => value !== key)
    : [...hidden, key]
  savePreference()
}

function moveColumn(key: string, offsetBy: -1 | 1): void {
  const order = orderedColumns.value.map((column) => column.key)
  const index = order.indexOf(key)
  const target = index + offsetBy
  if (index < 0 || target < 0 || target >= order.length) return
  order.splice(target, 0, ...order.splice(index, 1))
  preference.value.order = order
  localStorage.setItem(storageKey.value, JSON.stringify(preference.value))
}

function resetColumns(): void {
  preference.value = { order: [], hidden: [] }
  localStorage.removeItem(storageKey.value)
}

function sortBy(key: string): void {
  if (sort.value === key) direction.value = direction.value === 'desc' ? 'asc' : 'desc'
  else {
    sort.value = key
    direction.value = key === 'recorded_at' ? 'desc' : 'asc'
  }
  offset.value = 0
}

function clearFilter(): void {
  filterColumn.value = ''
  filterMin.value = ''
  filterMax.value = ''
  filterPresent.value = false
  offset.value = 0
}

async function load(): Promise<void> {
  const current = ++request
  loading.value = true
  error.value = ''
  const start = new Date(Date.now() - props.days * 86_400_000)
  const params = new URLSearchParams({
    start: start.toISOString(),
    limit: String(limit.value),
    offset: String(offset.value),
    sort: sort.value,
    direction: direction.value,
  })
  if (filterActive.value) {
    params.set('column', filterColumn.value)
    if (filterPresent.value) params.set('present', 'true')
    if (filterMin.value !== '') params.set('minimum', filterMin.value)
    if (filterMax.value !== '') params.set('maximum', filterMax.value)
  }
  try {
    const result = await api<HistoryEntries>(`/vehicles/${props.vehicleId}/history/entries?${params}`)
    if (current === request) data.value = result
  } catch (reason) {
    if (current === request) error.value = reason instanceof Error ? reason.message : t('common.error')
  } finally {
    if (current === request) loading.value = false
  }
}

function cell(entry: HistoryEntry, column: TableColumn): string {
  const [prefix, ...rest] = column.key.split(':')
  const name = rest.join(':')
  const raw =
    prefix === 'metric' ? entry.metrics[name]
    : prefix === 'device' ? entry.device[name]
    : (entry as unknown as Record<string, unknown>)[column.key]
  if (raw === null || raw === undefined || raw === '') return '—'
  if (column.key === 'recorded_at') return new Date(String(raw)).toLocaleString()
  if (typeof raw === 'boolean') return t(raw ? 'metrics.active' : 'metrics.inactive')
  // Fixed decimals per column keep a numeric column readable as one block.
  if (typeof raw === 'number') return raw.toFixed(column.decimals)
  return String(raw)
}

watch(() => props.vehicleId, () => { loadPreference(); offset.value = 0 }, { immediate: true })
watch(() => props.days, () => { offset.value = 0 })
watch([() => props.vehicleId, () => props.days, sort, direction, limit, offset, filterColumn, filterMin, filterMax, filterPresent], load, { immediate: true })
</script>

<template>
  <section class="entries panel">
    <header class="entries-head">
      <div>
        <h2>{{ t('history.entries') }}</h2>
        <p>{{ total ? t('history.entryRange', { from: rangeStart, to: rangeEnd, total }) : t('history.noEntries') }}</p>
      </div>
      <div class="entries-tools" @keydown.esc="columnsOpen = false">
        <button class="button secondary" type="button" aria-haspopup="true" :aria-expanded="columnsOpen" @click="columnsOpen = !columnsOpen">
          <AppIcon name="columns" :size="15" />
          {{ t('history.columnsButton') }}<span v-if="hiddenCount"> · {{ hiddenCount }}</span>
        </button>
        <div v-if="columnsOpen" class="columns-menu panel">
          <div class="columns-menu-head">
            <strong>{{ t('history.columnsTitle') }}</strong>
            <button class="link-button" type="button" @click="resetColumns">{{ t('history.reset') }}</button>
          </div>
          <ul>
            <li v-for="(column, index) in orderedColumns" :key="column.key">
              <label>
                <input type="checkbox" :checked="!preference.hidden.includes(column.key)" @change="toggleColumn(column.key)" />
                <span>{{ column.label }}</span>
              </label>
              <button class="icon-button" type="button" :disabled="index === 0" :aria-label="t('history.moveUp', { name: column.label })" @click="moveColumn(column.key, -1)"><AppIcon name="chevron-up" :size="14" /></button>
              <button class="icon-button" type="button" :disabled="index === orderedColumns.length - 1" :aria-label="t('history.moveDown', { name: column.label })" @click="moveColumn(column.key, 1)"><AppIcon name="chevron-down" :size="14" /></button>
            </li>
          </ul>
        </div>
      </div>
    </header>

    <div class="entries-filter">
      <label class="field inline"><span>{{ t('history.filterColumn') }}</span>
        <AppSelect v-model="filterColumn" compact :aria-label="t('history.filterColumn')">
          <option value="">{{ t('history.noFilter') }}</option>
          <option v-for="column in filterable" :key="column.key" :value="column.key">{{ column.label }}</option>
        </AppSelect>
      </label>
      <template v-if="filterColumn">
        <label class="field inline"><span>{{ t('history.minimum') }}</span><input v-model="filterMin" class="input" type="number" step="any" inputmode="decimal" /></label>
        <label class="field inline"><span>{{ t('history.maximum') }}</span><input v-model="filterMax" class="input" type="number" step="any" inputmode="decimal" /></label>
        <label class="check"><input v-model="filterPresent" type="checkbox" /><span>{{ t('history.onlyReported') }}</span></label>
        <button class="link-button" type="button" @click="clearFilter">{{ t('history.clear') }}</button>
      </template>
    </div>

    <p v-if="error" class="entries-note error" role="alert">{{ error }}</p>

    <div v-else-if="data?.entries.length" class="table-wrap" :aria-busy="loading">
      <table class="table entries-table">
        <thead>
          <tr>
            <th v-for="column in visibleColumns" :key="column.key" :aria-sort="sort === column.key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'">
              <button type="button" @click="sortBy(column.key)">
                <span>{{ column.label }}<em v-if="column.unit"> ({{ column.unit }})</em></span>
                <AppIcon v-if="sort === column.key" :name="direction === 'asc' ? 'chevron-up' : 'chevron-down'" :size="13" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="entry in data.entries" :key="entry.id">
            <td v-for="column in visibleColumns" :key="column.key" :class="{ numeric: column.numeric }">{{ cell(entry, column) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else class="entries-note">{{ loading ? t('common.loading') : t('history.noEntries') }}</p>

    <footer v-if="total > 0" class="entries-foot">
      <label class="field inline"><span>{{ t('history.pageSize') }}</span>
        <AppSelect v-model="limit" compact :aria-label="t('history.pageSize')">
          <option v-for="size in PAGE_SIZES" :key="size" :value="size">{{ size }}</option>
        </AppSelect>
      </label>
      <div class="pager">
        <button class="button secondary" type="button" :disabled="offset === 0" @click="offset = Math.max(0, offset - limit)">{{ t('history.previous') }}</button>
        <button class="button secondary" type="button" :disabled="rangeEnd >= total" @click="offset = offset + limit">{{ t('history.next') }}</button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.entries{display:grid;overflow:hidden}
.entries-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:14px 16px;border-bottom:1px solid var(--line)}
.entries-head h2{margin:0;font-size:13px;font-weight:600}
.entries-head p{margin:3px 0 0;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.entries-tools{position:relative}
.columns-menu{position:absolute;z-index:1400;top:38px;right:0;width:260px;max-height:340px;display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--shadow)}
.columns-menu-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line)}
.columns-menu-head strong{font-size:12px;font-weight:600}
.columns-menu ul{list-style:none;margin:0;padding:4px;min-height:0;overflow-y:auto}
.columns-menu li{display:grid;grid-template-columns:minmax(0,1fr) 24px 24px;align-items:center;gap:2px;padding:1px 4px}
.columns-menu label{min-width:0;display:flex;align-items:center;gap:8px;padding:5px 4px;font-size:12px;cursor:pointer}
.columns-menu label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.columns-menu input{width:13px;height:13px;flex:none;accent-color:var(--accent)}
.columns-menu .icon-button{width:24px;height:24px}

.entries-filter{display:flex;align-items:flex-end;flex-wrap:wrap;gap:12px 14px;padding:12px 16px;border-bottom:1px solid var(--line)}
.field.inline{gap:4px}
.field.inline>span{color:var(--muted);font-size:12px;font-weight:400}
.entries-filter .input{width:110px;min-height:30px;padding:4px 8px;font-size:12px}
.check{display:flex;align-items:center;gap:7px;padding-bottom:6px;font-size:12px;cursor:pointer}
.check input{width:13px;height:13px;accent-color:var(--accent)}
.entries-filter .link-button{padding-bottom:7px;font-size:12px}

.table-wrap{max-height:560px;overflow:auto}
.entries-table{font-variant-numeric:tabular-nums}
.entries-table th{position:sticky;top:0;z-index:1;padding:0;background:var(--panel);border-bottom:1px solid var(--line-strong);white-space:nowrap}
.entries-table th button{width:100%;display:flex;align-items:center;gap:5px;padding:8px 14px;color:var(--muted);background:transparent;border:0;font-size:12px;font-weight:500;text-align:left;cursor:pointer}
.entries-table th button:hover{color:var(--text)}
.entries-table th[aria-sort]:not([aria-sort="none"]) button{color:var(--text)}
.entries-table th em{color:var(--muted-2);font-style:normal}
.entries-table td{padding:7px 14px;white-space:nowrap}
.entries-table td.numeric{text-align:right}
.entries-table th:not(:first-child) button{justify-content:flex-end;flex-direction:row-reverse}
.entries-table tbody tr:hover td{background:var(--panel-2)}

.entries-note{margin:0;padding:28px 16px;color:var(--muted);font-size:13px;text-align:center}
.entries-note.error{color:var(--danger)}
.entries-foot{display:flex;align-items:flex-end;justify-content:space-between;gap:16px;padding:12px 16px;border-top:1px solid var(--line)}
.pager{display:flex;gap:8px}

@media(max-width:700px){
  .entries-head{align-items:stretch;flex-direction:column}
  .columns-menu{right:auto;left:0}
  .entries-foot{align-items:stretch;flex-direction:column}
  .pager .button{flex:1}
}
</style>
