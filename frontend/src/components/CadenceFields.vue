<script setup lang="ts">
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import {
  CADENCE_PRESETS,
  DEFAULT_DRIVING_HOURS,
  drivingDelaySeconds,
  formatDataVolume,
  formatDuration,
  monthlyUploadBytes,
  type Cadence,
} from '../agentCadence'

const props = defineProps<{ signalCount?: number }>()
const model = defineModel<Cadence>({ required: true })
const { t, locale } = useI18n()
const drivingHours = ref(DEFAULT_DRIVING_HOURS)

const active = computed(() => CADENCE_PRESETS.find((preset) =>
  preset.sampling_seconds === model.value.sampling_seconds
  && preset.upload_seconds === model.value.upload_seconds
  && preset.parked_sampling_seconds === model.value.parked_sampling_seconds
  && preset.parked_upload_seconds === model.value.parked_upload_seconds,
))

const estimate = computed(() => formatDataVolume(
  monthlyUploadBytes(model.value, props.signalCount ?? 0, drivingHours.value),
  locale.value,
))
const delay = computed(() => formatDuration(drivingDelaySeconds(model.value), locale.value))

const fields = [
  { key: 'sampling_seconds', labelKey: 'agents.samplingSeconds' },
  { key: 'upload_seconds', labelKey: 'agents.uploadSeconds' },
] as const

function set(key: keyof Cadence, value: number): void {
  model.value = { ...model.value, [key]: value }
}

function apply(preset: Cadence): void {
  const { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds } = preset
  model.value = { sampling_seconds, upload_seconds, parked_sampling_seconds, parked_upload_seconds }
}
</script>

<template>
  <div class="cadence">
    <div class="cadence-presets" role="group" :aria-label="t('agents.presets')">
      <button
        v-for="preset in CADENCE_PRESETS"
        :key="preset.key"
        type="button"
        :class="['preset', { active: active?.key === preset.key }]"
        :aria-pressed="active?.key === preset.key"
        @click="apply(preset)"
      >
        <strong>{{ t(`agents.preset.${preset.key}`) }}</strong>
        <small>{{ t('agents.presetSummary', { driving: preset.sampling_seconds, parked: preset.parked_sampling_seconds }) }}</small>
      </button>
    </div>

    <div class="cadence-states">
      <fieldset class="cadence-state">
        <legend>{{ t('agents.whileDriving') }}</legend>
        <div class="cadence-fields">
          <label v-for="field in fields" :key="field.key" class="field">
            <span>{{ t(field.labelKey) }}</span>
            <input :value="model[field.key]" class="input" type="number" min="1" max="86400" required @input="set(field.key, Number(($event.target as HTMLInputElement).value))" />
          </label>
        </div>
      </fieldset>
      <fieldset class="cadence-state">
        <legend>{{ t('agents.whileParked') }}</legend>
        <div class="cadence-fields">
          <label v-for="field in fields" :key="field.key" class="field">
            <span>{{ t(field.labelKey) }}</span>
            <input :value="model[`parked_${field.key}` as keyof Cadence]" class="input" type="number" min="1" max="86400" required @input="set(`parked_${field.key}` as keyof Cadence, Number(($event.target as HTMLInputElement).value))" />
          </label>
        </div>
      </fieldset>
    </div>

    <p class="field-hint">{{ t('agents.parkedHint') }}</p>
    <p class="field-hint">{{ t('agents.uploadHint') }}</p>

    <div class="cadence-estimate">
      <strong>{{ estimate }}</strong>
      <span>{{ t('agents.estimateHint') }}</span>
      <span class="cadence-delay">{{ t('agents.delayHint', { delay }) }}</span>
      <label class="driving-hours">
        <input v-model.number="drivingHours" class="input" type="number" min="0" max="24" step="0.5" :aria-label="t('agents.drivingHours')" />
        <span>{{ t('agents.drivingHours') }}</span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.cadence{display:grid;gap:12px}
.cadence-presets{display:grid;grid-template-columns:repeat(auto-fit,minmax(118px,1fr));gap:8px}
.preset{display:grid;gap:2px;padding:8px 10px;color:var(--text);background:var(--panel-2);border:1px solid transparent;border-radius:var(--radius);text-align:left;cursor:pointer}
.preset:hover{border-color:var(--line-strong)}
.preset.active{background:var(--accent-soft);border-color:var(--accent)}
.preset strong{font-size:12px;font-weight:600}
.preset small{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.cadence-states{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.cadence-state{min-width:0;margin:0;padding:10px 12px 12px;background:var(--panel-2);border-radius:var(--radius)}
.cadence-state legend{padding:0 5px;color:var(--muted);font-size:12px;font-weight:600}
.cadence-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.cadence-estimate{display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;color:var(--muted);font-size:12px}
.cadence-estimate strong{color:var(--text);font-size:14px;font-variant-numeric:tabular-nums}
.cadence-delay{padding-left:10px;border-left:1px solid var(--line)}
.driving-hours{display:flex;align-items:center;gap:6px;margin-left:auto}
.driving-hours .input{width:64px;min-height:28px;padding:3px 7px;font-size:12px}
</style>
