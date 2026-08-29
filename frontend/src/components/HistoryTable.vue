<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { errorMessage } from '../api/client'
import { TABLE_STEP_SECONDS, loadHistoryTable } from '../api/segments'
import type { HistoryTable, HistoryTableRow, Reading } from '../api/types'
import { formatAge, formatMetricNumber, formatSpan, metricDefinition, metricLabel } from '../vehicleDisplay'
import AppSelect from './AppSelect.vue'

const props = defineProps<{ vehicleId: string; days: number }>()
const { t, locale } = useI18n()

const table = ref<HistoryTable | null>(null)
const stepSeconds = ref(60)
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
const columns = computed(() => {
  const keys = new Set<string>()
  for (const row of rows.value) for (const key of Object.keys(row.readings)) keys.add(key)
  return [...keys]
    .map((key) => metricDefinition(key))
    .sort((left, right) => metricLabel(left, t).localeCompare(metricLabel(right, t), locale.value))
})

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

function age(row: HistoryTableRow, reading: Reading): string {
  const seconds = Math.max(0, Math.round(
    (new Date(row.bucket_end).getTime() - new Date(reading.observed_at).getTime()) / 1000,
  ))
  return formatAge(seconds, locale.value)
}

function display(key: string, reading: Reading): string {
  const definition = metricDefinition(key)
  if (typeof reading.value === 'boolean') return t(reading.value ? 'metrics.active' : 'metrics.inactive')
  if (typeof reading.value === 'number') return formatMetricNumber(reading.value, definition)
  return reading.value === null || reading.value === undefined ? '—' : String(reading.value)
}

function position(row: HistoryTableRow): string {
  return row.position ? `${row.position.latitude.toFixed(5)}, ${row.position.longitude.toFixed(5)}` : '—'
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
watch([stepSeconds, () => props.days, () => props.vehicleId], () => { offset.value = 0; void load() })
watch(offset, load)
void load()
</script>

<template>
  <section class="panel history-table">
    <header class="table-head">
      <div>
        <h2>{{ t('history.tableTitle') }}</h2>
        <p>{{ t('history.tableHint') }}</p>
      </div>
      <label class="field inline-field"><span>{{ t('history.resolution') }}</span>
        <AppSelect v-model="stepSeconds" :aria-label="t('history.resolution')">
          <option v-for="option in stepOptions" :key="option.value" :value="option.value">{{ option.label }}</option>
        </AppSelect>
      </label>
    </header>

    <p v-if="error" class="error table-message" role="alert">{{ error }}</p>
    <p v-else-if="!rows.length" class="empty-note">{{ loading ? t('common.loading') : t('history.noData') }}</p>

    <div v-else class="table-wrap">
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
          <tr v-for="row in rows" :key="row.bucket_start">
            <td class="snapshot-when">
              {{ instant(row.bucket_end) }}
              <!-- One row can stand for many identical buckets. Saying how many
                   is what stops a quiet night reading as a single moment. -->
              <small v-if="row.collapsed_buckets > 1">{{ t('history.unchangedFor', { count: row.collapsed_buckets }) }}</small>
            </td>
            <td class="mono">{{ position(row) }}</td>
            <td v-for="definition in columns" :key="definition.key">
              <template v-if="row.readings[definition.key]">
                <span :class="{ 'is-carried': carried(row, row.readings[definition.key]!) }" :title="carried(row, row.readings[definition.key]!) ? age(row, row.readings[definition.key]!) : instant(row.readings[definition.key]!.observed_at)">
                  {{ display(definition.key, row.readings[definition.key]!) }}
                </span>
                <small v-if="carried(row, row.readings[definition.key]!)" class="carried-age">{{ age(row, row.readings[definition.key]!) }}</small>
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
.table-head h2{margin:0;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em}
.table-head p{max-width:64ch;margin:4px 0 0;color:var(--muted);font-size:var(--font-caption);line-height:1.45}
.inline-field{width:170px}
.table-message{padding:14px 16px}
.snapshot{font-variant-numeric:tabular-nums;white-space:nowrap}
.snapshot th small{color:var(--muted);font-weight:400}
.snapshot-when{white-space:nowrap}
.snapshot-when small{display:block;margin-top:2px;color:var(--muted);font-size:var(--font-micro)}
/* A carried value is real but old. Dimming it and naming its age is what keeps
   a forward-filled cell from reading as a fresh measurement. */
.is-carried{color:var(--muted)}
.carried-age{display:block;margin-top:2px;color:var(--muted-2);font-size:var(--font-micro)}
.absent{color:var(--muted-2)}
.table-foot{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:12px;padding:11px 16px;border-top:1px solid var(--line)}
.table-pager{display:flex;align-items:center;gap:8px}
@media(max-width:700px){.table-head{align-items:stretch;flex-direction:column}.inline-field{width:100%}}
</style>
