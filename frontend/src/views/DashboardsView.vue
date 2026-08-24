<script setup lang="ts">
import { GridStack, type GridStackNode } from 'gridstack'
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { clientId } from '../clientId'
import { api } from '../api/client'
import { openLiveEventStream, type LiveConnectionStatus } from '../api/events'
import type { Dashboard, DashboardWidget, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'
import { defaultDashboardMetrics, metricDefinition } from '../vehicleDisplay'
import { widgetRegistry } from '../widgets/registry'
import { dashboardRuntimeKey } from '../widgets/dashboardContext'

const { t } = useI18n()
const dashboards = ref<Dashboard[]>([])
const activeId = ref('')
const vehicles = ref<Vehicle[]>([])
const gridElement = ref<HTMLDivElement>()
const configuring = ref(false)
const creating = ref(false)
const saving = ref(false)
const editing = ref(false)
const message = ref('')
const actionsOpen = ref(false)
const newDashboardName = ref('')
const narrowCanvas = ref(false)
const selectedVehicleId = ref('')
const liveStatus = ref<LiveConnectionStatus>('connecting')
const form = ref({ type:'metric-card', vehicle_id:'', metric:'vehicle.speed', metrics:'vehicle.speed', title:'', unit:'km/h', time_range_days:1 })
let grid: GridStack | undefined
let resizeObserver: ResizeObserver | undefined
let eventSource: EventSource | undefined
let canvasColumns = 12
let editSnapshot: Dashboard[] | null = null
const OVERVIEW_PRESET = 'overview-v3'

function cloneDashboards(value: Dashboard[]): Dashboard[] {
  return JSON.parse(JSON.stringify(value)) as Dashboard[]
}

const active = computed(() => dashboards.value.find((dashboard) => dashboard.id === activeId.value) ?? null)
const activeIsPremade = computed(() => active.value?.layout.preset?.startsWith('overview-') ?? false)
const definitions = computed(() => Object.values(widgetRegistry))
const selectedVehicle = computed(() => vehicles.value.find((row) => row.id === selectedVehicleId.value))
const metricSuggestion = computed(() => {
  const vehicle = vehicles.value.find((row) => row.id === form.value.vehicle_id) ?? selectedVehicle.value
  return defaultDashboardMetrics(vehicle).join(', ')
})
const availableMetrics = computed(() => {
  const vehicle = vehicles.value.find((row) => row.id === form.value.vehicle_id) ?? selectedVehicle.value
  const metrics = new Set(Object.keys(vehicle?.state?.metrics ?? {}))
  if (vehicle?.state?.position?.speed !== null && vehicle?.state?.position?.speed !== undefined) metrics.add('vehicle.speed')
  for (const metric of defaultDashboardMetrics(vehicle)) metrics.add(metric)
  return [...metrics].sort()
})

function widget(id: string, type: string, vehicleId: string | undefined, x: number, y: number, w: number, h: number, extra: Partial<DashboardWidget> = {}): DashboardWidget {
  return { id, type, x, y, w, h, ...(vehicleId ? { vehicle_id: vehicleId } : {}), ...extra }
}

function premadeLayout(vehicleId?: string): Dashboard['layout'] {
  void vehicleId
  return { preset:OVERVIEW_PRESET, widgets: [
    widget(clientId('widget'), 'vehicle-selector', undefined, 0, 0, 12, 1),
    widget(clientId('widget'), 'position-map', undefined, 0, 1, 8, 7),
    widget(clientId('widget'), 'vehicle-media', undefined, 8, 1, 4, 2),
    widget(clientId('widget'), 'battery-gauge', undefined, 8, 3, 4, 2),
    widget(clientId('widget'), 'telemetry-list', undefined, 8, 5, 4, 3),
    widget(clientId('widget'), 'time-series', undefined, 0, 8, 8, 4, { time_range_days:1 }),
    widget(clientId('widget'), 'device-health', undefined, 8, 8, 4, 2),
    widget(clientId('widget'), 'online-status', undefined, 8, 10, 4, 2),
  ] }
}

function applyVehicleDefaults(): void {
  const vehicle = vehicles.value.find((row) => row.id === form.value.vehicle_id) ?? selectedVehicle.value
  const metrics = defaultDashboardMetrics(vehicle)
  form.value.metric = metrics[0] ?? 'vehicle.speed'
  form.value.metrics = metrics.join(', ')
  form.value.unit = metricDefinition(form.value.metric).unit
}

function applyResponsiveGrid(width: number): void {
  const columns = width < 700 ? 1 : width < 1050 ? 6 : 12
  narrowCanvas.value = columns === 1
  if (columns === canvasColumns) return
  canvasColumns = columns
  grid?.column?.(columns, 'list')
  grid?.enableMove?.(columns === 12 && editing.value)
  grid?.enableResize?.(columns === 12 && editing.value)
}

function initializeGrid(): void {
  if (!gridElement.value || grid) return
  grid = GridStack.init({ column:12, cellHeight:72, margin:8, animate:true, float:true, staticGrid:!editing.value }, gridElement.value) ?? undefined
  grid?.on('change', (_event, items: GridStackNode[]) => {
    if (canvasColumns !== 12) return
    for (const item of items) {
      const id = item.el?.dataset.widgetId
      const currentWidget = active.value?.layout.widgets.find((row) => row.id === id)
      if (currentWidget) {
        currentWidget.x = item.x ?? currentWidget.x
        currentWidget.y = item.y ?? currentWidget.y
        currentWidget.w = item.w ?? currentWidget.w
        currentWidget.h = item.h ?? currentWidget.h
      }
    }
  })
  resizeObserver = new ResizeObserver(([entry]) => {
    if (entry) applyResponsiveGrid(entry.contentRect.width)
  })
  resizeObserver.observe(gridElement.value)
  applyResponsiveGrid(gridElement.value.clientWidth)
}

function destroyGrid(): void {
  resizeObserver?.disconnect()
  resizeObserver = undefined
  grid?.destroy(false)
  grid = undefined
  canvasColumns = 12
}

async function load(): Promise<void> {
  ;[dashboards.value, vehicles.value] = await Promise.all([
    api<Dashboard[]>('/dashboards'),
    api<Vehicle[]>('/vehicles'),
  ])
  const existingOverview = dashboards.value.find((dashboard) => dashboard.layout.preset?.startsWith('overview-'))
  if (!existingOverview) {
    const created = await api<Dashboard>('/dashboards', {
      method:'POST',
      body:JSON.stringify({ name:t('dashboards.defaultName'), is_default:true, layout:premadeLayout(vehicles.value[0]?.id) }),
    })
    dashboards.value = [...dashboards.value.map((dashboard) => ({ ...dashboard, is_default:false })), created]
  } else if (existingOverview.layout.preset !== OVERVIEW_PRESET) {
    const updated = await api<Dashboard>(`/dashboards/${existingOverview.id}`, {
      method:'PUT',
      body:JSON.stringify({ name:existingOverview.name, is_default:existingOverview.is_default, layout:premadeLayout(vehicles.value[0]?.id) }),
    })
    dashboards.value = dashboards.value.map((dashboard) => dashboard.id === updated.id ? updated : dashboard)
  }
  const initial = dashboards.value.find((row) => row.is_default) ?? dashboards.value[0]
  if (!initial) return
  activeId.value = initial.id
  selectedVehicleId.value = vehicles.value[0]?.id ?? ''
  applyVehicleDefaults()
  await nextTick()
  initializeGrid()
}

function selectVehicle(id: string): void {
  if (vehicles.value.some((vehicle) => vehicle.id === id)) selectedVehicleId.value = id
}

function connectLiveEvents(): void {
  eventSource = openLiveEventStream({
    onStatus: (status) => { liveStatus.value = status },
    onVehicleStates: (nextVehicles) => {
      vehicles.value = nextVehicles
      if (!nextVehicles.some((vehicle) => vehicle.id === selectedVehicleId.value)) selectedVehicleId.value = nextVehicles[0]?.id ?? ''
    },
    onSessionExpired: () => window.location.assign(`/login?next=${encodeURIComponent(window.location.pathname)}`),
  })
}

provide(dashboardRuntimeKey, { vehicles, selectedVehicleId, liveStatus, selectVehicle })

async function selectDashboard(id: string): Promise<void> {
  if (id === activeId.value || editing.value) return
  destroyGrid()
  activeId.value = id
  await nextTick()
  initializeGrid()
}

async function setEditing(value: boolean): Promise<void> {
  destroyGrid()
  editing.value = value
  await nextTick()
  initializeGrid()
}

async function beginEdit(): Promise<void> {
  actionsOpen.value = false
  editSnapshot = cloneDashboards(dashboards.value)
  await setEditing(true)
}

function openCreate(): void {
  actionsOpen.value = false
  creating.value = true
}

async function cancelEdit(): Promise<void> {
  if (editSnapshot) dashboards.value = cloneDashboards(editSnapshot)
  editSnapshot = null
  await setEditing(false)
}

async function createDashboard(): Promise<void> {
  const name = newDashboardName.value.trim()
  if (!name) return
  const created = await api<Dashboard>('/dashboards', {
    method:'POST',
    body:JSON.stringify({ name, is_default:false, layout:{ widgets:[] } }),
  })
  dashboards.value.push(created)
  creating.value = false
  newDashboardName.value = ''
  await selectDashboard(created.id)
  await beginEdit()
}

async function addWidget(): Promise<void> {
  if (!active.value) return
  const definition = widgetRegistry[form.value.type]
  if (!definition) return
  const newWidget: DashboardWidget = {
    id:clientId('widget'), type:definition.type, x:0, y:0,
    w:definition.defaultSize.w, h:definition.defaultSize.h,
    ...(form.value.title ? { title:form.value.title } : {}),
    ...(form.value.vehicle_id ? { vehicle_id:form.value.vehicle_id } : {}),
    ...(definition.needsMetric ? { metric:form.value.metric, unit:form.value.unit } : {}),
    ...(definition.needsMetrics ? { metrics:[...new Set(form.value.metrics.split(',').map((value) => value.trim()).filter(Boolean))] } : {}),
    ...(['time-series', 'multi-series'].includes(definition.type) ? { time_range_days:form.value.time_range_days } : {}),
  }
  active.value.layout.widgets.push(newWidget)
  configuring.value = false
  await nextTick()
  const element = gridElement.value?.querySelector<HTMLElement>(`[data-widget-id="${newWidget.id}"]`)
  if (element) grid?.makeWidget(element)
  if (gridElement.value) applyResponsiveGrid(gridElement.value.clientWidth)
}

function removeWidget(id: string): void {
  const element = gridElement.value?.querySelector<HTMLElement>(`[data-widget-id="${id}"]`)
  if (element) grid?.removeWidget(element, false)
  if (active.value) active.value.layout.widgets = active.value.layout.widgets.filter((row) => row.id !== id)
}

async function save(showMessage = true): Promise<void> {
  if (!active.value) return
  saving.value = true
  try {
    const updated = await api<Dashboard>(`/dashboards/${active.value.id}`, {
      method:'PUT',
      body:JSON.stringify({ name:active.value.name.trim(), is_default:active.value.is_default, layout:active.value.layout }),
    })
    dashboards.value = dashboards.value.map((row) => row.id === updated.id ? updated : updated.is_default ? { ...row, is_default:false } : row)
    if (showMessage) {
      message.value = t('dashboards.saved')
      window.setTimeout(() => message.value = '', 1800)
      editSnapshot = null
      await setEditing(false)
    }
  } finally {
    saving.value = false
  }
}

function makeDefault(): void {
  if (!active.value || active.value.is_default) return
  dashboards.value.forEach((dashboard) => { dashboard.is_default = dashboard.id === active.value?.id })
  active.value.is_default = true
}

async function deleteActive(): Promise<void> {
  if (!active.value || dashboards.value.length === 1 || !window.confirm(t('dashboards.deleteConfirm'))) return
  const deletedId = active.value.id
  const wasDefault = active.value.is_default
  await api(`/dashboards/${deletedId}`, { method:'DELETE' })
  dashboards.value = dashboards.value.filter((row) => row.id !== deletedId)
  const next = dashboards.value[0]
  if (!next) return
  if (wasDefault) {
    next.is_default = true
    const updated = await api<Dashboard>(`/dashboards/${next.id}`, {
      method:'PUT',
      body:JSON.stringify({ name:next.name, is_default:true, layout:next.layout }),
    })
    dashboards.value[0] = updated
  }
  editing.value = false
  editSnapshot = null
  await selectDashboard(next.id)
}

watch([() => form.value.vehicle_id, selectedVehicleId], applyVehicleDefaults)
watch(() => form.value.metric, (metric) => { form.value.unit = metricDefinition(metric).unit })
onMounted(async () => { await load(); connectLiveEvents() })
onBeforeUnmount(() => { destroyGrid(); eventSource?.close() })
</script>

<template>
  <div class="page dashboard-page">
    <header class="dashboard-topbar">
      <div class="dashboard-heading"><span class="eyebrow">{{ t('dashboards.eyebrow') }}</span><h1>{{ active?.name || t('dashboards.title') }}</h1></div>
      <div v-if="!editing" class="dashboard-view-actions" @keydown.esc="actionsOpen=false">
        <button class="dashboard-menu-button" type="button" :aria-label="t('dashboards.actions')" aria-haspopup="menu" :aria-expanded="actionsOpen" @click="actionsOpen=!actionsOpen"><AppIcon name="more" :size="19" /></button>
        <div v-if="actionsOpen" class="dashboard-menu panel" role="menu">
          <button type="button" role="menuitem" @click="beginEdit"><AppIcon name="edit" :size="15" />{{ t('dashboards.edit') }}</button>
          <button type="button" role="menuitem" @click="openCreate"><AppIcon name="plus" :size="15" />{{ t('dashboards.new') }}</button>
        </div>
      </div>
      <nav class="dashboard-tabs" :aria-label="t('dashboards.title')">
        <button v-for="dashboard in dashboards" :key="dashboard.id" :class="{ active:dashboard.id===activeId }" :disabled="editing && dashboard.id!==activeId" @click="selectDashboard(dashboard.id)">
          {{ dashboard.name }} <span v-if="dashboard.is_default">{{ t('dashboards.defaultBadge') }}</span>
        </button>
      </nav>
    </header>
    <p v-if="message" class="dashboard-message success" role="status">{{ message }}</p>

    <section v-if="editing && active" class="dashboard-editor-bar panel">
      <div class="dashboard-name"><label :for="`dashboard-name-${active.id}`">{{ t('dashboards.name') }}</label><input :id="`dashboard-name-${active.id}`" v-model="active.name" class="dashboard-name-input" /></div>
      <p>{{ t('dashboards.canvasHint') }}</p>
      <div class="canvas-controls">
        <button v-if="!active.is_default" class="text-button" @click="makeDefault">{{ t('dashboards.makeDefault') }}</button>
        <span v-else class="default-label">{{ t('dashboards.defaultBadge') }}</span>
        <button v-if="!activeIsPremade" class="text-button danger" :disabled="dashboards.length===1" @click="deleteActive">{{ t('dashboards.delete') }}</button>
        <button class="button secondary" @click="configuring=true"><AppIcon name="plus" :size="15" />{{ t('dashboards.addWidget') }}</button>
        <button class="button secondary" @click="cancelEdit">{{ t('common.cancel') }}</button>
        <button class="button" :disabled="saving" @click="save()">{{ t('common.save') }}</button>
      </div>
    </section>

    <section v-if="active && (editing || active.layout.widgets.length)" :class="['dashboard-canvas', { 'is-editing':editing }]">
      <div ref="gridElement" class="grid-stack min-h-80" :class="{ 'is-narrow':narrowCanvas }">
        <div v-for="currentWidget in active.layout.widgets" :key="currentWidget.id" class="grid-stack-item" :data-widget-id="currentWidget.id" :data-widget-type="currentWidget.type" :gs-x="currentWidget.x" :gs-y="currentWidget.y" :gs-w="currentWidget.w" :gs-h="currentWidget.h">
          <div class="grid-stack-item-content panel">
            <button v-if="editing" class="widget-remove" :aria-label="t('common.delete')" @click="removeWidget(currentWidget.id)"><AppIcon name="close" :size="14" /></button>
            <component :is="widgetRegistry[currentWidget.type]?.component" :widget="currentWidget" />
          </div>
        </div>
      </div>
      <div v-if="!active.layout.widgets.length" class="empty">{{ t('dashboards.empty') }}</div>
    </section>

    <AppModal :open="configuring" :title="t('dashboards.addWidget')" @close="configuring=false">
      <form class="dashboard-modal-form widget-modal-form" @submit.prevent="addWidget">
        <label class="field"><span>{{ t('common.type') }}</span><AppSelect v-model="form.type"><option v-for="definition in definitions" :key="definition.type" :value="definition.type">{{ t(definition.titleKey) }}</option></AppSelect></label>
        <label v-if="widgetRegistry[form.type]?.configSchema.fields.includes('vehicle_id')" class="field"><span>{{ t('devices.vehicle') }}</span><AppSelect v-model="form.vehicle_id"><option value="">{{ t('dashboards.selectedVehicle') }}</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect><small class="field-hint">{{ t('dashboards.selectedVehicleHint') }}</small></label>
        <label v-if="widgetRegistry[form.type]?.needsMetric" class="field"><span>{{ t('history.metric') }}</span><input v-model="form.metric" class="input" list="metric-options" /><datalist id="metric-options"><option v-for="name in availableMetrics" :key="name">{{ name }}</option></datalist></label>
        <label v-if="widgetRegistry[form.type]?.needsMetrics" class="field"><span>{{ t('dashboards.metrics') }}</span><input v-model="form.metrics" class="input" :placeholder="metricSuggestion" /></label>
        <label v-if="['time-series','multi-series'].includes(form.type)" class="field"><span>{{ t('dashboards.timeRange') }}</span><AppSelect v-model="form.time_range_days"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></AppSelect></label>
        <label class="field"><span>{{ t('common.title') }}</span><input v-model="form.title" class="input" /></label>
        <div class="form-actions"><button class="button">{{ t('dashboards.addWidget') }}</button><button class="button secondary" type="button" @click="configuring=false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>

    <AppModal :open="creating" :title="t('dashboards.new')" @close="creating=false">
      <form class="dashboard-modal-form create-dashboard-form" @submit.prevent="createDashboard">
        <label class="field"><span>{{ t('dashboards.name') }}</span><input v-model="newDashboardName" class="input" required autofocus /></label>
        <div class="form-actions"><button class="button">{{ t('dashboards.create') }}</button><button class="button secondary" type="button" @click="creating=false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.field-hint{color:var(--muted);font-size:9px;line-height:1.45}
.dashboard-page{max-width:none}.dashboard-topbar{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:15px 20px;margin-bottom:34px;padding:0 4px;border-bottom:1px solid var(--line)}.dashboard-heading h1{margin:0;font-size:clamp(25px,2.4vw,34px);font-weight:600;letter-spacing:-.045em}.dashboard-view-actions{position:relative;display:flex;align-items:center}.dashboard-menu-button{width:38px;height:38px;display:grid;place-items:center;color:var(--muted);background:transparent;border:1px solid transparent;border-radius:8px;cursor:pointer}.dashboard-menu-button:hover,.dashboard-menu-button[aria-expanded="true"]{color:var(--accent);background:var(--accent-soft);border-color:color-mix(in srgb,var(--accent) 25%,var(--line))}.dashboard-menu{position:absolute;z-index:1400;top:44px;right:0;width:190px;padding:5px;box-shadow:var(--shadow)}.dashboard-menu button{width:100%;display:flex;align-items:center;gap:9px;padding:10px;color:var(--text);background:transparent;border:0;border-radius:6px;font-size:10px;text-align:left;cursor:pointer}.dashboard-menu button:hover{color:var(--accent);background:var(--accent-soft)}.dashboard-tabs{grid-column:1/-1;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}.dashboard-tabs::-webkit-scrollbar{display:none}.dashboard-tabs button{position:relative;flex:0 0 auto;padding:10px 13px 13px;color:var(--muted);background:transparent;border:0;cursor:pointer}.dashboard-tabs button::after{content:"";position:absolute;right:10px;bottom:0;left:10px;height:2px;background:transparent;border-radius:2px}.dashboard-tabs button.active{color:var(--text)}.dashboard-tabs button.active::after{background:var(--accent)}.dashboard-tabs button:disabled{opacity:.48;cursor:not-allowed}.dashboard-tabs span{margin-left:5px;color:var(--accent);font-size:7px;text-transform:uppercase;letter-spacing:.08em}.dashboard-message{position:fixed;right:24px;bottom:24px;z-index:1200;margin:0;padding:11px 14px;background:var(--panel);border:1px solid var(--line);border-radius:8px;box-shadow:var(--shadow)}.dashboard-editor-bar{display:grid;grid-template-columns:minmax(210px,320px) minmax(160px,1fr) auto;align-items:end;gap:15px;margin:-18px 4px 14px;padding:13px 15px;border-color:color-mix(in srgb,var(--accent) 45%,var(--line))}.dashboard-editor-bar>p{align-self:center;margin:0;color:var(--muted);font-size:9px;line-height:1.45}.dashboard-name{display:grid;gap:6px}.dashboard-name label{color:var(--muted);font-size:9px;font-weight:600}.dashboard-name-input{width:100%;min-height:38px;padding:7px 9px;color:var(--text);background:var(--input);border:1px solid var(--line);border-radius:7px;font-size:13px;font-weight:600}.dashboard-name-input:focus{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-soft);outline:none}.canvas-controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:8px;color:var(--muted);font-size:10px}.text-button{padding:7px;color:var(--accent);background:none;border:0;cursor:pointer}.text-button:disabled{opacity:.4;cursor:not-allowed}.text-button.danger{color:var(--danger)}.default-label{padding:5px 7px;background:var(--accent-soft);border-radius:6px;color:var(--accent)}.dashboard-canvas{min-width:0}.grid-stack{padding:0;background:transparent}.dashboard-canvas.is-editing{margin:0 4px;padding:7px;background:color-mix(in srgb,var(--accent-soft) 28%,transparent);border:1px dashed color-mix(in srgb,var(--accent) 45%,var(--line));border-radius:10px}.grid-stack-item-content{inset:4px!important;min-width:0;overflow:hidden!important}.dashboard-canvas:not(.is-editing) .grid-stack-item-content{box-shadow:var(--shadow-soft)}.grid-stack.is-narrow .grid-stack-item-content{inset:3px!important}.widget-remove{position:absolute;right:8px;top:7px;z-index:600;width:29px;height:29px;display:grid;place-items:center;color:var(--danger);background:var(--panel);border:1px solid color-mix(in srgb,var(--danger) 35%,var(--line));border-radius:7px;cursor:pointer;box-shadow:var(--shadow-soft)}.widget-remove:hover{color:#fff;background:var(--danger);border-color:var(--danger)}.dashboard-modal-form{display:grid;gap:16px}.dashboard-modal-form .form-actions{justify-content:flex-end;margin-top:2px}
@media(max-width:980px){.dashboard-editor-bar{grid-template-columns:1fr}.canvas-controls{justify-content:flex-start}}@media(max-width:560px){.dashboard-topbar{grid-template-columns:minmax(0,1fr) auto}.dashboard-heading h1{font-size:26px}.dashboard-tabs button{padding-inline:10px}.dashboard-editor-bar{margin-inline:0}.canvas-controls .button{flex:1}.dashboard-canvas.is-editing{margin-inline:0}}
</style>
