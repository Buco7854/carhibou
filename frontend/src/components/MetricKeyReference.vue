<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import { loadMetricKeys, metricKeyStatus, metricKeys, positionDescriptor } from '../metricRegistry'
import { formatSpan, metricDefinition } from '../vehicleDisplay'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ close: [] }>()
const { t, te, locale } = useI18n()
const query = ref('')
const copied = ref('')

watch(
  () => props.open,
  (open) => {
    if (!open) return
    query.value = ''
    copied.value = ''
    void loadMetricKeys()
  },
  { immediate: true },
)

/** The catalogue's display name, when this key is one the interface renders. */
function label(key: string): string {
  const known = metricDefinition(key).labelKey
  return known ? t(known) : ''
}

/** Server vocabulary, translated when known and shown as it came when not. */
function term(namespace: string, value: string): string {
  const key = `metricKeys.${namespace}.${value}`
  return te(key) ? t(key) : value
}

/*
 * A fix is the one thing Carhibou understands that the registry cannot list as a
 * metric, because its fields are only true together. It is pinned above them
 * rather than explained away in a footnote: the rule editor accepts these as
 * targets, so an author looking for them has to find them here.
 *
 * Everything shown comes from the server's descriptor. A server that does not
 * send one gets no entry at all, which is honest, where a copy kept here would
 * quietly go stale.
 */
const fix = computed(() => {
  const descriptor = positionDescriptor.value
  if (!descriptor) return null
  return {
    meaning: descriptor.meaning,
    // The registry names a field; the rule editor takes it namespaced.
    fields: descriptor.fields.map((entry) => ({ ...entry, target: `position.${entry.key}` })),
  }
})

const positionMatches = computed(() => {
  const current = fix.value
  if (!current) return false
  const needle = query.value.trim().toLowerCase()
  if (!needle) return true
  return 'position'.includes(needle) ||
    current.meaning.toLowerCase().includes(needle) ||
    current.fields.some((field) =>
      field.target.toLowerCase().includes(needle) || field.meaning.toLowerCase().includes(needle))
})

const rows = computed(() => {
  const needle = query.value.trim().toLowerCase()
  return metricKeys.value
    .map((entry) => ({ ...entry, label: label(entry.key) }))
    .filter((entry) =>
      !needle ||
      entry.key.toLowerCase().includes(needle) ||
      entry.label.toLowerCase().includes(needle) ||
      entry.meaning.toLowerCase().includes(needle),
    )
})

async function copy(key: string): Promise<void> {
  try {
    await navigator.clipboard?.writeText(key)
    copied.value = key
  } catch {
    // Clipboard access can be refused, and the key is on screen to be read
    // either way, so a refusal is not worth an error message.
  }
}
</script>

<template>
  <AppModal :open="open" :title="t('metricKeys.title')" wide @close="emit('close')">
    <div class="key-reference">
      <p class="reference-intro">{{ t('metricKeys.intro') }}</p>

      <label class="field search-field">
        <span>{{ t('metricKeys.search') }}</span>
        <input v-model="query" class="input" type="search" :placeholder="t('metricKeys.searchPlaceholder')" />
      </label>

      <p v-if="metricKeyStatus === 'loading'" class="reference-note">{{ t('metricKeys.loading') }}</p>

      <div v-else-if="metricKeyStatus === 'error'" class="reference-note error-note" role="alert">
        <p>{{ t('metricKeys.unavailable') }}</p>
        <button class="button secondary" type="button" @click="loadMetricKeys(true)">{{ t('metricKeys.retry') }}</button>
      </div>

      <template v-else>
        <p class="reference-count" aria-live="polite">{{ t('metricKeys.count', { count: rows.length }) }}</p>

        <section v-if="fix && positionMatches" class="position-entry">
          <div class="key-head">
            <code class="key-name">position</code>
            <span class="key-kind">{{ t('metricKeys.position.kind') }}</span>
            <span class="key-label">{{ t('metricKeys.position.label') }}</span>
          </div>
          <p class="key-meaning">{{ fix.meaning }}</p>
          <ul class="position-fields">
            <li v-for="field in fix.fields" :key="field.key">
              <code>{{ field.target }}</code>
              <span v-if="field.unit" class="field-unit">{{ field.unit }}</span>
              <span class="field-meaning">{{ field.meaning }}</span>
              <button class="icon-button" type="button" :aria-label="t('metricKeys.copy', { key: field.target })" @click="copy(field.target)">
                <AppIcon :name="copied === field.target ? 'check' : 'copy'" :size="13" />
              </button>
            </li>
          </ul>
        </section>
        <ul v-if="rows.length" class="key-list">
          <li v-for="entry in rows" :key="entry.key">
            <div class="key-head">
              <code class="key-name">{{ entry.key }}</code>
              <span v-if="entry.unit" class="key-unit">{{ entry.unit }}</span>
              <span v-if="entry.label" class="key-label">{{ entry.label }}</span>
              <button class="icon-button" type="button" :aria-label="t('metricKeys.copy', { key: entry.key })" @click="copy(entry.key)">
                <AppIcon :name="copied === entry.key ? 'check' : 'copy'" :size="14" />
              </button>
            </div>
            <p class="key-meaning">{{ entry.meaning }}</p>
            <p class="key-facts">
              <span>{{ term('kind', entry.kind) }}</span>
              <span>{{ term('type', entry.value_type) }}</span>
              <span>{{ t('metricKeys.freshness', { span: formatSpan(entry.freshness_seconds, locale) }) }}</span>
              <span>{{ entry.retained ? t('metricKeys.retained') : t('metricKeys.notRetained') }}</span>
            </p>
          </li>
        </ul>
        <p v-else class="reference-note">{{ t('metricKeys.noMatch', { query: query.trim() }) }}</p>
      </template>
    </div>
  </AppModal>
</template>

<style scoped>
.key-reference{display:grid;gap:12px}
.reference-intro{margin:0;color:var(--muted);font-size:var(--font-caption);line-height:1.5;max-width:74ch}
.search-field{max-width:340px}
.reference-note{margin:0;color:var(--muted);font-size:var(--font-caption)}
.error-note{display:grid;justify-items:start;gap:9px}
.reference-count{margin:0;color:var(--muted-2);font-size:var(--font-micro)}

/* A fix is a different kind of thing from the rows below it, so it is set off
   rather than dressed as the first of them. */
.position-entry{display:grid;gap:5px;padding:11px 12px;background:var(--panel-2);border:1px solid var(--line);border-radius:var(--radius)}
.key-kind{padding:1px 6px;color:var(--accent);background:var(--accent-soft);border-radius:999px;font-size:var(--font-micro);font-weight:500}
/* Each field carries its own unit and meaning, so they read as a short list
   rather than as a row of bare names. */
.position-fields{list-style:none;display:grid;gap:2px;margin:0;padding:0}
.position-fields li{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px}
.position-fields .field-unit{color:var(--muted);font-size:var(--font-micro)}
.position-fields .field-meaning{flex:1 1 12ch;min-width:0;color:var(--muted);font-size:var(--font-micro)}
.position-fields code{font-family:var(--mono);font-size:var(--font-micro)}
.position-fields .icon-button{width:20px;height:20px}

.key-list{list-style:none;display:grid;gap:1px;margin:0;padding:0}
.key-list li{display:grid;gap:3px;padding:10px 2px;border-top:1px solid var(--line)}
.key-head{display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.key-name{font-family:var(--mono);font-size:var(--font-body);font-weight:500}
.key-unit{color:var(--muted);font-size:var(--font-caption)}
.key-label{color:var(--muted);font-size:var(--font-caption)}
.key-head .icon-button{width:24px;height:24px;margin-left:auto}
.key-meaning{margin:0;font-size:var(--font-caption);line-height:1.45}
/* Four short facts read as a row of chips, not as a sentence they do not form.
   They wrap on a phone, which is why the spacing separates them rather than a
   character that would then start a line on its own. */
.key-facts{display:flex;flex-wrap:wrap;gap:4px 16px;margin:0;color:var(--muted);font-size:var(--font-micro)}
.key-facts span{white-space:nowrap}
</style>
