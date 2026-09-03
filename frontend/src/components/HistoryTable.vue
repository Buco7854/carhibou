<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorMessage } from '../api/client'
import { TABLE_STEP_SECONDS, loadHistoryTable } from '../api/segments'
import type { HistoryTable, HistoryTableRow, Reading } from '../api/types'
import { useColumnPreference } from '../columnPreference'
import { formatCoordinates } from '../numberFormat'
import { formatMetricNumber, formatSpan, metricDefinition, metricLabel } from '../vehicleDisplay'
import AppHelp from './AppHelp.vue'
import ColumnPicker from './ColumnPicker.vue'
import AppSelect from './AppSelect.vue'

const props = defineProps<{ vehicleId: string; days: number }>()
const { t, locale } = useI18n()

/**
 * A step chosen from the range, so nobody has to know what a step is.
 *
 * Each range gets the coarsest step that still keeps a few hundred rows: fine
 * enough to see a drive, coarse enough that the server is not asked to build a
 * bucket per second across a month.
 */
function stepForRange(days: number): number {
  if (days <= 1) return 300
  if (days <= 7) return 3600
  return 21600
}

const table = ref<HistoryTable | null>(null)
const stepSeconds = ref(stepForRange(props.days))
const offset = ref(0)
const limit = ref(100)
const loading = ref(false)
const error = ref('')

const rows = computed(() => table.value?.rows ?? [])
const total = computed(() => table.value?.total ?? 0)
const rangeStart = computed(() => (total.value ? offset.value + 1 : 0))
const rangeEnd = computed(() => Math.min(offset.value + limit.value, total.value))

/**
 * Every metric any visible row knows about, ordered so the table does not
 * reshuffle its columns as the reader pages through it.
 */
const discovered = computed(() => {
  const keys = new Set<string>()
  for (const row of rows.value) for (const key of Object.keys(row.readings)) keys.add(key)
  return [...keys]
    .map((key) => metricDefinition(key))
    .sort((left, right) => metricLabel(left, t).localeCompare(metricLabel(right, t), locale.value))
})
const storageKey = computed(() => `carhibou.timeline-columns.${props.vehicleId}`)
const choices = computed(() => discovered.value.map((definition) => ({
  key: definition.key,
  label: metricLabel(definition, t),
  hint: definition.key,
})))
const { preference, ordered, visible, hiddenCount, load: loadColumns, toggle: toggleColumn, move: moveColumn, reset: resetColumns } =
  useColumnPreference(storageKey, choices)
const byKey = computed(() => new Map(discovered.value.map((definition) => [definition.key, definition])))
const columns = computed(() => visible.value.flatMap((choice) => {
  const definition = byKey.value.get(choice.key)
  return definition ? [definition] : []
}))
watch(() => props.vehicleId, () => { loadColumns() }, { immediate: true })

const stepOptions = computed(() => TABLE_STEP_SECONDS.map((seconds) => ({
  value: seconds,
  label: formatSpan(seconds, locale.value),
})))

function instant(value: string): string {
  return new Date(value).toLocaleString(locale.value)
}

/**
 * Whether a reading was carried into this row rather than measured in it.
 *
 * The server forward-fills the last known value, so an observation older than
 * the bucket it appears in is a value that has simply not changed hands since.
 * Saying so is the difference between "42 km/h now" and "42 km/h, an hour ago".
 */
function carried(row: HistoryTableRow, reading: Reading): boolean {
  return new Date(reading.observed_at).getTime() < new Date(row.bucket_start).getTime()
}

/**
 * How much older than its row a carried value is.
 *
 * An interval between two stored instants, not an age: the row is itself in the
 * past, so "21 minutes ago" would be a claim about now that nothing supports.
 * The anchor is the row's own time, in the first column of the same row.
 */
function carriedEarlier(row: HistoryTableRow, reading: Reading): string {
  const seconds = Math.max(0, Math.round(
    (new Date(row.bucket_end).getTime() - new Date(reading.observed_at).getTime()) / 1000,
  ))
  return t('history.carriedEarlier', { span: formatSpan(seconds, locale.value) })
}

/**
 * Whether anything in this row was actually received inside it.
 *
 * Rows are born at changes in what is known, which is not the same as rows being
 * born at reports: a value expiring changes what is known just as much as a new
 * reading does, and the range's own edge is always shown. A row nothing was
 * reported into is one of those, and it reads as a data error unless the
 * table says so. The server counts the samples recorded inside each row's span,
 * summed when rows collapse, so even a report whose values had all expired by
 * the bucket's end is still its row's anchor.
 */
function reportAnchored(row: HistoryTableRow): boolean {
  return row.reports > 0
}

/**
 * The newest row when it stands at the end of the range rather than at a report.
 *
 * Its time is the instant the range was asked for, so printing a wall clock
 * there implies the car said something then. It says "now" instead.
 */
function atRangeEdge(row: HistoryTableRow, index: number): boolean {
  if (index !== 0 || !table.value) return false
  const edge = new Date(table.value.end).getTime()
  const closed = new Date(row.bucket_end).getTime()
  return Math.abs(edge - closed) < stepSeconds.value * 1000 && !reportAnchored(row)
}

function whenLabel(row: HistoryTableRow, index: number): string {
  return atRangeEdge(row, index) ? t('history.rowNow') : instant(row.bucket_end)
}

function whyRow(row: HistoryTableRow, index: number): string {
  if (atRangeEdge(row, index)) return t('history.rowEdgeReason')
  return reportAnchored(row) ? '' : t('history.rowExpiryReason')
}

function display(key: string, reading: Reading): string {
  const definition = metricDefinition(key)
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  if (typeof reading.value === 'number') return formatMetricNumber(reading.value, definition, locale.value)
  return reading.value === null || reading.value === undefined ? '—' : String(reading.value)
}

function position(row: HistoryTableRow): string {
  return row.position ? formatCoordinates(row.position.latitude, row.position.longitude) : '—'
}

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  const end = new Date()
  const start = new Date(end.getTime() - props.days * 86_400_000)
  try {
    table.value = await loadHistoryTable(props.vehicleId, {
      start, end, stepSeconds: stepSeconds.value, limit: limit.value, offset: offset.value,
    })
  } catch (reason) {
    error.value = errorMessage(reason, t('common.error'))
    table.value = null
  } finally {
    loading.value = false
  }
}

// A coarser step means fewer, wider rows, so the page the reader was on no
// longer means anything; the same is true of a different range or vehicle.
watch([stepSeconds, () => props.vehicleId], () => { offset.value = 0; void load() })
// A step chosen for one day is wrong for a month, and a one-second step across
// thirty days asks the server for millions of buckets, so the range re-picks it.
watch(() => props.days, (days) => {
  offset.value = 0
  const next = stepForRange(days)
  if (next === stepSeconds.value) void load()
  else stepSeconds.value = next
})
watch(offset, load)
void load()
</script>

<template>
  <section class="panel history-table">
    <header class="table-head">
      <div>
        <h2>{{ t('history.tableTitle') }}<AppHelp :label="t('history.agedHelpLabel')"><span>{{ t('history.agedHelp') }}</span></AppHelp></h2>
        <p>{{ t('history.tableHint') }}</p>
      </div>
      <div class="table-tools">
        <ColumnPicker :columns="ordered" :preference="preference" :hidden-count="hiddenCount" @toggle="toggleColumn" @move="moveColumn" @reset="resetColumns" />
      </div>
      <label class="field inline-field"><span>{{ t('history.rowEvery') }}</span>
        <AppSelect v-model="stepSeconds" :aria-label="t('history.rowEvery')">
          <option v-for="option in stepOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </AppSelect>
      </label>
    </header>

    <p v-if="error" class="error table-message" role="alert">{{ error }}</p>
    <p v-else-if="!rows.length" class="empty-note">{{ loading ? t('common.loading') : t('history.noData') }}</p>

    <div v-else class="table-wrap timeline-scroll">
      <table class="table snapshot">
        <thead>
          <tr>
            <th scope="col">{{ t('history.columns.recordedAt') }}</th>
            <th scope="col">{{ t('history.columns.position') }}</th>
            <th v-for="definition in columns" :key="definition.key" scope="col">
              {{ metricLabel(definition, t) }}<small v-if="definition.unit"> ({{ definition.unit }})</small>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="row.bucket_start">
            <td class="snapshot-when">
              <span :class="{ 'is-derived': !reportAnchored(row) }" :title="whyRow(row, index)">{{ whenLabel(row, index) }}</span>
              <!-- One row can stand for many identical buckets. Saying how many
                   is what stops a quiet night reading as a single moment. -->
              <small v-if="row.collapsed_buckets > 1">{{ t('history.unchangedFor', { span: formatSpan(row.collapsed_buckets * stepSeconds, locale) }) }}</small>
            </td>
            <td class="mono">{{ position(row) }}</td>
            <td v-for="definition in columns" :key="definition.key">
              <template v-if="row.readings[definition.key]">
                <span :class="{ 'is-carried': carried(row, row.readings[definition.key]!) }" :title="instant(row.readings[definition.key]!.observed_at)">
                  {{ display(definition.key, row.readings[definition.key]!) }}
                </span>
                <small v-if="carried(row, row.readings[definition.key]!)" class="carried-age">{{ carriedEarlier(row, row.readings[definition.key]!) }}</small>
              </template>
              <span v-else class="absent">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <footer v-if="rows.length" class="table-foot">
      <span class="muted">{{ t('history.entryRange', { from: rangeStart, to: rangeEnd, total }) }}</span>
      <div class="table-pager">
        <button class="button secondary" type="button" :disabled="offset === 0 || loading" @click="offset = Math.max(0, offset - limit)">{{ t('history.previous') }}</button>
        <button class="button secondary" type="button" :disabled="rangeEnd >= total || loading" @click="offset = offset + limit">{{ t('history.next') }}</button>
      </div>
    </footer>
  </section>
</template>

<style scoped>
.history-table{overflow:hidden}
.table-head{display:flex;align-items:flex-end;justify-content:space-between;flex-wrap:wrap;gap:14px;padding:14px 16px;border-bottom:1px solid var(--line)}
.table-tools{display:flex;align-items:center;gap:8px;margin-left:auto}
/* The same window the raw table gives its rows, so switching modes does not
   change how much of the page the table claims. */
.timeline-scroll{max-height:520px;overflow:auto}
.snapshot thead th{position:sticky;top:0;z-index:1;background:var(--panel)}
.table-head h2{margin:0;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em}
.table-head p{max-width:64ch;margin:4px 0 0;color:var(--muted);font-size:var(--font-caption);line-height:1.45}
.inline-field{width:170px}
.table-message{padding:14px 16px}
.snapshot{font-variant-numeric:tabular-nums;white-space:nowrap}
.snapshot th small{color:var(--muted);font-weight:400}
.snapshot-when{white-space:nowrap}
.snapshot-when small{display:block;margin-top:2px;color:var(--muted);font-size:var(--font-micro)}
/* A row nothing was reported into still has a real time; muting it says the time
   is the row's, not a moment the car spoke. */
.is-derived{color:var(--muted)}
/* A carried value is real but old. Dimming it and naming its age is what keeps
   a forward-filled cell from reading as a fresh measurement. */
.is-carried{color:var(--muted)}
.carried-age{display:block;margin-top:2px;color:var(--muted-2);font-size:var(--font-micro)}
.absent{color:var(--muted-2)}
.table-foot{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:11px 16px;border-top:1px solid var(--line)}
.table-pager{display:flex;align-items:center;gap:8px}
@media(max-width:700px){.table-head{align-items:stretch;flex-direction:column}.inline-field{width:100%}}
</style>
