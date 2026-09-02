<script setup lang="ts">
import { useI18n } from 'vue-i18n'
import type { Vehicle } from '../api/types'
import AppSelect from './AppSelect.vue'
import CodeEditor from './CodeEditor.vue'

export interface HookDraft {
  name: string
  description: string
  enabled: boolean
  trigger_type: string
  vehicle_id: string | null
  source: string
  timeout_seconds: number
}

withDefaults(defineProps<{
  vehicles: Vehicle[]
  error?: string
  saving?: boolean
  formId?: string
  /** False when the parent supplies its own toolbar for enable/save/test. */
  standalone?: boolean
  /**
   * Creation, where the detail panel takes over the moment the hook exists.
   * Everything left out has a working default, so asking for it here would be
   * asking somebody to write Python in a sheet the size of a phone.
   */
  compact?: boolean
}>(), {
  error: '',
  saving: false,
  formId: '',
  standalone: true,
  compact: false,
})
const emit = defineEmits<{ save: []; reference: [] }>()
const form = defineModel<HookDraft>({ required: true })
const { t } = useI18n()
</script>

<template>
  <form :id="formId || undefined" class="hook-editor-form" @submit.prevent="emit('save')">
    <div :class="['form-grid', { 'single-column': compact }]">
      <!-- No autofocus: on a phone the keyboard would cover the sheet the
           instant it opened, before anything on it had been read. -->
      <label class="field"><span>{{ t('hooks.name') }}</span><input v-model="form.name" class="input" required /></label>
      <label v-if="!compact" class="field"><span>{{ t('hooks.vehicle') }}</span><AppSelect v-model="form.vehicle_id"><option :value="null">{{ t('hooks.allVehicles') }}</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
      <label class="field"><span>{{ t('hooks.description') }}</span><input v-model="form.description" class="input" /></label>
      <label v-if="!compact" class="field"><span>{{ t('hooks.timeout') }}</span><input v-model="form.timeout_seconds" class="input" type="number" min="1" max="120" /><small class="field-hint">{{ t('hooks.timeoutHint') }}</small></label>
    </div>

    <p v-if="compact" class="field-hint">{{ t('hooks.createHint') }}</p>

    <div v-if="!compact" class="field source-field">
      <div class="source-label">
        <span>{{ t('hooks.source') }}</span>
        <button class="link-button" type="button" @click="emit('reference')">{{ t('metricKeys.open') }}</button>
      </div>
      <CodeEditor v-model="form.source" :label="t('hooks.source')" />
      <small class="field-hint">
        {{ t('hooks.batchHint') }}<br>
        {{ t('hooks.sideEffectWarning') }}
      </small>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="standalone" class="editor-actions">
      <button class="button" :disabled="saving">{{ compact ? t('hooks.createAndEdit') : t('common.save') }}</button>
      <!-- Nothing to enable yet while the hook has no code of its own. -->
      <label v-if="!compact" class="inline-toggle"><input v-model="form.enabled" type="checkbox" /><span>{{ t('hooks.enabled') }}</span></label>
    </div>
  </form>
</template>

<style scoped>
.hook-editor-form{display:grid;gap:16px}
.form-grid.single-column{grid-template-columns:minmax(0,1fr)}
/* The keys go in the code directly below, so the way to look one up belongs on
   this label rather than somewhere else on the page. */
.source-label{display:flex;align-items:baseline;justify-content:space-between;gap:12px}
/* The wrapper takes the span out of .field's direct children, which is where
   the label styling is bound. */
.source-label>span{color:var(--text);font-size:var(--font-caption);font-weight:500}
.editor-actions{display:flex;align-items:center;gap:14px}
.inline-toggle{display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer}
.inline-toggle input{width:14px;height:14px;accent-color:var(--accent)}
</style>
