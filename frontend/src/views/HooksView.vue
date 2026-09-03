<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatAge, formatInstant } from '../vehicleDisplay'
import { api, errorMessage } from '../api/client'
import { useLiveRefresh } from '../api/live'
import type { HistoryObservationSample, HistoryObservations, Hook, HookExecution, HookRevision, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import RowMenu from '../components/RowMenu.vue'
import { isAdmin } from '../access'
import HookEditorForm, { type HookDraft } from '../components/HookEditorForm.vue'
import MetricKeyReference from '../components/MetricKeyReference.vue'
import { askConfirm } from '../confirm'

interface Secret { id: string; name: string; masked: string; created_at: string; updated_at: string }
const defaultSource = `# Runs after telemetry is safely stored.\nsoc = ctx.telemetry.current.readings.get("battery.soc")\nif soc is None or not soc.fresh:\n    return\n\narmed = ctx.state.get("armed", True)\nif armed and soc.value < 20:\n    ctx.log.warning("Battery is low", soc=soc.value, observed_at=soc.observed_at)\n    ctx.state["armed"] = False\nelif not armed and soc.value > 23:\n    ctx.state["armed"] = True\n`
const emptyDraft = (): HookDraft => ({ name:'', description:'', enabled:false, trigger_type:'telemetry.received', vehicle_id:null, source:defaultSource, timeout_seconds:10 })
const { t, locale } = useI18n()
const hooks = ref<Hook[]>([])
const vehicles = ref<Vehicle[]>([])
const selectedId = ref('')
const executions = ref<HookExecution[]>([])
const revisions = ref<HookRevision[]>([])
const error = ref('')
const saved = ref(false)
const saving = ref(false)
const testing = ref(false)
const creating = ref(false)
const referenceOpen = ref(false)
const secrets = ref<Secret[]>([])
const secretName = ref('')
const secretValue = ref('')
const form = ref<HookDraft>(emptyDraft())
const selected = computed(() => hooks.value.find((row) => row.id === selectedId.value))
const vehicleNames = computed(() => Object.fromEntries(vehicles.value.map((row) => [row.id, row.name])))
const lastRun = computed(() => executions.value[0] ?? null)
const hookFilter = ref('')

const listedHooks = computed(() => {
  const needle = hookFilter.value.trim().toLowerCase()
  if (!needle) return hooks.value
  return hooks.value.filter((hook) =>
    hook.name.toLowerCase().includes(needle) || hook.description.toLowerCase().includes(needle))
})

/*
 * A hook that failed is the one thing in this list worth interrupting for.
 *
 * Only a finished run that went wrong counts: pending and running have not
 * reached a verdict, and claiming failure for a run still in flight would be a
 * guess. `timeout` is a failure the server names separately.
 */
const FAILED_STATUSES = new Set(['failed', 'timeout'])

function hasFailed(hook: Hook): boolean {
  return FAILED_STATUSES.has(hook.last_execution?.status ?? '')
}

/** When a hook last ran, or that it never has. Never a guess about an outcome. */
function hookRun(hook: Hook): string {
  const run = hook.last_execution
  if (!run) return t('hooks.neverRun')
  const age = formatAge(run.created_at, locale.value)
  return hasFailed(hook) ? t('hooks.failedAge', { age }) : t('hooks.ranAge', { age })
}

/** Both facts a reader takes from the dot, for a reader who cannot see it. */
function hookState(hook: Hook): string {
  return `${hook.enabled ? t('hooks.enabledLabel') : t('hooks.disabledLabel')}, ${hookRun(hook)}`
}

/**
 * The one line under a hook's name, or nothing.
 *
 * "All vehicles" was under almost every row and is the default, so it said
 * nothing while taking the only line there was. What an author wrote to explain
 * the hook is worth more, and a vehicle is worth naming only when it narrows
 * the hook to one. A row with neither gets no second line rather than a filler.
 */
function hookNote(hook: Hook): string {
  const scope = hook.vehicle_id ? vehicleNames.value[hook.vehicle_id] ?? t('hooks.oneVehicle') : ''
  const described = hook.description.trim()
  if (scope && described) return `${scope} · ${described}`
  return scope || described
}

function runDuration(execution: HookExecution): string {
  return execution.duration_seconds === null ? '—' : `${Math.round(execution.duration_seconds * 1000)} ms`
}

async function load(): Promise<void> {
  ;[hooks.value, vehicles.value, secrets.value] = await Promise.all([
    api<Hook[]>('/hooks'),
    api<Vehicle[]>('/vehicles'),
    api<Secret[]>('/secrets'),
  ])
  if (!selectedId.value && hooks.value[0]) select(hooks.value[0].id)
}

function select(id: string): void {
  const hook = hooks.value.find((row) => row.id === id)
  if (!hook) return
  selectedId.value = id
  form.value = { name:hook.name, description:hook.description, enabled:hook.enabled, trigger_type:hook.trigger_type, vehicle_id:hook.vehicle_id, source:hook.source, timeout_seconds:hook.timeout_seconds }
  error.value = ''
  void loadExecutions()
}

function openCreate(): void {
  form.value = emptyDraft()
  error.value = ''
  creating.value = true
}

function cancelCreate(): void {
  creating.value = false
  if (selected.value) select(selected.value.id)
}

async function save(): Promise<void> {
  error.value = ''
  saving.value = true
  try {
    const hook = await api<Hook>(creating.value ? '/hooks' : `/hooks/${selectedId.value}`, {
      method: creating.value ? 'POST' : 'PUT',
      body: JSON.stringify(form.value),
    })
    selectedId.value = hook.id
    creating.value = false
    saved.value = true
    await load()
    select(hook.id)
    window.setTimeout(() => saved.value = false, 1500)
  } catch (reason) {
    error.value = errorMessage(reason, t('common.error'))
  } finally {
    saving.value = false
  }
}

async function refreshHooks(): Promise<void> {
  try {
    hooks.value = await api<Hook[]>('/hooks')
  } catch {
    // A poll that fails changes nothing on screen; the next one tries again.
  }
}

async function loadExecutions(): Promise<void> {
  if (!selectedId.value) return
  ;[executions.value, revisions.value] = await Promise.all([
    api<HookExecution[]>(`/hooks/${selectedId.value}/executions`),
    api<HookRevision[]>(`/hooks/${selectedId.value}/revisions`),
  ])
}

async function restoreRevision(revision: number): Promise<void> {
  if (!selectedId.value) return
  const hook = await api<Hook>(`/hooks/${selectedId.value}/revisions/${revision}/restore`, { method:'POST' })
  await load()
  select(hook.id)
}

/**
 * Which stored sample makes a useful dry run.
 *
 * A sample is a transport envelope, not a snapshot, so a parked vehicle's newest
 * one is usually a bare heartbeat carrying nothing at all. Handing that to a
 * test run gives the hook an empty ctx.telemetry.triggering, and a hook that
 * guards on it returns immediately and logs nothing, which reads as the test
 * being broken. Triggering is built from a sample's observations and its
 * position, so either one is enough to make the run mean something; readings
 * come first because they are what a hook usually reasons about.
 * The samples arrive newest first, so the first match is the newest match.
 */
function sampleWorthTesting(samples: HistoryObservationSample[]): HistoryObservationSample | undefined {
  return samples.find((sample) => sample.observations.length > 0)
    ?? samples.find((sample) => sample.position !== null)
    // Nothing in the window carried anything: the newest is still the honest
    // answer, and the run will show what that means.
    ?? samples[0]
}

async function testHook(): Promise<void> {
  if (!selectedId.value) return
  testing.value = true
  try {
    const vehicleId = form.value.vehicle_id ?? vehicles.value[0]?.id
    if (!vehicleId) throw new Error(t('hooks.createVehicleFirst'))
    const recent = await api<HistoryObservations>(`/vehicles/${vehicleId}/history/observations?limit=100`)
    const telemetry = sampleWorthTesting(recent.samples)
    if (!telemetry) throw new Error(t('hooks.noTelemetry'))
    await api(`/hooks/${selectedId.value}/test`, { method:'POST', body:JSON.stringify({ telemetry_id:telemetry.id, dry_run:true }) })
    await loadExecutions()
  } catch (reason) {
    error.value = errorMessage(reason, t('common.error'))
  } finally {
    testing.value = false
  }
}

async function deleteHook(hook: Hook): Promise<void> {
  error.value = ''
  const accepted = await askConfirm({
    title: t('hooks.deleteTitle'),
    question: t('hooks.deleteQuestion', { name: hook.name }),
    detail: t('hooks.deleteWarning'),
    confirmLabel: t('hooks.deleteAction'),
    busyLabel: t('hooks.deleting'),
    action: async () => { await api<void>(`/hooks/${hook.id}`, { method:'DELETE' }) },
  })
  if (!accepted) return
  // Land on the neighbour rather than on nothing, so deleting one of several
  // does not empty the panel and make the page look like it lost everything.
  const removed = hooks.value.findIndex((row) => row.id === hook.id)
  const remaining = hooks.value.filter((row) => row.id !== hook.id)
  const next = remaining[Math.min(Math.max(removed, 0), remaining.length - 1)]
  selectedId.value = ''
  executions.value = []
  revisions.value = []
  await load()
  if (next) select(next.id)
}

async function storeSecret(): Promise<void> {
  await api(`/secrets/${secretName.value}`, { method:'PUT', body:JSON.stringify({ name:secretName.value, value:secretValue.value }) })
  secretName.value = ''
  secretValue.value = ''
  secrets.value = await api<Secret[]>('/secrets')
}

async function removeSecret(name: string): Promise<void> {
  await api(`/secrets/${name}`, { method:'DELETE' })
  secrets.value = secrets.value.filter((row) => row.name !== name)
}

/*
 * A run started from here, or by telemetry arriving, appends a row the panel had
 * no way to hear about: the page was only ever loaded once. Polling the open
 * panel is the whole of what is needed, and the shared helper already stops
 * while the tab is hidden and catches up on return. Nothing polls when no hook
 * is selected, because there is nothing to ask about.
 */
useLiveRefresh(() => {
  if (selectedId.value) void loadExecutions()
  // The list now says how each hook last ran, which is only true if it is kept
  // up. This replaces the rows alone: reselecting would throw away edits in the
  // detail form that have not been saved yet.
  void refreshHooks()
}, { pollMs: 5000 })

onMounted(load)
</script>

<template>
  <div class="page hooks-page">
    <header class="page-header">
      <div>
        <h1>{{ t('hooks.title') }}</h1>
        <p class="privilege-warning"><strong>{{ t('hooks.trusted') }}</strong>: {{ t('hooks.trustedHint') }}</p>
      </div>
      <div class="header-actions">
        <button class="button" @click="openCreate"><AppIcon name="plus" :size="15" />{{ t('hooks.new') }}</button>
      </div>
    </header>

    <div class="hooks-layout">
      <aside class="hooks-rail">
        <!-- With no hooks the panel beside this one already says so, and a rail
             group repeating it under an empty heading reads as a second, broken
             list rather than as the same message. -->
        <section v-if="hooks.length" class="rail-group">
          <h2 class="rail-title">{{ t('hooks.yours') }}<span class="rail-count">{{ hooks.length }}</span></h2>
          <!-- Past a handful, reading the list stops being how you find one. -->
          <label v-if="hooks.length > 6" class="hook-filter">
            <span class="sr-only">{{ t('hooks.filter') }}</span>
            <input v-model="hookFilter" class="input" type="search" :placeholder="t('hooks.filter')" />
          </label>
          <div class="hook-list">
            <button v-for="hook in listedHooks" :key="hook.id" :class="['hook-row', { active:selectedId===hook.id, off:!hook.enabled, failing:hasFailed(hook) }]" @click="select(hook.id)">
              <span class="hook-state" aria-hidden="true" />
              <span class="hook-name">{{ hook.name }}</span>
              <!-- The dot carries both of these visually; nothing is left to
                   colour alone, and the run is stated rather than implied. -->
              <span class="sr-only">{{ hookState(hook) }}</span>
              <span class="hook-meta">
                <small v-if="hookNote(hook)" class="hook-note">{{ hookNote(hook) }}</small>
                <!-- Last, and never truncated: a long description gives way to
                     it rather than pushing it out of the row. -->
                <small class="hook-run">{{ hookRun(hook) }}</small>
              </span>
            </button>
            <p v-if="!listedHooks.length" class="rail-note">{{ t('hooks.noMatch') }}</p>
          </div>
        </section>

        <section class="rail-group rail-card">
          <h2 class="rail-title">{{ t('hooks.secrets') }}</h2>
          <p class="rail-note">{{ t('hooks.secretsHint') }}</p>
          <ul v-if="secrets.length" class="secret-list">
            <li v-for="secret in secrets" :key="secret.id">
              <strong class="mono">{{ secret.name }}</strong>
              <button class="icon-button" :aria-label="t('common.delete')" @click="removeSecret(secret.name)"><AppIcon name="close" :size="13" /></button>
              <small class="mono">{{ secret.masked }}</small>
            </li>
          </ul>
          <form class="secret-form" @submit.prevent="storeSecret">
            <input v-model="secretName" class="input mono" placeholder="gate_token" pattern="[A-Za-z][A-Za-z0-9_.-]*" :aria-label="t('hooks.secretName')" required />
            <input v-model="secretValue" class="input" type="password" placeholder="••••••••" :aria-label="t('hooks.secretValue')" required />
            <button class="button secondary">{{ t('hooks.addSecret') }}</button>
          </form>
        </section>
      </aside>

      <section v-if="selected" class="panel hook-detail">
        <header class="detail-bar">
          <div class="detail-identity">
            <h2>{{ selected.name }}</h2>
            <p>
              {{ t('hooks.revision', { revision:selected.revision }) }}
              <template v-if="lastRun"> · {{ t('hooks.lastRun') }} <span :class="['run-state', lastRun.status==='success' ? 'ok' : 'bad']">{{ lastRun.status }}</span></template>
            </p>
          </div>
          <div class="detail-actions">
            <span v-if="saved" class="saved-note" role="status">{{ t('hooks.savedNote') }}</span>
            <label class="toggle">
              <input v-model="form.enabled" type="checkbox" :aria-label="t('hooks.enabled')" />
              <span class="track" aria-hidden="true" />
              <span class="toggle-label">{{ form.enabled ? t('hooks.enabledLabel') : t('hooks.disabledLabel') }}</span>
            </label>
            <button class="button secondary" type="button" :disabled="testing" @click="testHook">{{ t('hooks.test') }}</button>
            <button class="button" type="submit" form="hook-detail-form" :disabled="saving">{{ t('common.save') }}</button>
            <RowMenu v-if="isAdmin" :label="t('dataSources.moreActions', { name: selected.name })">
              <button type="button" role="menuitem" class="danger" @click="deleteHook(selected)">{{ t('common.delete') }}</button>
            </RowMenu>
          </div>
        </header>

        <div class="detail-body">
          <HookEditorForm v-model="form" form-id="hook-detail-form" :standalone="false" :vehicles="vehicles" :error="error" :saving="saving" @save="save" @reference="referenceOpen = true" />
          <details v-if="revisions.length" class="revision-list">
            <summary>{{ t('hooks.revisions') }}</summary>
            <div><button v-for="revision in revisions" :key="revision.id" class="button secondary" type="button" :disabled="revision.revision===selected?.revision" @click="restoreRevision(revision.revision)">{{ t('hooks.restoreRevision', { revision:revision.revision }) }}</button></div>
          </details>
        </div>

        <div class="detail-runs">
          <div class="runs-head"><h3>{{ t('hooks.executions') }}</h3><span v-if="executions.length" class="count">{{ executions.length }}</span></div>
          <div v-if="executions.length" class="table-wrap">
            <table class="table runs-table">
              <thead><tr><th>{{ t('hooks.status') }}</th><th>{{ t('hooks.when') }}</th><th>{{ t('hooks.duration') }}</th><th>{{ t('hooks.logs') }}</th></tr></thead>
              <tbody>
                <tr v-for="execution in executions" :key="execution.id">
                  <td><span :class="['status', { online:execution.status==='success', failed:execution.status!=='success' }]">{{ execution.status }}</span></td>
                  <td>{{ formatInstant(execution.created_at) }}</td>
                  <td class="mono">{{ runDuration(execution) }}</td>
                  <td>
                    <details v-if="execution.error || execution.logs.length">
                      <summary>{{ execution.error ? t('hooks.viewError') : t('hooks.logCount', { count:execution.logs.length }) }}</summary>
                      <pre :class="['execution-output', { 'is-error':execution.error }]">{{ execution.error || JSON.stringify(execution.logs, null, 2) }}</pre>
                    </details>
                    <!-- A run that logged nothing is a fact about the run, and
                         an empty cell reads as the page having failed to draw. -->
                    <span v-else class="muted quiet-run">{{ t('hooks.noOutput') }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p v-else class="empty-note">{{ t('hooks.noExecutions') }}</p>
        </div>
      </section>

      <section v-else class="panel empty hook-detail">
        <h2>{{ t('hooks.empty') }}</h2>
        <p>{{ t('hooks.emptyHint') }}</p>
        <button class="button" @click="openCreate"><AppIcon name="plus" :size="15" />{{ t('hooks.new') }}</button>
      </section>
    </div>

    <AppModal :open="creating" :inactive="referenceOpen" :title="t('hooks.createTitle')" wide @close="cancelCreate">
      <HookEditorForm v-model="form" compact :vehicles="vehicles" :error="error" :saving="saving" @save="save" @reference="referenceOpen = true" />
    </AppModal>

    <MetricKeyReference :open="referenceOpen" @close="referenceOpen = false" />

  </div>
</template>

<style scoped>
.hooks-page{display:grid;gap:14px}
.hooks-page>.page-header{margin-bottom:0}
.privilege-warning{max-width:70ch}
.privilege-warning strong{color:var(--warning);font-weight:600}

.hooks-layout{display:grid;grid-template-columns:236px minmax(0,1fr);align-items:start;gap:14px}

.hooks-rail{display:grid;gap:22px;align-content:start}
.rail-group{display:grid;gap:7px}
/* Secrets are a form, and a form standing on the page beside a panel reads as
   something that fell out of one. */
.rail-card{padding:13px 14px;background:var(--panel);border-radius:var(--radius-lg);box-shadow:0 0 0 1px var(--panel-line),var(--shadow-soft)}
.rail-title{display:flex;align-items:baseline;gap:6px;margin:0;color:var(--muted);font-size:var(--font-caption);font-weight:600}
.rail-count{color:var(--muted-2);font-variant-numeric:tabular-nums;font-weight:500}

.rail-note{margin:0;color:var(--muted);font-size:var(--font-caption);line-height:1.45}

.hook-filter .input{min-height:30px;padding:5px 8px;font-size:var(--font-caption)}
/* Twenty hooks used to push the secrets card off the bottom of the page. The
   list keeps its own scroll so everything beside it stays reachable. */
.hook-list{display:grid;gap:2px;max-height:min(52vh,420px);overflow-y:auto;overscroll-behavior:contain}
.hook-row{
  width:100%;display:grid;grid-template-columns:auto minmax(0,1fr);align-items:baseline;
  gap:1px 8px;padding:7px 10px;color:var(--text);background:transparent;
  border:1px solid transparent;border-radius:var(--radius);text-align:left;cursor:pointer;
  transition:background-color .12s,border-color .12s;
}
.hook-row:hover{background:var(--panel-2)}
.hook-row.active{background:var(--panel);border-color:var(--line);box-shadow:var(--shadow-soft)}
/* Whether a hook is on was the loudest word on the row and the least useful.
   A dot says it without competing with the name. */
.hook-state{width:7px;height:7px;align-self:center;background:var(--success);border-radius:50%}
.hook-row.off .hook-state{background:transparent;box-shadow:inset 0 0 0 1.5px var(--muted-2)}
/* A failed run recolours the dot without disturbing what it already says: still
   filled when the hook is on, still a ring when it is off. */
.hook-row.failing .hook-state{background:var(--danger)}
.hook-row.off.failing .hook-state{background:transparent;box-shadow:inset 0 0 0 1.5px var(--danger)}
.hook-name{overflow:hidden;font-size:var(--font-body);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
/* A hook that is off should recede rather than announce itself. */
.hook-row.off .hook-name{color:var(--muted)}
/* The description gives way, the run does not: the fact most worth reading is
   the one a long description would otherwise push out of the row. */
.hook-meta{grid-column:2;min-width:0;display:flex;align-items:baseline;gap:8px}
.hook-note{min-width:0;overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.hook-run{flex:none;margin-left:auto;color:var(--muted-2);font-size:var(--font-micro);white-space:nowrap}
.hook-row.failing .hook-run{color:var(--danger)}
/* The dark danger tone measures 4.35:1 against the row's hover background,
   under the 4.5:1 this size of text is held to. Lightened only for this text,
   because the token is a fill elsewhere and reads white-on-danger there. */
[data-theme="dark"] .hook-row.failing .hook-run{color:#f48080}

.secret-list{list-style:none;margin:0;padding:0;display:grid;gap:1px}
.secret-list li{display:grid;grid-template-columns:minmax(0,1fr) 22px;align-items:center;padding:5px 2px 5px 0}
.secret-list strong{overflow:hidden;font-size:var(--font-caption);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.secret-list small{grid-column:1;color:var(--muted-2);font-size:var(--font-micro);letter-spacing:.06em}
.secret-list .icon-button{width:22px;height:22px}
.secret-form{display:grid;gap:6px;margin-top:4px}
.secret-form .input{min-height:30px;padding:5px 8px;font-size:var(--font-caption)}
.secret-form .button{justify-self:start;height:28px;font-size:var(--font-caption)}

.hook-detail{min-width:0}
.detail-bar{
  position:sticky;top:0;z-index:5;display:flex;align-items:center;justify-content:space-between;
  gap:16px;padding:11px 16px;background:var(--panel);
  border-bottom:1px solid var(--line);border-radius:var(--radius-lg) var(--radius-lg) 0 0;
}
.detail-identity{min-width:0}
.detail-identity h2{margin:0;overflow:hidden;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em;text-overflow:ellipsis;white-space:nowrap}
.detail-identity p{margin:2px 0 0;color:var(--muted);font-size:var(--font-caption)}
.run-state.ok{color:var(--success)}
.run-state.bad{color:var(--danger)}
.detail-actions{display:flex;align-items:center;gap:12px;flex:none}
.saved-note{color:var(--success);font-size:var(--font-caption)}

.toggle{display:flex;align-items:center;gap:7px;cursor:pointer}
.toggle input{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.track{width:28px;height:16px;flex:none;background:var(--line-strong);border-radius:999px;transition:background-color .12s}
.track::after{content:"";display:block;width:12px;height:12px;margin:2px;background:var(--panel);border-radius:50%;transition:transform .12s}
.toggle input:checked+.track{background:var(--success)}
.toggle input:checked+.track::after{transform:translateX(12px)}
.toggle input:focus-visible+.track{outline:2px solid var(--accent);outline-offset:2px}
.toggle-label{color:var(--muted);font-size:var(--font-caption)}

.detail-body{padding:16px}
.revision-list{margin-top:16px;color:var(--muted);font-size:var(--font-caption)}
.revision-list summary{cursor:pointer}
.revision-list div{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}

.detail-runs{border-top:1px solid var(--line)}
.runs-head{display:flex;align-items:baseline;gap:10px;padding:12px 16px}
.runs-head h3{margin:0;font-size:var(--font-body);font-weight:600}
.runs-head .count{color:var(--muted);font-size:var(--font-caption);font-variant-numeric:tabular-nums}
.runs-table{border-top:1px solid var(--line)}
.runs-table th:first-child,.runs-table td:first-child{width:104px}
.runs-table th:nth-child(3),.runs-table td:nth-child(3){width:96px}
.runs-table summary{color:var(--muted);cursor:pointer}
.runs-table summary:hover{color:var(--text)}
.execution-output{max-width:620px;max-height:220px;margin:8px 0 0;overflow:auto;font-family:var(--mono);font-size:var(--font-caption);white-space:pre-wrap;overflow-wrap:anywhere}
.execution-output.is-error{color:var(--danger)}
.quiet-run{font-size:var(--font-caption);font-style:italic}

@media(max-width:900px){
  .hooks-layout{grid-template-columns:1fr}
  .hooks-rail{grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}
  /* The list is the thing being chosen from, so it gets the full width and the
     secrets form sits under it rather than competing for half the row. */
  .hooks-rail>.rail-group:first-child{grid-column:1/-1}
  .hook-list{max-height:min(38vh,300px)}
  .detail-bar{position:static;flex-wrap:wrap}
  /* The bar wraps, but this row did not: three items that each refuse to shrink
     below their own text overflow the page in any locale whose labels are
     longer than English. It has to be allowed to wrap in turn. */
  .detail-actions{flex-wrap:wrap}
}
@media(max-width:560px){
  .hooks-rail{grid-template-columns:1fr}
  .detail-actions{width:100%}
  .detail-actions .button{flex:1 1 auto;min-width:0}
  .toggle{flex:1 0 100%}
  /* A 620px log pane and two fixed columns give the runs table about 905px of
     intrinsic width, which its wrapper then scrolls sideways for the whole
     width of a phone. On a narrow screen the columns can size themselves and
     the pane can take the width it is given. */
  .execution-output{max-width:100%}
  .runs-table th:first-child,.runs-table td:first-child,
  .runs-table th:nth-child(3),.runs-table td:nth-child(3){width:auto}
  .runs-table th,.runs-table td{padding:9px 10px}
}
</style>
