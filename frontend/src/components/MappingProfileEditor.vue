<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { MappingRule, MappingTransform, VehicleProfile } from '../api/types'
import AppIcon from './AppIcon.vue'
import AppModal from './AppModal.vue'
import AppSelect from './AppSelect.vue'

type TransformKind = 'none' | 'scale' | 'enum' | 'boolean' | 'json'

interface RuleDraft {
  match: string
  target: string
  kind: TransformKind
  scale: number
  offset: number
  enumText: string
}

const props = defineProps<{ open: boolean; profile?: VehicleProfile | null; clone?: boolean }>()
const emit = defineEmits<{ saved: []; close: [] }>()
const { t } = useI18n()
const saving = ref(false)
const error = ref('')
const ruleError = ref('')
const ruleOpen = ref(false)
const ruleIndex = ref<number | null>(null)
const form = ref({ name: '', description: '', passthrough_prefix: '', ignore: '', rules: [] as RuleDraft[] })
const rule = ref<RuleDraft>(blankRule())
const editing = computed(() => Boolean(props.profile) && !props.clone)
const transformKinds: TransformKind[] = ['none', 'scale', 'enum', 'boolean', 'json']
const positionTargets = ['position.latitude', 'position.longitude', 'position.altitude', 'position.speed', 'position.heading', 'position.accuracy']

function blankRule(): RuleDraft {
  return { match: '', target: '', kind: 'none', scale: 1, offset: 0, enumText: '' }
}

function enumToText(values: Record<string, string | number | boolean>): string {
  return Object.entries(values).map(([key, value]) => `${key} = ${value}`).join('\n')
}

function textToEnum(text: string): Record<string, string | number | boolean> {
  const values: Record<string, string | number | boolean> = {}
  for (const line of text.split('\n')) {
    if (!line.trim()) continue
    const separator = line.indexOf('=')
    if (separator < 0) continue
    const key = line.slice(0, separator).trim()
    const raw = line.slice(separator + 1).trim()
    if (!key) continue
    values[key] = raw === 'true' ? true : raw === 'false' ? false : Number(raw) === Number(raw) && raw !== '' ? Number(raw) : raw
  }
  return values
}

function transformKind(transform: MappingTransform | undefined): TransformKind {
  if (!transform) return 'none'
  if (transform.enum) return 'enum'
  if (transform.boolean) return 'boolean'
  if (transform.json) return 'json'
  if (transform.scale !== undefined || transform.offset !== undefined) return 'scale'
  return 'none'
}

function profileRules(profile: VehicleProfile): RuleDraft[] {
  return (profile.definition.rules ?? []).map((item) => ({
    match: item.match,
    target: item.target,
    kind: transformKind(item.transform),
    scale: item.transform?.scale ?? 1,
    offset: item.transform?.offset ?? 0,
    enumText: item.transform?.enum ? enumToText(item.transform.enum) : '',
  }))
}

function reset(): void {
  const source = props.profile
  form.value = source
    ? {
        name: props.clone ? t('profiles.cloneName', { name: source.name }) : source.name,
        description: source.description,
        passthrough_prefix: source.definition.passthrough_prefix ?? '',
        ignore: (source.definition.ignore ?? []).join(', '),
        rules: profileRules(source),
      }
    : { name: '', description: '', passthrough_prefix: '', ignore: '', rules: [] }
  error.value = ''
  ruleError.value = ''
  ruleOpen.value = false
  ruleIndex.value = null
}

function close(): void {
  if (ruleOpen.value) {
    ruleOpen.value = false
    return
  }
  emit('close')
}

function editRule(index?: number): void {
  ruleIndex.value = index ?? null
  rule.value = index === undefined ? blankRule() : { ...form.value.rules[index]! }
  ruleError.value = ''
  ruleOpen.value = true
}

function validTarget(target: string): boolean {
  if (target.startsWith('position.')) return positionTargets.includes(target)
  return /^[a-z][a-z0-9_.-]*$/.test(target)
}

function saveRule(): void {
  ruleError.value = ''
  const match = rule.value.match.trim()
  const target = rule.value.target.trim()
  if (!match || !validTarget(target)) {
    ruleError.value = t('profiles.invalidRule')
    return
  }
  if (form.value.rules.some((item, index) => item.match === match && index !== ruleIndex.value)) {
    ruleError.value = t('profiles.duplicateMatch')
    return
  }
  const next = { ...rule.value, match, target }
  if (ruleIndex.value === null) form.value.rules.push(next)
  else form.value.rules[ruleIndex.value] = next
  ruleOpen.value = false
}

function removeRule(index: number): void { form.value.rules.splice(index, 1) }

function transformOf(draft: RuleDraft): MappingTransform | undefined {
  if (draft.kind === 'scale') return { scale: draft.scale, offset: draft.offset }
  if (draft.kind === 'enum') return { enum: textToEnum(draft.enumText) }
  if (draft.kind === 'boolean') return { boolean: true }
  if (draft.kind === 'json') return { json: true }
  return undefined
}

function transformSummary(draft: RuleDraft): string {
  if (draft.kind === 'scale') return `× ${draft.scale} + ${draft.offset}`
  if (draft.kind === 'enum') return t('profiles.transformKind.enum')
  if (draft.kind === 'boolean') return t('profiles.transformKind.boolean')
  if (draft.kind === 'json') return t('profiles.transformKind.json')
  return t('profiles.transformKind.none')
}

async function save(): Promise<void> {
  error.value = ''
  if (!form.value.rules.length) {
    error.value = t('profiles.noRules')
    return
  }
  const rules: MappingRule[] = form.value.rules.map((item) => {
    const transform = transformOf(item)
    return { match: item.match, target: item.target, ...(transform ? { transform } : {}) }
  })
  saving.value = true
  try {
    await api(editing.value ? `/vehicle-profiles/${props.profile!.id}` : '/vehicle-profiles', {
      method: editing.value ? 'PUT' : 'POST',
      body: JSON.stringify({
        name: form.value.name.trim(),
        description: form.value.description.trim(),
        type: 'mapping',
        passthrough_prefix: form.value.passthrough_prefix.trim(),
        ignore: form.value.ignore.split(',').map((item) => item.trim()).filter(Boolean),
        rules,
      }),
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
  <AppModal :open="open" :inactive="ruleOpen" :title="editing ? t('profiles.editMappingTitle') : t('profiles.createMappingTitle')" wide @close="close">
    <form class="profile-editor" @submit.prevent="save">
      <div class="profile-details">
        <label class="field"><span>{{ t('profiles.name') }}</span><input v-model="form.name" class="input" required autofocus /></label>
        <label class="field"><span>{{ t('profiles.description') }}</span><textarea v-model="form.description" class="textarea" rows="2" /></label>
      </div>
      <div class="form-grid">
        <label class="field"><span>{{ t('profiles.passthroughPrefix') }}</span><input v-model="form.passthrough_prefix" class="input mono" placeholder="teslamate" /><small class="field-hint">{{ t('profiles.passthroughHint') }}</small></label>
        <label class="field"><span>{{ t('profiles.ignoreKeys') }}</span><input v-model="form.ignore" class="input mono" placeholder="latitude, longitude" /><small class="field-hint">{{ t('profiles.ignoreHint') }}</small></label>
      </div>

      <section class="signal-section">
        <header>
          <div><h3>{{ t('profiles.rulesTitle') }}</h3><p>{{ t('profiles.rulesHint') }}</p></div>
          <button class="button secondary" type="button" @click="editRule()"><AppIcon name="plus" :size="14" />{{ t('profiles.addRule') }}</button>
        </header>
        <div class="signal-rows">
          <article v-for="(item,index) in form.rules" :key="`${item.match}-${index}`" class="signal-row">
            <span class="signal-index">{{ index + 1 }}</span>
            <div><strong><code>{{ item.match }}</code> → <code>{{ item.target }}</code></strong><small>{{ transformSummary(item) }}</small></div>
            <button class="icon-button" type="button" :aria-label="t('profiles.editRule')" @click="editRule(index)"><AppIcon name="edit" :size="16" /></button>
            <button class="icon-button danger-text" type="button" :aria-label="t('common.delete')" @click="removeRule(index)"><AppIcon name="trash" :size="16" /></button>
          </article>
          <p v-if="!form.rules.length" class="profile-empty">{{ t('profiles.noRulesHint') }}</p>
        </div>
      </section>

      <p v-if="error" class="error" role="alert">{{ error }}</p>
      <div class="form-actions"><button class="button" :disabled="saving">{{ t('common.save') }}</button><button class="button secondary" type="button" @click="emit('close')">{{ t('common.cancel') }}</button></div>
    </form>
  </AppModal>

  <AppModal :open="ruleOpen" :title="ruleIndex === null ? t('profiles.addRule') : t('profiles.editRule')" wide @close="ruleOpen=false">
    <form class="signal-editor" @submit.prevent="saveRule">
      <section class="field-section">
        <header><h3>{{ t('profiles.ruleMapping') }}</h3><p>{{ t('profiles.ruleMappingHint') }}</p></header>
        <div class="signal-grid identity-grid">
          <label class="field"><span>{{ t('profiles.ruleMatch') }}</span><input v-model="rule.match" class="input mono" placeholder="battery_level" required autofocus /></label>
          <label class="field"><span>{{ t('profiles.ruleTarget') }}</span><input v-model="rule.target" class="input mono" list="mapping-targets" placeholder="battery.soc" required /></label>
        </div>
        <datalist id="mapping-targets"><option v-for="target in positionTargets" :key="target" :value="target" /></datalist>
      </section>
      <section class="field-section">
        <header><h3>{{ t('profiles.transform') }}</h3><p>{{ t('profiles.transformHint') }}</p></header>
        <div class="signal-grid conversion-grid">
          <label class="field"><span>{{ t('profiles.transformType') }}</span><AppSelect v-model="rule.kind" :aria-label="t('profiles.transformType')"><option v-for="kind in transformKinds" :key="kind" :value="kind">{{ t(`profiles.transformKind.${kind}`) }}</option></AppSelect></label>
          <template v-if="rule.kind==='scale'">
            <label class="field"><span>{{ t('profiles.scale') }}</span><input v-model.number="rule.scale" class="input" type="number" step="any" required /></label>
            <label class="field"><span>{{ t('profiles.offset') }}</span><input v-model.number="rule.offset" class="input" type="number" step="any" required /></label>
          </template>
        </div>
        <label v-if="rule.kind==='enum'" class="field enum-field"><span>{{ t('profiles.enumValues') }}</span><textarea v-model="rule.enumText" class="textarea mono" rows="4" placeholder="Charging = true&#10;* = false" /><small class="field-hint">{{ t('profiles.enumHint') }}</small></label>
      </section>
      <p v-if="ruleError" class="error" role="alert">{{ ruleError }}</p>
      <div class="form-actions"><button class="button">{{ t('profiles.saveRule') }}</button><button class="button secondary" type="button" @click="ruleOpen=false">{{ t('common.cancel') }}</button></div>
    </form>
  </AppModal>
</template>

<style scoped>
.profile-editor,.signal-editor{display:grid;gap:18px}
.profile-details{display:grid;gap:14px}
.signal-section{display:grid;gap:10px}
.signal-section>header{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
.signal-section h3{margin:0;font-size:var(--font-body);font-weight:600}
.signal-section p{margin:3px 0 0;color:var(--muted);font-size:var(--font-caption);line-height:1.45}
.signal-rows{display:grid;gap:6px}
.signal-row{display:grid;grid-template-columns:24px minmax(0,1fr) 30px 30px;align-items:center;gap:8px;padding:8px 10px;background:var(--panel-2);border-radius:var(--radius)}
.signal-index{color:var(--muted-2);font-size:var(--font-caption);font-variant-numeric:tabular-nums}
.signal-row>div{min-width:0}
.signal-row strong{display:block;overflow:hidden;font-size:var(--font-caption);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.signal-row code{font-family:var(--mono)}
.signal-row small{display:block;margin-top:2px;color:var(--muted);font-size:var(--font-micro)}
.danger-text{color:var(--danger)}
.profile-empty{margin:0;padding:16px;color:var(--muted);font-size:var(--font-caption);text-align:center;border:1px dashed var(--line);border-radius:var(--radius)}
.field-section{display:grid;gap:10px}
.field-section header h3{margin:0;font-size:var(--font-body);font-weight:600}
.field-section header p{margin:3px 0 0;color:var(--muted);font-size:var(--font-caption)}
.signal-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.conversion-grid{grid-template-columns:repeat(3,minmax(0,1fr))}
.enum-field{margin-top:12px}
.form-actions{display:flex;justify-content:flex-end;gap:8px}
@media(max-width:620px){.signal-grid,.conversion-grid{grid-template-columns:1fr}}
</style>
