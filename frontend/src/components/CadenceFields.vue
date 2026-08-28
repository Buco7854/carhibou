<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import AppIcon from './AppIcon.vue'
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
const customOpen = ref(false)

const active = computed(() => CADENCE_PRESETS.find((preset) =>
  preset.sampling_seconds === model.value.sampling_seconds
  && preset.upload_seconds === model.value.upload_seconds
  && preset.parked_sampling_seconds === model.value.parked_sampling_seconds
  && preset.parked_upload_seconds === model.value.parked_upload_seconds,
))

// Intervals that match no preset are the reason somebody opened this, so the
// exact seconds are already showing when the form loads on them.
watch(active, (preset) => { if (!preset) customOpen.value = true }, { immediate: true })

const summary = computed(() => active.value
  ? t('agents.presetSummary', { driving: active.value.sampling_seconds, parked: active.value.parked_sampling_seconds })
  : t('agents.presetSummary', { driving: model.value.sampling_seconds, parked: model.value.parked_sampling_seconds }))

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
    <!-- Five named presets read as one control. Spelling each one out as a card
         with its own intervals made the choice look like five settings. -->
    <div class="cadence-presets" role="group" :aria-label="t('agents.presets')">
      <button
        v-for="preset in CADENCE_PRESETS"
        :key="preset.key"
        type="button"
        :class="['preset', { active: active?.key === preset.key }]"
        :aria-pressed="active?.key === preset.key"
        @click="apply(preset)"
      >{{ t(`agents.preset.${preset.key}`) }}</button>
    </div>
    <p class="cadence-summary">
      <strong v-if="!active">{{ t('agents.customCadence') }}</strong>{{ summary }}
    </p>

    <button class="cadence-disclosure" type="button" :aria-expanded="customOpen" aria-controls="cadence-custom" @click="customOpen = !customOpen">
      {{ t('agents.customIntervals') }}<AppIcon name="chevron-down" :size="14" />
    </button>
    <div v-if="customOpen" id="cadence-custom" class="cadence-custom">
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
    </div>

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
.cadence{display:grid;gap:10px}
.cadence-presets{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:3px;padding:3px;background:var(--panel-2);border-radius:var(--radius)}
.preset{min-width:0;padding:6px 4px;color:var(--muted);background:transparent;border:0;border-radius:var(--radius-sm);font-size:var(--font-caption);font-weight:500;cursor:pointer;transition:color .12s,background-color .12s}
.preset:hover{color:var(--text)}
.preset.active{color:var(--accent);background:var(--panel);box-shadow:var(--shadow-soft)}
.cadence-summary{margin:0;color:var(--muted);font-size:var(--font-caption);font-variant-numeric:tabular-nums}
.cadence-summary strong{margin-right:6px;color:var(--text);font-weight:500}
.cadence-disclosure{justify-self:start;display:inline-flex;align-items:center;gap:5px;padding:0;color:var(--accent);background:none;border:0;font-size:var(--font-caption);cursor:pointer}
.cadence-disclosure .app-icon{transition:transform .12s}
.cadence-disclosure[aria-expanded="true"] .app-icon{transform:rotate(180deg)}
.cadence-custom{display:grid;gap:10px}
.cadence-states{display:grid;grid-template-columns:repeat(auto-fit,minmax(228px,1fr));gap:10px}
.cadence-state{min-width:0;margin:0;padding:9px 11px 11px;background:var(--panel-2);border:0;border-radius:var(--radius)}
.cadence-state legend{padding:0 4px;color:var(--muted);font-size:var(--font-caption);font-weight:600}
.cadence-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}
.cadence-estimate{display:flex;align-items:center;flex-wrap:wrap;gap:6px 10px;color:var(--muted);font-size:var(--font-caption)}
.cadence-estimate strong{color:var(--text);font-size:var(--font-body);font-variant-numeric:tabular-nums}
.cadence-delay{padding-left:10px;border-left:1px solid var(--line)}
.driving-hours{display:flex;align-items:center;gap:6px;margin-left:auto}
.driving-hours .input{width:64px;min-height:28px;padding:3px 7px;font-size:var(--font-caption)}
@media(max-width:520px){.cadence-presets{grid-template-columns:repeat(3,minmax(0,1fr))}}
</style>