<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { CADENCE_PRESETS, formatDataVolume, monthlyUploadBytes } from '../trackerCadence'

export interface Cadence { sampling_seconds: number; upload_seconds: number }

const props = defineProps<{ signalCount?: number }>()
const model = defineModel<Cadence>({ required: true })
const { t, locale } = useI18n()

const active = computed(() => CADENCE_PRESETS.find(
  (preset) => preset.samplingSeconds === model.value.sampling_seconds
    && preset.uploadSeconds === model.value.upload_seconds,
))

const estimate = computed(() => formatDataVolume(
  monthlyUploadBytes(model.value.sampling_seconds, model.value.upload_seconds, props.signalCount ?? 0),
  locale.value,
))

function apply(samplingSeconds: number, uploadSeconds: number): void {
  model.value = { sampling_seconds: samplingSeconds, upload_seconds: uploadSeconds }
}
</script>

<template>
  <div class="cadence">
    <div class="cadence-presets" role="group" :aria-label="t('devices.presets')">
      <button
        v-for="preset in CADENCE_PRESETS"
        :key="preset.key"
        type="button"
        :class="['preset', { active: active?.key === preset.key }]"
        :aria-pressed="active?.key === preset.key"
        @click="apply(preset.samplingSeconds, preset.uploadSeconds)"
      >
        <strong>{{ t(`devices.preset.${preset.key}`) }}</strong>
        <small>{{ t('devices.cadenceValue', { sampling: preset.samplingSeconds, upload: preset.uploadSeconds }) }}</small>
      </button>
    </div>

    <div class="cadence-fields">
      <label class="field"><span>{{ t('devices.samplingSeconds') }}</span><input :value="model.sampling_seconds" class="input" type="number" min="1" max="86400" required @input="apply(Number(($event.target as HTMLInputElement).value), model.upload_seconds)" /></label>
      <label class="field"><span>{{ t('devices.uploadSeconds') }}</span><input :value="model.upload_seconds" class="input" type="number" min="1" max="86400" required @input="apply(model.sampling_seconds, Number(($event.target as HTMLInputElement).value))" /></label>
    </div>

    <p class="cadence-estimate">
      <strong>{{ estimate }}</strong>
      <span>{{ t('devices.estimateHint') }}</span>
    </p>
  </div>
</template>

<style scoped>
.cadence{display:grid;gap:12px}
.cadence-presets{display:grid;grid-template-columns:repeat(auto-fit,minmax(112px,1fr));gap:8px}
.preset{display:grid;gap:2px;padding:8px 10px;color:var(--text);background:var(--panel-2);border:1px solid transparent;border-radius:var(--radius);text-align:left;cursor:pointer}
.preset:hover{border-color:var(--line-strong)}
.preset.active{background:var(--accent-soft);border-color:var(--accent)}
.preset strong{font-size:12px;font-weight:600}
.preset small{color:var(--muted);font-size:11px;font-variant-numeric:tabular-nums}
.cadence-fields{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}
.cadence-estimate{display:flex;align-items:baseline;flex-wrap:wrap;gap:6px;margin:0;color:var(--muted);font-size:12px}
.cadence-estimate strong{color:var(--text);font-size:13px;font-variant-numeric:tabular-nums}
</style>
