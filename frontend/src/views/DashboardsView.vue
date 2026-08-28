<script setup lang="ts">
import { GridStack, type GridStackNode } from 'gridstack'
import { computed, nextTick, onBeforeUnmount, onMounted, provide, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { clientId } from '../clientId'
import { api, errorMessage } from '../api/client'
import type { LiveConnectionStatus } from '../api/events'
import { useLiveRefresh, useLiveVehicles } from '../api/live'
import type { Dashboard, DashboardWidget, SelectedSegment, Vehicle } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
import AppSelect from '../components/AppSelect.vue'
import { defaultDashboardMetrics, metricDefinition, reportedChartMetrics } from '../vehicleDisplay'
import { isGeneralChoice, needsSpecificData, normalizeWidget, widgetRegistry } from '../widgets/registry'
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
const dataVersion = ref(0)
const selectedSegment = ref<SelectedSegment | null>(null)
const form = ref({ type:'metric-card', vehicle_id:'', metric:'vehicle.speed', metrics:'vehicle.speed', x_metric:'battery.soc', y_metric:'charging.power', title:'', unit:'km/h', time_range_days:1, hide_when_empty:false })
let grid: GridStack | undefined
let resizeObserver: ResizeObserver | undefined
let canvasColumns = 12
let editSnapshot: Dashboard[] | null = null
const OVERVIEW_PRESET = 'overview-v8'

function cloneDashboards(value: Dashboard[]): Dashboard[] {
  return JSON.parse(JSON.stringify(value)) as Dashboard[]
}

const active = computed(() => dashboards.value.find((dashboard) => dashboard.id === activeId.value) ?? null)

function widgetVehicle(currentWidget: DashboardWidget): Vehicle | undefined {
  const id = currentWidget.vehicle_id || selectedVehicleId.value
  return vehicles.value.find((row) => row.id === id)
}

/**
 * Widgets rendered on the canvas.
 *
 * Editing always shows every widget, otherwise a hidden one could never be removed
 * or reconfigured. Viewing drops the widgets that opted into hiding and have nothing
 * to show for the selected vehicle, so an EV card does not sit empty on a petrol car.
 */
const visibleWidgets = computed<DashboardWidget[]>(() => {
  const widgets = active.value?.layout.widgets ?? []
  if (editing.value) return widgets
  return widgets.filter((currentWidget) => {
    if (!currentWidget.settings?.hide_when_empty) return true
    const definition = widgetRegistry[currentWidget.type]
    return !definition?.isEmpty?.(currentWidget, widgetVehicle(currentWidget))
  })
})
const supportsHiding = computed(() => Boolean(chosenDefinition.value?.isEmpty))
const activeIsPremade = computed(() => active.value?.layout.preset?.startsWith('overview-') ?? false)
const definitions = computed(() => Object.values(widgetRegistry))
/**
 * The picker separates cards that suit any vehicle from cards bound to named
 * data, so choosing one is an informed decision rather than a surprise later.
 * Both groups read the same `general` flag the premade layout does.
 */
const pickerGroups = computed(() => {
  const choices = [
    ...definitions.value.map((definition) => ({ value: definition.type, label: t(definition.titleKey) })),
  ]
  return [
    { label: t('dashboards.groupGeneral'), options: choices.filter((choice) => isGeneralChoice(choice.value)) },
    { label: t('dashboards.groupSpecific'), options: choices.filter((choice) => !isGeneralChoice(choice.value)) },
  ]
})
const chosenDefinition = computed(() => widgetRegistry[form.value.type])
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

const hideWhenEmpty = { settings:{ hide_when_empty:true } }

/**
 * The premade Overview, laid out in the order an owner asks: what is it doing,
 * how fast, how much is left, where is it, what happened recently, what did it
 * cost.
 *
 * A card hides only when it needs non-standard data: battery state, charging, a
 * charge curve. Everything else shows unconditionally and answers for itself,
 * because an empty state on standard data is information rather than noise. Both
 * speed cards are standard: `vehicle.speed` resolves from the CAN reading or from
 * the GNSS fix, so either kind of vehicle can answer them.
 *
 * Composition rules this layout keeps, because a premade dashboard is the one
 * layout nobody chose and so the one that has to look designed:
 *
 * - every grid row is covered across all twelve columns, so no row reads ragged;
 * - a row holds cards of one height, so their tops and bottoms line up;
 * - the cards that may hide sit at the end of their row, so the gap a hidden one
 *   leaves is trailing space rather than a hole punched in the middle.
 */
function premadeLayout(vehicleId?: string): Dashboard['layout'] {
  void vehicleId
  // Ordered by the questions somebody opening this actually has: what is the car
  // doing, where is it, how much is left, and is the agent still reporting. The
  // status card carries the vehicle's state and the agent's separately, which is
  // why it comes first and why nothing else needs to repeat either.
  return { preset:OVERVIEW_PRESET, widgets: [
    // Which vehicle everything below is about.
    widget(clientId('widget'), 'vehicle-selector', undefined, 0, 0, 12, 1),
    // What is it doing, how fast, how much is left. Four equal cards; the two
    // that need battery data trail so hiding them shortens the row from the end.
    widget(clientId('widget'), 'online-status', undefined, 0, 1, 3, 2),
    widget(clientId('widget'), 'metric-card', undefined, 3, 1, 3, 2, { metric:'vehicle.speed' }),
    widget(clientId('widget'), 'battery-gauge', undefined, 6, 1, 3, 2, hideWhenEmpty),
    widget(clientId('widget'), 'charging', undefined, 9, 1, 3, 2, hideWhenEmpty),
    // Where is it, and what has it been up to. The map is the one hero card, and
    // the two lists beside it stack to exactly its height.
    widget(clientId('widget'), 'route-map', undefined, 0, 3, 8, 6, { time_range_days:1 }),
    widget(clientId('widget'), 'activity-feed', undefined, 8, 3, 4, 3, { time_range_days:7 }),
    widget(clientId('widget'), 'telemetry-list', undefined, 8, 6, 4, 3),
    // What did it cost. Half and half: both hold a grid of readings that wrapped
    // badly at a third of the width.
    widget(clientId('widget'), 'segment-stats', undefined, 0, 9, 6, 2, { time_range_days:7 }),
    widget(clientId('widget'), 'period-stats', undefined, 6, 9, 6, 2, { time_range_days:7 }),
    // How it has moved. The charge curve trails, being the one that may hide.
    widget(clientId('widget'), 'time-series', undefined, 0, 11, 6, 4, { metric:'vehicle.speed', time_range_days:1 }),
    widget(clientId('widget'), 'xy-chart', undefined, 6, 11, 6, 4, { x_metric:'battery.soc', y_metric:'charging.power', time_range_days:7, ...hideWhenEmpty }),
  ] }
}

function applyVehicleDefaults(): void {
  const vehicle = vehicles.value.find((row) => row.id === form.value.vehicle_id) ?? selectedVehicle.value
  const metrics = defaultDashboardMetrics(vehicle)
  form.value.metric = metrics[0] ?? 'vehicle.speed'
  form.value.metrics = metrics.join(', ')
  form.value.unit = metricDefinition(form.value.metric).unit
  // A generic chart is offered two axes only when the vehicle really reports two
  // distinct ones. Otherwise both stay empty and the card asks to be configured,
  // which is honest where a guessed pair of EV metrics would not be.
  const pair = reportedChartMetrics(vehicle)
  const usable = pair.length >= 2
  form.value.x_metric = usable ? pair[0]! : ''
  form.value.y_metric = usable ? pair[1]! : ''
}

/** Hiding defaults on only for a card that would need non-standard data. */
function applyTierDefaults(): void {
  const definition = chosenDefinition.value
  if (!definition) return
  form.value.hide_when_empty = needsSpecificData({
    id:'draft', type:definition.type, x:0, y:0, w:0, h:0,
    ...(definition.needsMetric ? { metric:form.value.metric } : {}),
    ...(definition.needsMetrics ? { metrics:form.value.metrics.split(',').map((value) => value.trim()).filter(Boolean) } : {}),
    ...(definition.configSchema.fields.includes('x_metric') ? { x_metric:form.value.x_metric, y_metric:form.value.y_metric } : {}),
  })
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

/**
 * Restore every item's gs-* attributes from the widget model.
 *
 * Gridstack rewrites those attributes as it lays out, and the responsive remap to
 * six columns leaves six-column coordinates behind. Vue never patches them back,
 * because the value it binds never changed, so the next GridStack.init would read
 * that stale layout as the truth and scatter the cards across the wide grid. The
 * model is the layout; the attributes are restored from it before every init.
 */
function applyModelCoordinates(): void {
  for (const currentWidget of visibleWidgets.value) {
    const element = gridElement.value?.querySelector<HTMLElement>(`[data-widget-id="${currentWidget.id}"]`)
    if (!element) continue
    element.setAttribute('gs-x', String(currentWidget.x))
    element.setAttribute('gs-y', String(currentWidget.y))
    element.setAttribute('gs-w', String(currentWidget.w))
    element.setAttribute('gs-h', String(currentWidget.h))
  }
}

function initializeGrid(): void {
  if (!gridElement.value || grid) return
  applyModelCoordinates()
  grid = GridStack.init({ column:12, cellHeight:76, margin:6, animate:true, float:true, staticGrid:!editing.value }, gridElement.value) ?? undefined
  grid?.on('change', (_event, items: GridStackNode[]) => {
    // Only a person dragging changes the layout. Viewing compacts the canvas to
    // close the space a hidden card leaves, and at fewer than twelve columns the
    // whole thing is remapped; both are ways of drawing this layout, not new
    // layouts, and writing either back turned every redraw into an edit.
    if (!editing.value || canvasColumns !== 12) return
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
  // No compaction on view. It existed to close the hole a hidden card left, and
  // it closed that hole by moving its neighbours, so a card saved in one column
  // was drawn in another. The layout solves this structurally instead: a card
  // that may hide sits at the end of its row, so what it leaves is trailing
  // space. What is stored is now always what is drawn.
}

function destroyGrid(): void {
  resizeObserver?.disconnect()
  resizeObserver = undefined
  grid?.destroy(false)
  grid = undefined
  canvasColumns = 12
}

async function load(): Promise<void> {
  message.value = ''
  try {
    await fetchDashboards()
  } catch (reason) {
    message.value = errorMessage(reason, t('common.error'))
  }
}

async function fetchDashboards(): Promise<void> {
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
  for (const dashboard of dashboards.value) {
    if (Array.isArray(dashboard?.layout?.widgets)) dashboard.layout.widgets = dashboard.layout.widgets.map(normalizeWidget)
  }
  const initial = dashboards.value.find((row) => row.is_default) ?? dashboards.value[0]
  if (!initial) return
  activeId.value = initial.id
  selectedVehicleId.value = vehicles.value[0]?.id ?? ''
  applyVehicleDefaults()
  applyTierDefaults()
  await nextTick()
  initializeGrid()
}

function selectVehicle(id: string): void {
  if (!vehicles.value.some((vehicle) => vehicle.id === id)) return
  selectedVehicleId.value = id
  selectedSegment.value = null
}

function selectSegment(segment: SelectedSegment | null): void {
  selectedSegment.value = segment
}

function connectLiveEvents(): void {
  const live = useLiveVehicles()
  watch(live.status, (status) => { liveStatus.value = status }, { immediate: true })
  // History and segment widgets cannot see new telemetry in the snapshot they are
  // handed, so one throttled counter tells them all to refetch at once.
  useLiveRefresh(() => { dataVersion.value += 1 })
  watch(live.vehicles, (nextVehicles) => {
    if (!nextVehicles.length) return
    vehicles.value = nextVehicles
    if (!nextVehicles.some((vehicle) => vehicle.id === selectedVehicleId.value)) selectedVehicleId.value = nextVehicles[0]?.id ?? ''
  }, { immediate: true })
}

provide(dashboardRuntimeKey, { vehicles, selectedVehicleId, selectedSegment, liveStatus, dataVersion, selectVehicle, selectSegment })

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
  const definition = chosenDefinition.value
  if (!definition) return
  const newWidget: DashboardWidget = {
    id:clientId('widget'), type:definition.type, x:0, y:0,
    w:definition.defaultSize.w, h:definition.defaultSize.h,
    ...(form.value.title ? { title:form.value.title } : {}),
    ...(form.value.vehicle_id ? { vehicle_id:form.value.vehicle_id } : {}),
    ...(definition.needsMetric ? { metric:form.value.metric, unit:form.value.unit } : {}),
    ...(definition.needsMetrics ? { metrics:[...new Set(form.value.metrics.split(',').map((value) => value.trim()).filter(Boolean))] } : {}),
    ...(definition.configSchema.fields.includes('time_range_days') ? { time_range_days:form.value.time_range_days } : {}),
    ...(definition.configSchema.fields.includes('x_metric') ? { x_metric:form.value.x_metric, y_metric:form.value.y_metric } : {}),
    ...(definition.isEmpty && form.value.hide_when_empty ? { settings:{ hide_when_empty:true } } : {}),
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

watch(() => visibleWidgets.value.map((row) => row.id).join(','), async (next, previous) => {
  if (!grid || next === previous) return
  destroyGrid()
  await nextTick()
  initializeGrid()
})
watch([() => form.value.vehicle_id, selectedVehicleId], applyVehicleDefaults)
watch([() => form.value.type, () => form.value.metric, () => form.value.metrics], applyTierDefaults)
watch(() => form.value.metric, (metric) => { form.value.unit = metricDefinition(metric).unit })
onMounted(async () => { await load(); connectLiveEvents() })
onBeforeUnmount(destroyGrid)
</script>

<template>
  <div class="page dashboard-page">
    <header class="dashboard-topbar">
      <h1>{{ active?.name || t('dashboards.title') }}</h1>
      <div v-if="!editing" class="dashboard-view-actions" @keydown.esc="actionsOpen=false">
        <button class="dashboard-menu-button" type="button" :aria-label="t('dashboards.actions')" aria-haspopup="menu" :aria-expanded="actionsOpen" @click="actionsOpen=!actionsOpen"><AppIcon name="more" :size="18" /></button>
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

    <section v-if="editing && active" class="dashboard-editor-bar">
      <div class="dashboard-name"><label :for="`dashboard-name-${active.id}`">{{ t('dashboards.name') }}</label><input :id="`dashboard-name-${active.id}`" v-model="active.name" class="input dashboard-name-input" /></div>
      <p class="editor-hint">{{ t('dashboards.canvasHint') }}</p>
      <div class="canvas-controls">
        <button v-if="!active.is_default" class="link-button" @click="makeDefault">{{ t('dashboards.makeDefault') }}</button>
        <span v-else class="default-label">{{ t('dashboards.defaultBadge') }}</span>
        <button v-if="!activeIsPremade" class="link-button danger" :disabled="dashboards.length===1" @click="deleteActive">{{ t('dashboards.delete') }}</button>
        <button class="button secondary" @click="configuring=true"><AppIcon name="plus" :size="15" />{{ t('dashboards.addWidget') }}</button>
        <button class="button secondary" @click="cancelEdit">{{ t('common.cancel') }}</button>
        <button class="button" :disabled="saving" @click="save()">{{ t('common.save') }}</button>
      </div>
    </section>

    <section v-if="active && (editing || active.layout.widgets.length)" :class="['dashboard-canvas', { 'is-editing':editing }]">
      <div ref="gridElement" class="grid-stack min-h-80" :class="{ 'is-narrow':narrowCanvas }">
        <div v-for="currentWidget in visibleWidgets" :key="currentWidget.id" class="grid-stack-item" :data-widget-id="currentWidget.id" :data-widget-type="currentWidget.type" :gs-x="currentWidget.x" :gs-y="currentWidget.y" :gs-w="currentWidget.w" :gs-h="currentWidget.h">
          <div class="grid-stack-item-content panel">
            <button v-if="editing" class="widget-remove" :aria-label="t('common.delete')" @click="removeWidget(currentWidget.id)"><AppIcon name="close" :size="13" /></button>
            <component :is="widgetRegistry[currentWidget.type]?.component" :widget="currentWidget" />
          </div>
        </div>
      </div>
      <div v-if="!active.layout.widgets.length" class="empty panel">{{ t('dashboards.empty') }}</div>
    </section>

    <AppModal :open="configuring" :title="t('dashboards.addWidget')" @close="configuring=false">
      <form class="dashboard-modal-form widget-modal-form" @submit.prevent="addWidget">
        <label class="field"><span>{{ t('common.type') }}</span><AppSelect v-model="form.type"><optgroup v-for="group in pickerGroups" :key="group.label" :label="group.label"><option v-for="option in group.options" :key="option.value" :value="option.value">{{ option.label }}</option></optgroup></AppSelect></label>
        <label v-if="chosenDefinition?.configSchema.fields.includes('vehicle_id')" class="field"><span>{{ t('common.vehicle') }}</span><AppSelect v-model="form.vehicle_id"><option value="">{{ t('dashboards.selectedVehicle') }}</option><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></AppSelect><small class="field-hint">{{ t('dashboards.selectedVehicleHint') }}</small></label>
        <label v-if="chosenDefinition?.needsMetric" class="field"><span>{{ t('history.metric') }}</span><input v-model="form.metric" class="input mono" list="metric-options" /><datalist id="metric-options"><option v-for="name in availableMetrics" :key="name">{{ name }}</option></datalist></label>
        <label v-if="chosenDefinition?.needsMetrics" class="field"><span>{{ t('dashboards.metrics') }}</span><input v-model="form.metrics" class="input mono" :placeholder="metricSuggestion" /></label>
        <label v-if="chosenDefinition?.configSchema.fields.includes('time_range_days')" class="field"><span>{{ t('dashboards.timeRange') }}</span><AppSelect v-model="form.time_range_days"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></AppSelect></label>
        <template v-if="chosenDefinition?.configSchema.fields.includes('x_metric')">
          <label class="field"><span>{{ t('dashboards.xMetric') }}</span><input v-model="form.x_metric" class="input mono" list="metric-options" /></label>
          <label class="field"><span>{{ t('dashboards.yMetric') }}</span><input v-model="form.y_metric" class="input mono" list="metric-options" /></label>
        </template>
        <label class="field"><span>{{ t('common.title') }}</span><input v-model="form.title" class="input" /></label>
        <label v-if="supportsHiding" class="widget-toggle"><input v-model="form.hide_when_empty" type="checkbox" /><span>{{ t('dashboards.hideWhenEmpty') }}</span></label>
        <div class="form-actions"><button class="button">{{ t('dashboards.addWidget') }}</button><button class="button ghost" type="button" @click="configuring=false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>

    <AppModal :open="creating" :title="t('dashboards.new')" @close="creating=false">
      <form class="dashboard-modal-form create-dashboard-form" @submit.prevent="createDashboard">
        <label class="field"><span>{{ t('dashboards.name') }}</span><input v-model="newDashboardName" class="input" required autofocus /></label>
        <div class="form-actions"><button class="button">{{ t('dashboards.create') }}</button><button class="button ghost" type="button" @click="creating=false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>
  </div>
</template>

<style scoped>
.dashboard-topbar{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:10px 16px;margin-bottom:20px;border-bottom:1px solid var(--line)}
.dashboard-topbar h1{margin:0;font-size:var(--font-page-title);font-weight:600;letter-spacing:-.015em}
.dashboard-view-actions{position:relative;display:flex;align-items:center}
.dashboard-menu-button{width:30px;height:30px;display:grid;place-items:center;color:var(--muted);background:transparent;border:1px solid transparent;border-radius:var(--radius);cursor:pointer;transition:color .12s,background-color .12s}
.dashboard-menu-button:hover,.dashboard-menu-button[aria-expanded="true"]{color:var(--text);background:var(--panel-2)}
.dashboard-menu{position:absolute;z-index:1400;top:36px;right:0;width:186px;padding:4px;box-shadow:var(--shadow)}
.dashboard-menu button{width:100%;display:flex;align-items:center;gap:9px;padding:8px 9px;color:var(--text);background:transparent;border:0;border-radius:var(--radius);font-size:var(--font-body);text-align:left;cursor:pointer;transition:background-color .12s}
.dashboard-menu button:hover{background:var(--panel-2)}

.dashboard-tabs{grid-column:1/-1;display:flex;gap:2px;overflow-x:auto;scrollbar-width:none}
.dashboard-tabs::-webkit-scrollbar{display:none}
.dashboard-tabs button{position:relative;flex:0 0 auto;padding:8px 10px 10px;color:var(--muted);background:transparent;border:0;font-size:var(--font-body);cursor:pointer;transition:color .12s}
.dashboard-tabs button:hover{color:var(--text)}
.dashboard-tabs button::after{content:"";position:absolute;right:10px;bottom:-1px;left:10px;height:2px;background:transparent}
.dashboard-tabs button.active{color:var(--text);font-weight:500}
.dashboard-tabs button.active::after{background:var(--text)}
.dashboard-tabs button:disabled{opacity:.45;cursor:not-allowed}
.dashboard-tabs span{margin-left:5px;padding:1px 4px;color:var(--muted);background:var(--panel-2);border-radius:var(--radius-sm);font-size:10px;font-weight:400;text-transform:uppercase;letter-spacing:.04em}

.dashboard-message{position:fixed;right:20px;bottom:20px;z-index:1200;margin:0;padding:9px 13px;font-size:var(--font-body);background:var(--panel);border-radius:var(--radius);box-shadow:var(--shadow)}

.dashboard-editor-bar{display:grid;grid-template-columns:minmax(200px,300px) minmax(140px,1fr) auto;align-items:end;gap:14px;margin-bottom:12px;padding-bottom:12px;border-bottom:1px solid var(--line)}
.dashboard-name{display:grid;gap:5px}
.dashboard-name label{color:var(--text);font-size:var(--font-caption);font-weight:500}
.dashboard-name-input{font-weight:500}
.editor-hint{align-self:end;margin:0;padding-bottom:9px;color:var(--muted);font-size:var(--font-caption);line-height:1.45}
.canvas-controls{display:flex;align-items:center;justify-content:flex-end;flex-wrap:wrap;gap:14px}
.default-label{color:var(--muted);font-size:var(--font-caption)}

.dashboard-canvas{min-width:0;margin:-6px}
.grid-stack{padding:0;background:transparent}

.grid-stack-item-content{inset:6px!important;min-width:0;overflow:hidden!important;border-radius:var(--radius-lg)}
.grid-stack.is-narrow .grid-stack-item-content{inset:5px!important}
.widget-remove{position:absolute;right:6px;top:6px;z-index:600;width:24px;height:24px;display:grid;place-items:center;color:var(--danger);background:var(--panel);border:1px solid var(--line-strong);border-radius:var(--radius);cursor:pointer;transition:color .12s,background-color .12s,border-color .12s}
.widget-remove:hover{color:#fff;background:var(--danger);border-color:var(--danger)}

.dashboard-modal-form{display:grid;gap:15px}
.widget-toggle{display:flex;align-items:flex-start;gap:8px;font-size:var(--font-body);line-height:1.45;cursor:pointer}
.widget-toggle input{width:14px;height:14px;margin-top:2px;flex:none;accent-color:var(--accent)}
.dashboard-modal-form .form-actions{justify-content:flex-end;margin-top:2px}

@media(max-width:980px){.dashboard-editor-bar{grid-template-columns:1fr}.canvas-controls{justify-content:flex-start}}
@media(max-width:560px){.dashboard-topbar h1{font-size:20px}.canvas-controls .button{flex:1}}
</style>
