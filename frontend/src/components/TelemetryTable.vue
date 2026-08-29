<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, type CSSProperties, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorMessage } from '../api/client'
import { loadSampleProvenance } from '../api/segments'
import { useLiveRefresh } from '../api/live'
import type { HistoryEntries, HistoryEntry, HistoryObservationSample } from '../api/types'
import { formatInstant, formatSpan, metricDefinition, metricLabel } from '../vehicleDisplay'
import { layerHost } from '../layerHost'
import AppHelp from './AppHelp.vue'
import AppIcon from './AppIcon.vue'
import AppSelect from './AppSelect.vue'

interface TableColumn {
  key: string
  label: string
  // The canonical name behind the label. A friendly label is what makes a table
  // readable and the canonical name is what a profile, a hook and a filter are
  // all written against, so the column carries both rather than choosing.
  canonical: string
  numeric: boolean
  unit: string
  decimals: number
}

interface ColumnPreference {
  order: string[]
  hidden: string[]
}

const props = defineProps<{ vehicleId: string; days: number }>()
const { t, te, locale } = useI18n()

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
interface EntryFilter {
  id: number
  column: string
  minimum: string
  maximum: string
  present: boolean
}

const filters = ref<EntryFilter[]>([])
const columnsOpen = ref(false)
const host = computed(layerHost)
const columnsTools = ref<HTMLElement>()
const columnsMenu = ref<HTMLElement>()
const columnsStyle = ref<CSSProperties>({})

/**
 * The picker is anchored to its button but drawn against the viewport.
 *
 * The entries panel clips its own overflow so the table's corners stay rounded,
 * which cut the menu off at the panel edge. Teleporting it out and positioning
 * it here is what the row menus and help bubbles already do.
 */
function placeColumns(): void {
  const bounds = columnsTools.value?.getBoundingClientRect()
  if (!bounds) return
  const edge = 8
  const width = 260
  const height = columnsMenu.value?.offsetHeight ?? 0
  const below = bounds.bottom + 6
  const flip = height > 0 && below + height > window.innerHeight - edge && bounds.top - height - 6 > edge
  columnsStyle.value = {
    top: `${flip ? bounds.top - height - 6 : below}px`,
    left: `${Math.min(Math.max(edge, bounds.right - width), window.innerWidth - width - edge)}px`,
  }
}

async function toggleColumns(): Promise<void> {
  if (columnsOpen.value) {
    columnsOpen.value = false
    window.removeEventListener('resize', placeColumns)
    window.removeEventListener('scroll', placeColumns, true)
    return
  }
  columnsOpen.value = true
  await nextTick()
  placeColumns()
  placeColumns()
  window.addEventListener('resize', placeColumns)
  window.addEventListener('scroll', placeColumns, true)
}
let nextFilterId = 1
const preference = ref<ColumnPreference>({ order: [], hidden: [] })
let request = 0

const storageKey = computed(() => `carhibou.history-columns.${props.vehicleId}`)

function humanize(key: string): string {
  const text = key.replaceAll('_', ' ').trim()
  return text.charAt(0).toUpperCase() + text.slice(1)
}

/** Every column the range can produce, in discovery order: fixed, then metrics, then agent. */
const allColumns = computed<TableColumn[]>(() => {
  const columns: TableColumn[] = FIXED.map((column) => ({
    key: column.key,
    label: t(column.labelKey),
    canonical: column.key,
    numeric: column.key !== 'recorded_at',
    unit: column.unit,
    decimals: column.decimals,
  }))
  for (const name of data.value?.metric_keys ?? []) {
    const definition = metricDefinition(name)
    columns.push({
      key: `metric:${name}`,
      label: definition.labelKey ? metricLabel(definition, t) : name,
      canonical: name,
      numeric: true,
      unit: definition.unit,
      decimals: definition.decimals,
    })
  }
  for (const name of data.value?.agent_keys ?? []) {
    columns.push({ key: `agent:${name}`, label: humanize(name), canonical: name, numeric: true, unit: '', decimals: 1 })
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
/** A filter with a column but no bound yet narrows nothing, so it is not sent. */
function filterQuery(filter: EntryFilter): string | null {
  if (!filter.column) return null
  if (!filter.present && filter.minimum === '' && filter.maximum === '') return null
  return `${filter.column}|${filter.minimum}|${filter.maximum}|${filter.present ? '1' : ''}`
}

const activeFilters = computed(() => filters.value.flatMap((filter) => {
  const query = filterQuery(filter)
  return query ? [query] : []
}))

/** Columns the agent reports about itself rather than about the vehicle. */
function systemColumns(): string[] {
  return (data.value?.agent_keys ?? []).map((name) => `agent:${name}`)
}

function loadPreference(): void {
  // An agent's own load average and queue depth are not readings from the car,
  // and there are enough of them to bury the ones that are. They stay available,
  // in the column menu, rather than shown by default.
  preference.value = { order: [], hidden: systemColumns() }
  try {
    const stored = JSON.parse(localStorage.getItem(storageKey.value) ?? 'null') as ColumnPreference | null
    if (stored && Array.isArray(stored.order) && Array.isArray(stored.hidden)) preference.value = stored
    else hideSystemOnceKnown = true
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

/** What a label stands for: the canonical name, and a note where one exists.
 *
 * The lookup key has its dots removed because vue-i18n reads a dot as a step into
 * a nested message, so a canonical name cannot be a key as it stands.
 */
function columnHint(column: TableColumn): string {
  const path = `metricNotes.${column.canonical.replaceAll('.', '_')}`
  return te(path) ? `${column.canonical} — ${t(path)}` : column.canonical
}

function sortBy(key: string): void {
  if (sort.value === key) direction.value = direction.value === 'desc' ? 'asc' : 'desc'
  else {
    sort.value = key
    direction.value = key === 'recorded_at' ? 'desc' : 'asc'
  }
  offset.value = 0
}

function addFilter(): void {
  const used = new Set(filters.value.map((filter) => filter.column))
  const next = filterable.value.find((column) => !used.has(column.key))
  filters.value.push({
    id: nextFilterId++,
    column: next?.key ?? '',
    minimum: '',
    maximum: '',
    present: false,
  })
}

function removeFilter(id: number): void {
  filters.value = filters.value.filter((filter) => filter.id !== id)
  offset.value = 0
}

function clearFilters(): void {
  filters.value = []
  offset.value = 0
}

/**
 * Where one row's values came from.
 *
 * The grid is served by /entries, the only endpoint that can sort and filter,
 * and that endpoint carries values without provenance. Rather than trade the
 * grid's abilities away, provenance is fetched per row from /observations when a
 * reader opens one, which is also the only time it is worth a request.
 */
const openSample = ref('')
const provenance = ref<HistoryObservationSample | null>(null)
const provenanceError = ref('')
const provenanceLoading = ref(false)
let provenanceRequest = 0

async function toggleSample(entry: HistoryEntry): Promise<void> {
  if (openSample.value === entry.id) {
    openSample.value = ''
    return
  }
  const current = ++provenanceRequest
  openSample.value = entry.id
  provenance.value = null
  provenanceError.value = ''
  provenanceLoading.value = true
  try {
    const found = await loadSampleProvenance(props.vehicleId, entry)
    if (current === provenanceRequest) provenance.value = found
  } catch (reason) {
    if (current === provenanceRequest) provenanceError.value = errorMessage(reason, t('common.error'))
  } finally {
    if (current === provenanceRequest) provenanceLoading.value = false
  }
}

/** How long the sample spent in flight, when that is worth saying. */
const uploadLag = computed(() => {
  if (!provenance.value) return ''
  const seconds = Math.round(
    (new Date(provenance.value.received_at).getTime() - new Date(provenance.value.recorded_at).getTime()) / 1000,
  )
  return seconds > 0 ? formatSpan(seconds, locale.value) : ''
})

/**
 * How long before its own report an observation was taken.
 *
 * The gap between two instants this panel already shows, named as such. Said as
 * an age it would claim a distance from now, which for a batch upload is the
 * one thing it is not: an agent on the parked cadence can carry a fix that is
 * seconds older than its report and minutes older than this moment.
 */
function beforeReport(observedAt: string): string {
  if (!provenance.value) return ''
  const seconds = Math.round((new Date(provenance.value.recorded_at).getTime() - new Date(observedAt).getTime()) / 1000)
  return seconds > 0 ? t('history.beforeReport', { span: formatSpan(seconds, locale.value) }) : ''
}

function observationValue(value: unknown): string {
  if (typeof value === 'boolean') return t(value ? 'metrics.active' : 'metrics.inactive')
  if (typeof value === 'number') return String(value)
  return value === null || value === undefined ? '—' : String(value)
}

function sourceLabel(sample: HistoryObservationSample): string {
  return `${t(`history.sourceKind.${sample.source_kind}`)} · ${sample.source_id}`
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
  for (const filter of activeFilters.value) params.append('filter', filter)
  try {
    const result = await api<HistoryEntries>(`/vehicles/${props.vehicleId}/history/entries?${params}`)
    if (current === request) data.value = result
  } catch (reason) {
    if (current === request) error.value = errorMessage(reason, t('common.error'))
  } finally {
    if (current === request) loading.value = false
  }
}

function cell(entry: HistoryEntry, column: TableColumn): string {
  const [prefix, ...rest] = column.key.split(':')
  const name = rest.join(':')
  const raw =
    prefix === 'metric' ? entry.metrics[name]
    : prefix === 'agent' ? entry.agent[name]
    : (entry as unknown as Record<string, unknown>)[column.key]
  if (raw === null || raw === undefined || raw === '') return '—'
  if (column.key === 'recorded_at') return formatInstant(String(raw))
  if (typeof raw === 'boolean') return t(raw ? 'metrics.active' : 'metrics.inactive')
  // Fixed decimals per column keep a numeric column readable as one block.
  if (typeof raw === 'number') return raw.toFixed(column.decimals)
  return String(raw)
}

// The column set is per vehicle, so a filter on a column the next vehicle does not
// report would silently return nothing.
// The agent's columns are only known once a page has arrived, so a first visit
// applies the default the moment they are.
let hideSystemOnceKnown = true
watch(() => data.value?.agent_keys, (keys) => {
  if (!hideSystemOnceKnown || !keys?.length) return
  hideSystemOnceKnown = false
  preference.value = { ...preference.value, hidden: [...new Set([...preference.value.hidden, ...systemColumns()])] }
})

watch(() => props.vehicleId, () => { hideSystemOnceKnown = true; loadPreference(); filters.value = []; offset.value = 0 }, { immediate: true })
watch(() => props.days, () => { offset.value = 0 })
watch(activeFilters, () => { offset.value = 0 })
watch([() => props.vehicleId, () => props.days, sort, direction, limit, offset, activeFilters], load, { immediate: true })

/**
 * New telemetry while the reader is in the table.
 *
 * On the first page the newest rows are the ones being looked at, so the table
 * refetches in place. Deeper in, refetching would slide rows under the cursor as
 * newer ones are inserted above, so the table says there is new data and waits to
 * be asked. Page, sort and filters are never changed by either path.
 */
const staleRows = ref(false)
useLiveRefresh(() => {
  if (offset.value === 0) void load()
  else staleRows.value = true
})
watch([() => props.vehicleId, () => props.days, sort, direction, limit, offset, activeFilters], () => { staleRows.value = false })

function showNewRows(): void {
  staleRows.value = false
  void load()
}

function closeColumns(event: PointerEvent): void {
  const target = event.target as Node
  if (!columnsTools.value?.contains(target) && !columnsMenu.value?.contains(target)) columnsOpen.value = false
}

document.addEventListener('pointerdown', closeColumns, true)
onBeforeUnmount(() => document.removeEventListener('pointerdown', closeColumns, true))
</script>

<template>
  <section class="entries panel">
    <header class="entries-head">
      <div>
        <h2>{{ t('history.entries') }}</h2>
        <p>{{ total ? t('history.entryRange', { from: rangeStart, to: rangeEnd, total }) : t('history.noEntries') }}</p>
      </div>
      <div ref="columnsTools" class="entries-tools" @keydown.esc="columnsOpen = false">
        <button class="button secondary" type="button" aria-haspopup="true" :aria-expanded="columnsOpen" @click="toggleColumns">
          <AppIcon name="columns" :size="15" />
          {{ t('history.columnsButton') }}<span v-if="hiddenCount"> · {{ hiddenCount }}</span>
        </button>
        <Teleport :to="host">
        <div v-if="columnsOpen" ref="columnsMenu" class="columns-menu panel" :style="columnsStyle">
          <div class="columns-menu-head">
            <strong>{{ t('history.columnsTitle') }}</strong>
            <button class="link-button" type="button" @click="resetColumns">{{ t('history.reset') }}</button>
          </div>
          <ul>
            <li v-for="(column, index) in orderedColumns" :key="column.key">
              <label :title="columnHint(column)">
                <input type="checkbox" :checked="!preference.hidden.includes(column.key)" @change="toggleColumn(column.key)" />
                <span>{{ column.label }}</span>
              </label>
              <button class="icon-button" type="button" :disabled="index === 0" :aria-label="t('history.moveUp', { name: column.label })" @click="moveColumn(column.key, -1)"><AppIcon name="chevron-up" :size="14" /></button>
              <button class="icon-button" type="button" :disabled="index === orderedColumns.length - 1" :aria-label="t('history.moveDown', { name: column.label })" @click="moveColumn(column.key, 1)"><AppIcon name="chevron-down" :size="14" /></button>
            </li>
          </ul>
        </div>
        </Teleport>
      </div>
    </header>

    <div class="entries-filter">
      <div v-for="filter in filters" :key="filter.id" class="filter-row">
        <label class="field inline filter-column"><span>{{ t('history.filterColumn') }}</span>
          <AppSelect v-model="filter.column" searchable :search-placeholder="t('common.search')" :no-results-text="t('common.noResults')" :aria-label="t('history.filterColumn')">
            <option v-for="column in filterable" :key="column.key" :value="column.key">{{ column.label }}</option>
          </AppSelect>
        </label>
        <label class="field inline"><span>{{ t('history.minimum') }}</span><input v-model="filter.minimum" class="input" type="number" step="any" inputmode="decimal" /></label>
        <label class="field inline"><span>{{ t('history.maximum') }}</span><input v-model="filter.maximum" class="input" type="number" step="any" inputmode="decimal" /></label>
        <label class="check"><input v-model="filter.present" type="checkbox" /><span>{{ t('history.onlyReported') }}</span></label>
        <button class="icon-button remove-filter" type="button" :aria-label="t('history.removeFilter')" @click="removeFilter(filter.id)"><AppIcon name="close" :size="15" /></button>
      </div>
      <div class="filter-actions">
        <button class="button secondary" type="button" :disabled="!filterable.length" @click="addFilter">
          <AppIcon name="plus" :size="15" />{{ t('history.addFilter') }}
        </button>
        <button v-if="filters.length" class="link-button" type="button" @click="clearFilters">{{ t('history.clear') }}</button>
      </div>
    </div>

    <p v-if="staleRows" class="entries-fresh">
      <span>{{ t('history.newEntries') }}</span>
      <button class="link-button" type="button" @click="showNewRows">{{ t('history.showNewEntries') }}</button>
    </p>

    <p v-if="error" class="entries-note error" role="alert">{{ error }}</p>

    <div v-else-if="data?.entries?.length" class="table-wrap" :aria-busy="loading">
      <table class="table entries-table">
        <thead>
          <tr>
            <th class="expand-cell"><span class="sr-only">{{ t('history.provenance') }}</span></th>
            <th v-for="column in visibleColumns" :key="column.key" :aria-sort="sort === column.key ? (direction === 'asc' ? 'ascending' : 'descending') : 'none'">
              <button type="button" :title="columnHint(column)" @click="sortBy(column.key)">
                <span>{{ column.label }}<em v-if="column.unit"> ({{ column.unit }})</em></span>
                <AppIcon v-if="sort === column.key" :name="direction === 'asc' ? 'chevron-up' : 'chevron-down'" :size="13" />
              </button>
            </th>
          </tr>
        </thead>
        <tbody>
          <template v-for="entry in data.entries" :key="entry.id">
            <tr :class="{ 'is-open': openSample === entry.id }">
              <td class="expand-cell">
                <button class="icon-button" type="button" :aria-expanded="openSample === entry.id" :aria-label="t('history.provenanceFor', { time: formatInstant(entry.recorded_at) })" @click="toggleSample(entry)">
                  <AppIcon :name="openSample === entry.id ? 'chevron-up' : 'chevron-down'" :size="15" />
                </button>
              </td>
              <td v-for="column in visibleColumns" :key="column.key" :class="{ numeric: column.numeric }">{{ cell(entry, column) }}</td>
            </tr>
            <tr v-if="openSample === entry.id" class="provenance-row">
              <td :colspan="visibleColumns.length + 1">
                <p v-if="provenanceError" class="error" role="alert">{{ provenanceError }}</p>
                <p v-else-if="provenanceLoading" class="muted">{{ t('common.loading') }}</p>
                <div v-else-if="provenance" class="provenance">
                  <dl class="provenance-facts">
                    <div><dt>{{ t('history.source') }}</dt><dd>{{ sourceLabel(provenance) }}</dd></div>
                    <div><dt>{{ t('history.observedAt') }}</dt><dd>{{ formatInstant(provenance.recorded_at) }}</dd></div>
                    <div><dt>{{ t('history.receivedAt') }}</dt><dd>{{ formatInstant(provenance.received_at) }}<small v-if="uploadLag">{{ t('history.uploadLag', { lag: uploadLag }) }}</small></dd></div>
                    <div><dt>{{ t('history.cadence') }}</dt><dd>{{ provenance.event_driven ? t('history.eventDriven') : provenance.reporting_interval ? formatSpan(provenance.reporting_interval, locale) : '—' }}</dd></div>
                  </dl>
                  <table class="table provenance-table">
                    <thead>
                      <tr>
                        <th scope="col">{{ t('history.metric') }}</th>
                        <th scope="col">{{ t('history.value') }}</th>
                        <th scope="col">
                          {{ t('history.channel') }}
                          <AppHelp :label="t('history.channelHelpLabel')">
                            <dl>
                              <div v-for="channel in (['can','obd','gnss','mqtt','derived'] as const)" :key="channel">
                                <dt>{{ t(`history.channels.${channel}`) }}</dt>
                                <dd>{{ t(`history.channelHelp.${channel}`) }}</dd>
                              </div>
                            </dl>
                          </AppHelp>
                        </th>
                        <th scope="col">
                          {{ t('history.method') }}
                          <AppHelp :label="t('history.methodHelpLabel')">
                            <dl>
                              <div v-for="method in (['direct','derived'] as const)" :key="method">
                                <dt>{{ t(`history.methods.${method}`) }}</dt>
                                <dd>{{ t(`history.methodHelp.${method}`) }}</dd>
                              </div>
                            </dl>
                          </AppHelp>
                        </th>
                        <th scope="col">{{ t('history.observedAt') }}</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-if="provenance.position">
                        <td>{{ t('history.columns.position') }}</td>
                        <td class="mono">{{ provenance.position.value.latitude.toFixed(5) }}, {{ provenance.position.value.longitude.toFixed(5) }}</td>
                        <td>{{ t(`history.channels.${provenance.position.channel}`) }}</td>
                        <td>{{ t(`history.methods.${provenance.position.method}`) }}</td>
                        <td>{{ formatInstant(provenance.position.observed_at) }}<small v-if="beforeReport(provenance.position.observed_at)" class="observed-age">{{ beforeReport(provenance.position.observed_at) }}</small></td>
                      </tr>
                      <tr v-for="observation in provenance.observations" :key="`${observation.key}-${observation.channel}`">
                        <td>{{ metricLabel(metricDefinition(observation.key), t) }}<small class="mono">{{ observation.key }}</small></td>
                        <td class="mono">{{ observationValue(observation.value) }}</td>
                        <td>{{ t(`history.channels.${observation.channel}`) }}</td>
                        <td>{{ t(`history.methods.${observation.method}`) }}</td>
                        <td>{{ formatInstant(observation.observed_at) }}</td>
                      </tr>
                    </tbody>
                  </table>
                </div>
                <p v-else class="muted">{{ t('history.noProvenance') }}</p>
              </td>
            </tr>
          </template>
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
/* The disclosure column is chrome, not data, so it takes only what it needs and
   never enters the sort or the column preference. */
.expand-cell{width:44px}
.expand-cell .icon-button{width:26px;height:26px}
tr.is-open>td{border-bottom-color:transparent}
.provenance-row>td{padding:0 14px 14px;background:var(--panel-2)}
.provenance{display:grid;gap:12px;padding-top:12px}
.provenance-facts{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:12px 18px;margin:0}
.provenance-facts dt{color:var(--muted);font-size:var(--font-caption)}
.provenance-facts dd{margin:2px 0 0;font-size:var(--font-caption)}
.provenance-facts dd small{margin-left:6px;color:var(--muted)}
.provenance-table{background:var(--panel);border-radius:var(--radius)}
.provenance-table th,.provenance-table td{padding:7px 11px}
.provenance-table th{white-space:nowrap}
.provenance-table th .app-help{margin-left:4px}
.provenance-table td small{display:block;margin-top:1px;color:var(--muted-2);font-size:var(--font-micro)}
.observed-age{color:var(--muted-2)}
.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%);white-space:nowrap}

.entries{display:grid;overflow:hidden}
.entries-fresh{display:flex;align-items:center;justify-content:center;gap:8px;margin:0;padding:8px 16px;color:var(--muted);background:var(--panel-2);font-size:var(--font-caption);border-bottom:1px solid var(--line)}
.entries-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;padding:14px 16px;border-bottom:1px solid var(--line)}
.entries-head h2{margin:0;font-size:13px;font-weight:600}
.entries-head p{margin:3px 0 0;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.entries-tools{position:relative}
.columns-menu{position:fixed;z-index:1400;width:260px;max-height:340px;display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--shadow)}
.columns-menu-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line)}
.columns-menu-head strong{font-size:12px;font-weight:600}
.columns-menu ul{list-style:none;margin:0;padding:4px;min-height:0;overflow-y:auto}
.columns-menu li{display:grid;grid-template-columns:minmax(0,1fr) 24px 24px;align-items:center;gap:2px;padding:1px 4px}
.columns-menu label{min-width:0;display:flex;align-items:center;gap:8px;padding:5px 4px;font-size:12px;cursor:pointer}
.columns-menu label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.columns-menu input{width:13px;height:13px;flex:none;accent-color:var(--accent)}
.columns-menu .icon-button{width:24px;height:24px}

.entries-filter{display:grid;gap:10px;padding:12px 16px;border-bottom:1px solid var(--line)}
.filter-row{display:flex;align-items:flex-end;flex-wrap:wrap;gap:10px 14px}
.field.inline{gap:4px}
.field.inline>span{color:var(--muted);font-size:12px;font-weight:400}
/* Metric names are long and a truncated one is unusable as a filter label, so the
   column select is sized to read rather than to fit its shortest option. */
.filter-column{min-width:220px;flex:1 1 220px;max-width:320px}
.entries-filter .input{width:110px;min-height:30px;padding:4px 8px;font-size:12px}
.check{display:flex;align-items:center;gap:7px;padding-bottom:6px;font-size:12px;cursor:pointer}
.check input{width:13px;height:13px;accent-color:var(--accent)}
.remove-filter{width:30px;height:30px;flex:none}
.filter-actions{display:flex;align-items:center;gap:12px}
.entries-filter .link-button{font-size:12px}

.table-wrap{max-height:560px;overflow:auto}
.entries-table{font-variant-numeric:tabular-nums}
.entries-table th{position:sticky;top:0;z-index:1;padding:0;background:var(--panel);border-bottom:1px solid var(--line-strong);white-space:nowrap}
.entries-table th button{width:100%;display:flex;align-items:center;gap:5px;padding:8px 14px;color:var(--muted);background:transparent;border:0;font-size:12px;font-weight:500;text-align:left;cursor:pointer}
.entries-table th button:hover{color:var(--text)}
.entries-table th[aria-sort]:not([aria-sort="none"]) button{color:var(--text)}
.entries-table th em{color:var(--muted-2);font-style:normal}
.entries-table td{padding:7px 14px;white-space:nowrap}
.entries-table th.expand-cell{padding:8px 0 8px 18px}
.entries-table td.expand-cell{padding-left:18px;padding-right:0}
.entries-table td.numeric{text-align:right}
.entries-table th:not(:first-child) button{justify-content:flex-end;flex-direction:row-reverse}

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
