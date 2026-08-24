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
  saved?: boolean
  saving?: boolean
  testing?: boolean
  showTest?: boolean
}>(), {
  error: '',
  saved: false,
  saving: false,
  testing: false,
  showTest: false,
})
const emit = defineEmits<{ save: []; test: [] }>()
const form = defineModel<HookDraft>({ required: true })
const { t } = useI18n()
</script>

<template>
  <form class="hook-editor-form" @submit.prevent="emit('save')">
    <div class="form-grid">
      <label class="field"><span>{{ t('hooks.name') }}</span><input v-model="form.name" class="input" required autofocus /></label>
      <label class="field"><span>{{ t('hooks.vehicle') }}</span><AppSelect v-model="form.vehicle_id"><option :value="null">{{ t('hooks.allVehicles') }}</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect></label>
      <label class="field"><span>{{ t('hooks.description') }}</span><input v-model="form.description" class="input" /></label>
      <label class="field"><span>{{ t('hooks.timeout') }}</span><input v-model="form.timeout_seconds" class="input" type="number" min="1" max="120" /><small class="field-hint">{{ t('hooks.timeoutHint') }}</small></label>
    </div>
    <label class="toggle"><input v-model="form.enabled" type="checkbox" /><span>{{ t('hooks.enabled') }}</span></label>
    <div class="field"><span>{{ t('hooks.source') }}</span><CodeEditor v-model="form.source" /></div>
    <p v-if="error" class="error">{{ error }}</p>
    <div class="form-actions">
      <button class="button" :disabled="saving">{{ saved ? '✓' : t('common.save') }}</button>
      <button v-if="showTest" class="button secondary" type="button" :disabled="testing" @click="emit('test')">{{ t('hooks.test') }}</button>
    </div>
    <p v-if="showTest" class="side-effect-warning">{{ t('hooks.sideEffectWarning') }}</p>
  </form>
</template>

<style scoped>
.hook-editor-form{display:grid;gap:15px}.field-hint{color:var(--muted);font-size:9px;line-height:1.45}.toggle{display:flex;align-items:center;gap:8px;font-size:11px}.side-effect-warning{margin:0;color:var(--warning);font-size:10px}.form-actions{justify-content:flex-start}
</style>
