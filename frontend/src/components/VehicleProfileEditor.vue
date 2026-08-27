<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { ProfileDataType, VehicleProfile } from '../api/types'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import AppSelect from './AppSelect.vue'

interface SignalDraft {
  name: string
  display_name: string
  can_id: string
  byte_offset: number
  data_type: ProfileDataType
  endianness: 'big' | 'little'
  scale: number
  offset: number
  unit: string
  minimum: string
  maximum: string
}

const props = defineProps<{ open: boolean; profile?: VehicleProfile | null; clone?: boolean }>()
const emit = defineEmits<{ saved: []; close: [] }>()
const { t } = useI18n()
const saving = ref(false)
const error = ref('')
const signalError = ref('')
const signalOpen = ref(false)
const signalIndex = ref<number | null>(null)
const form = ref({ name: '', description: '', signals: [] as SignalDraft[] })
const signal = ref<SignalDraft>(blankSignal())
const editing = computed(() => Boolean(props.profile) && !props.clone)
const dataTypes: ProfileDataType[] = ['uint8', 'uint16', 'uint32', 'int8', 'int16', 'int32', 'boolean', 'bytes']

function blankSignal(): SignalDraft {
  return { name: '', display_name: '', can_id: '', byte_offset: 0, data_type: 'uint8', endianness: 'big', scale: 1, offset: 0, unit: '', minimum: '', maximum: '' }
}

function profileSignals(profile: VehicleProfile): SignalDraft[] {
  return (profile.definition.signals ?? []).map((item) => ({
    name: item.name,
    display_name: item.display_name ?? '',
    can_id: `0x${item.source.can_id.toString(16).toUpperCase()}`,
    byte_offset: item.decoder.byte_offset,
    data_type: item.decoder.data_type,
    endianness: item.decoder.endianness ?? 'big',
    scale: item.decoder.scale ?? 1,
    offset: item.decoder.offset ?? 0,
    unit: item.unit ?? '',
    minimum: item.minimum === null || item.minimum === undefined ? '' : String(item.minimum),
    maximum: item.maximum === null || item.maximum === undefined ? '' : String(item.maximum),
  }))
}

function reset(): void {
  form.value = props.profile
    ? { name: props.clone ? t('profiles.cloneName', { name: props.profile.name }) : props.profile.name, description: props.profile.description, signals: profileSignals(props.profile) }
    : { name: '', description: '', signals: [] }
  error.value = ''
  signalError.value = ''
  signalOpen.value = false
  signalIndex.value = null
}

function close(): void {
  if (signalOpen.value) {
    signalOpen.value = false
    return
  }
  emit('close')
}

function editSignal(index?: number): void {
  signalIndex.value = index ?? null
  signal.value = index === undefined ? blankSignal() : { ...form.value.signals[index]! }
  signalError.value = ''
  signalOpen.value = true
}

function saveSignal(): void {
  signalError.value = ''
  if (!signal.value.name.trim() || !Number.isInteger(Number(signal.value.can_id))) {
    signalError.value = t('profiles.invalidSignal')
    return
  }
  const next = { ...signal.value, name: signal.value.name.trim(), display_name: signal.value.display_name.trim() }
  if (signalIndex.value === null) form.value.signals.push(next)
  else form.value.signals[signalIndex.value] = next
  signalOpen.value = false
}

function removeSignal(index: number): void { form.value.signals.splice(index, 1) }
function numberOrNull(value: string): number | null { return value.trim() === '' ? null : Number(value) }

async function save(): Promise<void> {
  error.value = ''
  if (!form.value.signals.length) {
    error.value = t('profiles.noSignals')
    return
  }
  const signals = form.value.signals.map((item) => ({
    name: item.name,
    display_name: item.display_name,
    source: { type: 'can', can_id: Number(item.can_id) },
    decoder: {
      byte_offset: item.byte_offset,
      data_type: item.data_type,
      endianness: item.endianness,
      scale: item.scale,
      offset: item.offset,
      ...(item.data_type === 'bytes' ? { length: 1 } : {}),
      ...(item.data_type === 'boolean' ? { bit: 0 } : {}),
    },
    unit: item.unit.trim() || null,
    minimum: numberOrNull(item.minimum),
    maximum: numberOrNull(item.maximum),
  }))
  saving.value = true
  try {
    await api(editing.value ? `/vehicle-profiles/${props.profile!.id}` : '/vehicle-profiles', {
      method: editing.value ? 'PUT' : 'POST',
      body: JSON.stringify({ name: form.value.name.trim(), description: form.value.description.trim(), type: 'can', signals, computed_metrics: [] }),
    })
    emit('saved')
    emit('close')
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('common.error')
  } finally {
    saving.value = false
  }
}

watch(() => [props.open, props.profile?.id, props.clone] as const, ([open]) => { if (open) reset() }, { immediate: true })
</script>

<template>
  <AppModal :open="open" :inactive="signalOpen" :title="editing ? t('profiles.editTitle') : t('profiles.createTitle')" wide @close="close">
    <form class="profile-editor" @submit.prevent="save">
      <div class="profile-details">
        <label class="field"><span>{{ t('profiles.name') }}</span><input v-model="form.name" class="input" required autofocus /></label>
        <label class="field"><span>{{ t('profiles.description') }}</span><textarea v-model="form.description" class="textarea" rows="3" /></label>
      </div>

      <section class="signal-section">
        <header>
          <div><h3>{{ t('profiles.signalsTitle') }}</h3><p>{{ t('profiles.signalsHint') }}</p></div>
          <button class="button secondary" type="button" @click="editSignal()"><AppIcon name="plus" :size="14" />{{ t('profiles.addSignal') }}</button>
        </header>
        <div class="signal-rows">
          <article v-for="(item,index) in form.signals" :key="`${item.name}-${index}`" class="signal-row">
            <span class="signal-index">{{ index + 1 }}</span>
            <div><strong>{{ item.display_name || item.name }}</strong><small><code>{{ item.name }}</code> Â· {{ item.can_id }} Â· {{ item.data_type }}</small></div>
            <button class="icon-button" type="button" :aria-label="t('profiles.editSignal')" @click="editSignal(index)"><AppIcon name="edit" :size="16" /></button>
            <button class="icon-button danger-text" type="button" :aria-label="t('common.delete')" @click="removeSignal(index)"><AppIcon name="trash" :size="16" /></button>
          </article>
          <p v-if="!form.signals.length" class="profile-empty">{{ t('profiles.noSignalsHint') }}</p>
        </div>
      </section>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="form-actions"><button class="button" :disabled="saving">{{ t('common.save') }}</button><button class="button secondary" type="button" @click="emit('close')">{{ t('common.cancel') }}</button></div>
    </form>
  </AppModal>

  <AppModal :open="signalOpen" :title="signalIndex === null ? t('profiles.addSignal') : t('profiles.editSignal')" wide @close="signalOpen=false">
    <form class="signal-editor" @submit.prevent="saveSignal">
      <section class="field-section">
        <header><h3>{{ t('profiles.signalIdentity') }}</h3><p>{{ t('profiles.signalIdentityHint') }}</p></header>
        <div class="signal-grid identity-grid">
          <label class="field"><span>{{ t('profiles.metricName') }}</span><input v-model="signal.name" class="input mono" placeholder="battery.soc" pattern="[a-z][a-z0-9_.-]*" required autofocus /></label>
          <label class="field"><span>{{ t('profiles.displayName') }}</span><input v-model="signal.display_name" class="input" /></label>
        </div>
      </section>
      <section class="field-section">
        <header><h3>{{ t('profiles.source') }}</h3><p>{{ t('profiles.sourceHint') }}</p></header>
        <div class="signal-grid source-grid">
          <label class="field"><span>{{ t('profiles.canId') }}</span><input v-model="signal.can_id" class="input mono" placeholder="0x374" required /></label>
          <label class="field"><span>{{ t('profiles.byteOffset') }}</span><input v-model.number="signal.byte_offset" class="input" type="number" min="0" max="63" required /></label>
          <label class="field"><span>{{ t('profiles.dataType') }}</span><AppSelect v-model="signal.data_type"><option v-for="type in dataTypes" :key="type" :value="type">{{ type }}</option></AppSelect></label>
          <label class="field"><span>{{ t('profiles.endianness') }}</span><AppSelect v-model="signal.endianness"><option value="big">{{ t('profiles.bigEndian') }}</option><option value="little">{{ t('profiles.littleEndian') }}</option></AppSelect></label>
        </div>
      </section>
      <section class="field-section">
        <header><h3>{{ t('profiles.conversion') }}</h3><p>{{ t('profiles.conversionHint') }}</p></header>
        <div class="signal-grid conversion-grid">
          <label class="field"><span>{{ t('profiles.scale') }}</span><input v-model.number="signal.scale" class="input" type="number" step="any" required /></label>
          <label class="field"><span>{{ t('profiles.offset') }}</span><input v-model.number="signal.offset" class="input" type="number" step="any" required /></label>
          <label class="field"><span>{{ t('profiles.unit') }}</span><input v-model="signal.unit" class="input" placeholder="%" /></label>
          <label class="field"><span>{{ t('profiles.minimum') }}</span><input v-model="signal.minimum" class="input" type="number" step="any" /></label>
          <label class="field"><span>{{ t('profiles.maximum') }}</span><input v-model="signal.maximum" class="input" type="number" step="any" /></label>
        </div>
      </section>
      <p v-if="signalError" class="error" role="alert">{{ signalError }}</p>
      <div class="form-actions"><button class="button">{{ t('profiles.saveSignal') }}</button><button class="button secondary" type="button" @click="signalOpen=false">{{ t('common.cancel') }}</button></div>
    </form>
  </AppModal>
</template>

<style scoped>
.profile-editor,.signal-editor{display:grid;gap:18px}
.profile-details{display:grid;gap:14px}
.profile-details .textarea{min-height:88px;resize:vertical}
.signal-section{display:grid;gap:10px}
.signal-section>header{display:flex;align-items:flex-end;justify-content:space-between;gap:18px}
.signal-section h3,.field-section h3{margin:0;font-size:13px;font-weight:600}
.signal-section p,.field-section header p{margin:3px 0 0;color:var(--muted);font-size:12px;line-height:1.45}
.signal-rows{overflow:hidden;border:1px solid var(--line);border-radius:var(--radius-lg)}
.signal-row{min-height:52px;display:flex;align-items:center;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line)}
.signal-row:last-child{border-bottom:0}
.signal-row>div{min-width:0;flex:1}
.signal-row strong{display:block;font-size:13px;font-weight:500}
.signal-row small{display:block;margin-top:2px;color:var(--muted);font-size:12px}
.signal-row code{font-family:var(--mono);color:var(--text)}
.signal-index{width:22px;flex:none;color:var(--muted);font-family:var(--mono);font-size:12px;text-align:right}
.profile-empty{margin:0;padding:16px;color:var(--muted);font-size:13px;text-align:center}
.danger-text{color:var(--danger)}
.danger-text:hover{color:var(--danger);background:var(--danger-soft)}
.field-section{display:grid;gap:12px;padding:0 0 16px;border-bottom:1px solid var(--line)}
.field-section:last-of-type{padding-bottom:0;border-bottom:0}
.signal-grid{display:grid;gap:12px}
.identity-grid,.source-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
.conversion-grid{grid-template-columns:repeat(5,minmax(0,1fr))}
.form-actions{justify-content:flex-end;margin-top:0}
@media(max-width:760px){
  .identity-grid,.source-grid,.conversion-grid{grid-template-columns:1fr}
  .signal-section>header{align-items:flex-start;flex-direction:column}
}
</style>
