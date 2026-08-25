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
}>(), {
  error: '',
  saving: false,
  formId: '',
  standalone: true,
})
const emit = defineEmits<{ save: [] }>()
const form = defineModel<HookDraft>({ required: true })
const { t } = useI18n()
</script>

<template>
  <form :id="formId || undefined" class="hook-editor-form" @submit.prevent="emit('save')">
    <div class="form-grid">
      <label class="field"><span>{{ t('hooks.name') }}</span><input v-model="form.name" class="input" required autofocus /></label>
      <label class="field"><span>{{ t('hooks.vehicle') }}</span><AppSelect v-model="form.vehicle_id"><option :value="null">{{ t('hooks.allVehicles') }}</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
      <label class="field"><span>{{ t('hooks.description') }}</span><input v-model="form.description" class="input" /></label>
      <label class="field"><span>{{ t('hooks.timeout') }}</span><input v-model="form.timeout_seconds" class="input" type="number" min="1" max="120" /><small class="field-hint">{{ t('hooks.timeoutHint') }}</small></label>
    </div>

    <div class="field source-field">
      <span>{{ t('hooks.source') }}</span>
      <CodeEditor v-model="form.source" />
      <small class="field-hint">
        {{ t('hooks.batchHint') }}<br>
        {{ t('hooks.sideEffectWarning') }}
      </small>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="standalone" class="editor-actions">
      <button class="button" :disabled="saving">{{ t('common.save') }}</button>
      <label class="inline-toggle"><input v-model="form.enabled" type="checkbox" /><span>{{ t('hooks.enabled') }}</span></label>
    </div>
  </form>
</template>

<style scoped>
.hook-editor-form{display:grid;gap:16px}
.editor-actions{display:flex;align-items:center;gap:14px}
.inline-toggle{display:flex;align-items:center;gap:7px;font-size:13px;cursor:pointer}
.inline-toggle input{width:14px;height:14px;accent-color:var(--accent)}
</style>
