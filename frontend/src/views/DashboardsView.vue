<script setup lang="ts">
import { GridStack, type GridStackNode } from 'gridstack'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Dashboard, DashboardWidget, Vehicle } from '../api/types'
import { defaultDashboardMetrics, metricDefinition } from '../vehicleDisplay'
import { widgetRegistry } from '../widgets/registry'

const { t } = useI18n()
const dashboards = ref<Dashboard[]>([])
const active = ref<Dashboard|null>(null)
const vehicles = ref<Vehicle[]>([])
const gridElement = ref<HTMLDivElement>()
const configuring = ref(false)
const saving = ref(false)
const message = ref('')
const form = ref({type:'metric-card',vehicle_id:'',metric:'vehicle.speed',metrics:'vehicle.speed',title:'',unit:'km/h',time_range_days:1})
let grid: GridStack|undefined
const definitions = computed(()=>Object.values(widgetRegistry))
const metricSuggestion = computed(()=>{
  const vehicle=vehicles.value.find(row=>row.id===form.value.vehicle_id)
  return defaultDashboardMetrics(vehicle).join(', ')
})
const availableMetrics = computed(()=>{
  const vehicle=vehicles.value.find(row=>row.id===form.value.vehicle_id)
  const metrics=new Set(Object.keys(vehicle?.state?.metrics??{}))
  if(vehicle?.state?.position?.speed!==null&&vehicle?.state?.position?.speed!==undefined)metrics.add('vehicle.speed')
  for(const metric of defaultDashboardMetrics(vehicle))metrics.add(metric)
  return [...metrics].sort()
})

function applyVehicleDefaults():void{
  const vehicle=vehicles.value.find(row=>row.id===form.value.vehicle_id)
  const metrics=defaultDashboardMetrics(vehicle)
  form.value.metric=metrics[0]??'vehicle.speed'
  form.value.metrics=metrics.join(', ')
  form.value.unit=metricDefinition(form.value.metric).unit
}

function initializeGrid() {
  if (!gridElement.value || grid) return
  grid=GridStack.init({column:12,cellHeight:72,margin:8,animate:true,float:true},gridElement.value) ?? undefined
  grid?.on('change',(_event,items:GridStackNode[])=>{
    for(const item of items){const id=item.el?.dataset.widgetId;const widget=active.value?.layout.widgets.find(row=>row.id===id);if(widget){widget.x=item.x??widget.x;widget.y=item.y??widget.y;widget.w=item.w??widget.w;widget.h=item.h??widget.h}}
  })
}
async function load(){
  ;[dashboards.value,vehicles.value]=await Promise.all([api<Dashboard[]>('/dashboards'),api<Vehicle[]>('/vehicles')])
  active.value=dashboards.value.find(row=>row.is_default)??dashboards.value[0]??null
  if(!active.value){active.value=await api<Dashboard>('/dashboards',{method:'POST',body:JSON.stringify({name:t('dashboards.defaultName'),is_default:true,layout:{widgets:[]}})})}
  if(vehicles.value[0]){form.value.vehicle_id=vehicles.value[0].id;applyVehicleDefaults()}
  await nextTick();initializeGrid()
}
async function addWidget(){
  if(!active.value)return
  const definition=widgetRegistry[form.value.type];if(!definition)return
  const widget:DashboardWidget={
    id:crypto.randomUUID(),type:definition.type,x:0,y:0,
    w:definition.defaultSize.w,h:definition.defaultSize.h,
    ...(form.value.title?{title:form.value.title}:{}),
    ...(form.value.vehicle_id?{vehicle_id:form.value.vehicle_id}:{}),
    ...(definition.needsMetric?{metric:form.value.metric,unit:form.value.unit}:{}),
    ...(definition.needsMetrics?{metrics:[...new Set(form.value.metrics.split(',').map(value=>value.trim()).filter(Boolean))]}:{}),
    ...(['time-series','multi-series'].includes(definition.type)?{time_range_days:form.value.time_range_days}:{}),
  }
  active.value.layout.widgets.push(widget);configuring.value=false
  await nextTick();const element=gridElement.value?.querySelector<HTMLElement>(`[data-widget-id="${widget.id}"]`);if(element)grid?.makeWidget(element)
}
function removeWidget(id:string){const element=gridElement.value?.querySelector<HTMLElement>(`[data-widget-id="${id}"]`);if(element)grid?.removeWidget(element,false);if(active.value)active.value.layout.widgets=active.value.layout.widgets.filter(row=>row.id!==id)}
async function save(){if(!active.value)return;saving.value=true;active.value=await api<Dashboard>(`/dashboards/${active.value.id}`,{method:'PUT',body:JSON.stringify({name:active.value.name,is_default:active.value.is_default,layout:active.value.layout})});saving.value=false;message.value=t('settings.saved');window.setTimeout(()=>message.value='',1800)}
watch(()=>form.value.vehicle_id,applyVehicleDefaults)
watch(()=>form.value.metric,(metric)=>{form.value.unit=metricDefinition(metric).unit})
onMounted(load);onBeforeUnmount(()=>grid?.destroy(false))
</script>

<template>
  <div class="page">
    <header class="page-header"><div><span class="eyebrow">{{ t('dashboards.eyebrow') }}</span><h1>{{ t('dashboards.title') }}</h1></div><div class="flex gap-2"><button class="button secondary" @click="configuring=true">{{ t('dashboards.addWidget') }}</button><button class="button" :disabled="saving" @click="save">{{ t('dashboards.save') }}</button></div></header>
    <p v-if="message" class="success text-sm">{{ message }}</p>
    <section v-if="active" class="panel dashboard-canvas"><header class="canvas-heading"><div><h2>{{ active.name }}</h2><p>{{ t('dashboards.canvasHint') }}</p></div><span>{{ t('dashboards.widgetCount',{count:active.layout.widgets.length}) }}</span></header><div ref="gridElement" class="grid-stack min-h-80">
      <div v-for="widget in active.layout.widgets" :key="widget.id" class="grid-stack-item" :data-widget-id="widget.id" :gs-x="widget.x" :gs-y="widget.y" :gs-w="widget.w" :gs-h="widget.h"><div class="grid-stack-item-content panel !overflow-hidden"><button class="widget-remove" :aria-label="t('common.delete')" @click="removeWidget(widget.id)">×</button><component :is="widgetRegistry[widget.type]?.component" :widget="widget" /></div></div>
    </div><div v-if="!active.layout.widgets.length" class="empty">{{ t('dashboards.empty') }}</div></section>
    <div v-if="configuring" class="modal-backdrop" @click.self="configuring=false"><form class="panel modal" @submit.prevent="addWidget"><div class="flex items-center justify-between"><h2 class="m-0 text-xl">{{ t('dashboards.addWidget') }}</h2><button class="icon-button" type="button" :aria-label="t('common.close')" @click="configuring=false">×</button></div><label class="field"><span>{{ t('common.type') }}</span><select v-model="form.type" class="select"><option v-for="definition in definitions" :key="definition.type" :value="definition.type">{{ t(definition.titleKey) }}</option></select></label><label v-if="form.type!=='hook-activity'" class="field"><span>{{ t('devices.vehicle') }}</span><select v-model="form.vehicle_id" class="select"><option v-for="vehicle in vehicles" :key="vehicle.id" :value="vehicle.id">{{ vehicle.name }}</option></select></label><label v-if="widgetRegistry[form.type]?.needsMetric" class="field"><span>{{ t('history.metric') }}</span><input v-model="form.metric" class="input" list="metric-options" /><datalist id="metric-options"><option v-for="name in availableMetrics" :key="name">{{ name }}</option></datalist></label><label v-if="widgetRegistry[form.type]?.needsMetrics" class="field"><span>{{ t('dashboards.metrics') }}</span><input v-model="form.metrics" class="input" :placeholder="metricSuggestion" /></label><label v-if="['time-series','multi-series'].includes(form.type)" class="field"><span>{{ t('dashboards.timeRange') }}</span><select v-model="form.time_range_days" class="select"><option :value="1">{{ t('history.day') }}</option><option :value="7">{{ t('history.week') }}</option><option :value="30">{{ t('history.month') }}</option></select></label><label class="field"><span>{{ t('common.title') }}</span><input v-model="form.title" class="input" /></label><button class="button">{{ t('dashboards.addWidget') }}</button></form></div>
  </div>
</template>

<style scoped>
.dashboard-canvas{overflow:hidden}.canvas-heading{height:66px;display:flex;align-items:center;justify-content:space-between;padding:12px 15px;border-bottom:1px solid var(--line)}.canvas-heading h2{margin:0;font-size:14px}.canvas-heading p{margin:4px 0 0;color:var(--muted);font-size:8px}.canvas-heading>span{padding:6px 8px;color:var(--muted);background:var(--panel-2);border-radius:8px;font-size:7px}.grid-stack{padding:8px;background:color-mix(in srgb,var(--panel-2) 50%,var(--panel))}.grid-stack-item-content{inset:4px!important}.widget-remove{position:absolute;right:8px;top:7px;z-index:600;width:25px;height:25px;color:var(--muted);background:var(--panel-2);border:1px solid var(--line);border-radius:50%;cursor:pointer}.widget-remove:hover{color:var(--danger);border-color:var(--danger)}.modal-backdrop{position:fixed;inset:0;z-index:2000;display:grid;place-items:center;padding:20px;background:rgba(0,0,0,.55);backdrop-filter:blur(5px)}.modal{width:min(100%,470px);display:grid;gap:16px;padding:23px}
</style>
