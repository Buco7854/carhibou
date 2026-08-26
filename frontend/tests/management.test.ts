import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import AppSelect from '../src/components/AppSelect.vue'
import VehicleProfileEditor from '../src/components/VehicleProfileEditor.vue'
import DashboardsView from '../src/views/DashboardsView.vue'
import DevicesView from '../src/views/DevicesView.vue'
import ProfilesView from '../src/views/ProfilesView.vue'
import VehiclesView from '../src/views/VehiclesView.vue'
import { jsonResponse, vehicle } from './helpers'

vi.mock('gridstack', () => ({
  GridStack: {
    init: vi.fn(() => ({
      on: vi.fn(), makeWidget: vi.fn(), removeWidget: vi.fn(), destroy: vi.fn(), column:vi.fn(), enableMove:vi.fn(), enableResize:vi.fn(),
    })),
  },
}))

describe('vehicle and dashboard management', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('creates a vehicle through the real form/API contract', async () => {
    let created = false
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (options?.method === 'POST') { created = true; return Promise.resolve(jsonResponse(vehicle, 201)) }
      return Promise.resolve(jsonResponse(created ? [vehicle] : []))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')
    await wrapper.get('input[required]').setValue('Éclair')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const createCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(createCall?.[0]).toBe('/api/v1/vehicles')
    expect(JSON.parse(createCall?.[1]?.body as string).name).toBe('Éclair')
    expect(wrapper.text()).toContain('Éclair')
  })

  it('shows stale device status from the server freshness calculation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/devices')) return Promise.resolve(jsonResponse([{
        id:'d1',vehicle_id:vehicle.id,name:'Pi Zero',credential_version:1,agent_version:'0.1.0',hostname:'car',hardware:{},online:false,last_seen_at:'2026-01-01T00:00:00Z',revoked_at:null,created_at:'2026-01-01T00:00:00Z',
      }]))
      return Promise.resolve(jsonResponse([vehicle]))
    }))
    const wrapper = mount(DevicesView, { global:{plugins:[i18n]} })
    await flushPromises()
    expect(wrapper.text()).toContain('Pi Zero')
    expect(wrapper.text()).toContain('Parked / stale')
  })

  it('shows newly created vehicles in the tracker enrollment selector', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/devices')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith(`/vehicles/${vehicle.id}/enrollments`) && options?.method === 'POST') {
        return Promise.resolve(jsonResponse({ install_command:'install tracker' }, 201))
      }
      return Promise.resolve(jsonResponse([vehicle]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DevicesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    await wrapper.get('.page-header .button').trigger('click')
    expect(wrapper.get('[role="combobox"]').text()).toContain('Éclair')
    await wrapper.get('.enrollment-panel').trigger('submit')
    await flushPromises()

    expect(fetchMock.mock.calls.some((call) => call[0].endsWith(`/vehicles/${vehicle.id}/enrollments`) && call[1]?.method === 'POST')).toBe(true)
  })

  it('filters the vehicle catalog by search and live status locally', async () => {
    const parked = { ...vehicle, id:'vehicle-2', name:'Nimbus', battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{ ...vehicle.state, online:false, metrics:{'fuel.level':48,'engine.rpm':900} } }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [] : [vehicle, parked]))))
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('.search-field input').setValue('Nimbus')
    expect(wrapper.text()).toContain('Nimbus')
    expect(wrapper.find('.vehicle-list').text()).not.toContain('Éclair')
    await wrapper.get('.search-field input').setValue('')
    await wrapper.findAll('.filter-tabs button')[2]!.trigger('click')
    expect(wrapper.find('.vehicle-list').text()).toContain('Nimbus')
    expect(wrapper.find('.vehicle-list').text()).not.toContain('Éclair')
    expect(wrapper.get('.vehicle-card').text()).toContain('Fuel level')
    expect(wrapper.get('.vehicle-card').text()).toContain('48%')
    expect(wrapper.get('.vehicle-card').text()).not.toContain('Battery level')
    i18n.global.locale.value = 'fr'
    await flushPromises()
    expect(wrapper.get('.vehicle-card').text()).toContain('Niveau de carburant')
  })

  it('creates vehicles from a name without asking for telemetry or optional specifications', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, options?: RequestInit) => {
      if (_url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (options?.method === 'POST') return Promise.resolve(jsonResponse(vehicle, 201))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')
    expect(wrapper.text()).not.toContain('Propulsion')
    expect(wrapper.find('input[type="number"][step=".1"]').exists()).toBe(false)
    expect(wrapper.get('[role="dialog"]').text()).not.toContain('Telemetry profile')
    await wrapper.get('input[required]').setValue('Touring')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const createCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    const body = JSON.parse(createCall?.[1]?.body as string)
    expect(body).not.toHaveProperty('propulsion_type')
    expect(body).not.toHaveProperty('battery_nominal_capacity_kwh')
    expect(body).not.toHaveProperty('vehicle_profile')
  })

  it('uploads and removes a vehicle photo through the media controls', async () => {
    let photoUrl: string | null = null
    const vehicleWithoutTelemetry = { ...vehicle, state: { ...vehicle.state, position: null, metrics: {} } }
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/vehicles/vehicle-1/photo') && options?.method === 'PUT') {
        photoUrl = '/api/v1/vehicles/vehicle-1/photo?v=abc123'
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url.endsWith('/vehicles/vehicle-1/photo') && options?.method === 'DELETE') {
        photoUrl = null
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse([{ ...vehicleWithoutTelemetry, photo_url: photoUrl }]))
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()

    expect(wrapper.get('.vehicle-photo-placeholder').attributes('aria-label')).toBe('No photo for Éclair')
    expect(wrapper.find('.vehicle-photo-placeholder .app-icon').exists()).toBe(true)
    expect(wrapper.find('.vehicle-color').exists()).toBe(false)
    // Nothing reported yet: say so rather than draw an empty percentage gauge.
    expect(wrapper.get('.charge-reading').text()).toBe('No telemetry reported yet')
    expect(wrapper.find('.charge-reading i').exists()).toBe(false)
    // Nothing reported means nothing is listed: a dash beside "current speed" only
    // dressed up the absence of data as a reading.
    // The contact time still shows; what must not appear is a reading it never sent.
    expect(wrapper.findAll('.vehicle-facts span')).toHaveLength(0)
    expect(wrapper.get('.vehicle-facts').text()).not.toContain('km/h')
    const image = new File(['image-content'], 'eclair.webp', { type: 'image/webp' })
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', { configurable: true, value: [image] })
    await input.trigger('change')
    await flushPromises()

    const upload = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(upload?.[0]).toBe('/api/v1/vehicles/vehicle-1/photo')
    expect(upload?.[1]?.body).toBe(image)
    expect(new Headers(upload?.[1]?.headers).get('Content-Type')).toBe('image/webp')
    expect(wrapper.find('img').attributes('src')).toContain('/api/v1/vehicles/vehicle-1/photo?v=abc123')

    await wrapper.get('button[aria-label="Remove photo"]').trigger('click')
    await flushPromises()
    expect(fetchMock.mock.calls.some((call) => call[1]?.method === 'DELETE')).toBe(true)
    expect(wrapper.find('.vehicle-photo-placeholder').exists()).toBe(true)
  })

  it('deletes a vehicle through an explicit destructive confirmation modal', async () => {
    let deleted = false
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicles/vehicle-1') && options?.method === 'DELETE') {
        deleted = true
        return Promise.resolve(new Response(null, { status: 204 }))
      }
      return Promise.resolve(jsonResponse(deleted ? [] : [vehicle]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()

    await wrapper.get('.vehicle-card footer .danger').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Delete vehicle')
    expect(wrapper.get('.delete-warning').text()).toContain('telemetry history')
    await wrapper.get('.delete-actions .danger').trigger('click')
    await flushPromises()

    expect(fetchMock.mock.calls.some((call) => call[0].endsWith('/vehicles/vehicle-1') && call[1]?.method === 'DELETE')).toBe(true)
    expect(wrapper.find('.vehicle-card').exists()).toBe(false)
    expect(wrapper.text()).toContain('Éclair was deleted.')
  })

  it('persists the registry-backed custom dashboard layout', async () => {
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{preset:'test-fixture',widgets:[{id:'soc',type:'metric-card',vehicle_id:vehicle.id,metric:'battery.soc',title:'SOC',unit:'%',x:0,y:0,w:3,h:2}]},created_at:'',updated_at:'' }
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/dashboards') && !options?.method) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith(`/vehicles/${vehicle.id}`)) return Promise.resolve(jsonResponse(vehicle))
      if (url.endsWith('/dashboards/dash-1') && options?.method === 'PUT') return Promise.resolve(jsonResponse(dashboard))
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()
    await wrapper.get('.dashboard-menu-button').trigger('click')
    await wrapper.findAll('[role="menuitem"]').find((button) => button.text().includes('Edit dashboard'))!.trigger('click')
    await wrapper.get('.dashboard-editor-bar .button:not(.secondary)').trigger('click')
    await flushPromises()
    const saveCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(saveCall?.[0]).toBe('/api/v1/dashboards/dash-1')
    expect(JSON.parse(saveCall?.[1]?.body as string).layout.widgets[0].type).toBe('metric-card')
  })

  it('suggests dashboard metrics that are actually reported by the selected vehicle', async () => {
    const thermal = { ...vehicle, battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{preset:'test-fixture',widgets:[]},created_at:'',updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([thermal]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()
    await wrapper.get('.dashboard-menu-button').trigger('click')
    await wrapper.findAll('[role="menuitem"]').find((button) => button.text().includes('Edit dashboard'))!.trigger('click')
    await wrapper.findAll('.dashboard-editor-bar .button').find((button) => button.text().includes('Add widget'))!.trigger('click')
    wrapper.findAllComponents(AppSelect)[0]!.vm.$emit('update:modelValue', 'multi-series')
    await flushPromises()
    expect((wrapper.get('.app-modal input[placeholder]').element as HTMLInputElement).value).toBe('fuel.level, engine.rpm')
  })

  it('adapts the energy gauge to fuel for a combustion vehicle', async () => {
    const thermal = { ...vehicle, battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{preset:'test-fixture',widgets:[{id:'energy',type:'battery-gauge',vehicle_id:thermal.id,x:0,y:0,w:3,h:3}]},created_at:'',updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith(`/vehicles/${thermal.id}`)) return Promise.resolve(jsonResponse(thermal))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([thermal]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    expect(wrapper.get('.gauge').text()).toBe('52%')
    expect(wrapper.get('.widget-card').text()).toContain('Fuel level')
    expect(wrapper.get('.widget-card').text()).not.toContain('Battery level')
  })

  it('creates the single premade overview on first use', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/dashboards') && options?.method === 'POST') {
        const body = JSON.parse(options.body as string)
        return Promise.resolve(jsonResponse({ id:'overview', ...body, created_at:'', updated_at:'' }, 201))
      }
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith('/hooks')) return Promise.resolve(jsonResponse([]))
      return Promise.resolve(jsonResponse(vehicle))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div data-chart />'},VehicleMap:{template:'<div data-map />'}}} })
    await flushPromises()

    const createCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    const body = JSON.parse(createCall?.[1]?.body as string)
    expect(body.name).toBe('Overview')
    expect(body.is_default).toBe(true)
    expect(body.layout.preset).toBe('overview-v4')
    expect(body.layout.widgets.map((row: {type:string}) => row.type)).toEqual([
      'vehicle-selector', 'position-map', 'battery-gauge', 'charging',
      'telemetry-list', 'time-series', 'device-health', 'online-status', 'vehicle-media',
    ])
    // Energy, charging and the photo opt out for vehicles that cannot report them.
    const conditional = body.layout.widgets.filter((row: {settings?:{hide_when_empty?:boolean}}) => row.settings?.hide_when_empty)
    expect(conditional.map((row: {type:string}) => row.type)).toEqual(['battery-gauge', 'charging', 'vehicle-media'])
    expect(wrapper.get('.dashboard-tabs').text()).toContain('Overview')
  })

  it('updates dynamic widgets from the vehicle selector and persists card deletion', async () => {
    const secondVehicle = { ...vehicle, id:'vehicle-2', name:'Nimbus', state:{...vehicle.state,metrics:{'fuel.level':25}} }
    const dashboard = { id:'overview', name:'Overview', is_default:true, layout:{preset:'overview-v4',widgets:[
      {id:'selector',type:'vehicle-selector',x:0,y:0,w:12,h:1},
      {id:'fuel',type:'metric-card',metric:'fuel.level',x:0,y:1,w:3,h:2},
    ]}, created_at:'', updated_at:'' }
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/dashboards') && !options?.method) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle,secondVehicle]))
      if (url.endsWith('/dashboards/overview') && options?.method === 'PUT') {
        return Promise.resolve(jsonResponse({ ...dashboard, ...JSON.parse(options.body as string) }))
      }
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div data-chart />'},VehicleMap:{template:'<div data-map />'}}} })
    await flushPromises()
    expect(wrapper.get('[data-widget-type="metric-card"] .dashboard-widget-empty').text()).toContain('No data yet')
    wrapper.getComponent(AppSelect).vm.$emit('update:modelValue', secondVehicle.id)
    await flushPromises()
    expect(wrapper.get('[data-widget-type="metric-card"] .metric-value').text()).toBe('25%')

    await wrapper.get('.dashboard-menu-button').trigger('click')
    await wrapper.findAll('[role="menuitem"]').find((button) => button.text().includes('Edit dashboard'))!.trigger('click')
    await wrapper.get('[data-widget-type="metric-card"] .widget-remove').trigger('click')
    await wrapper.findAll('.dashboard-editor-bar .button').find((button) => button.text() === 'Save')!.trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-widget-type="metric-card"]').exists()).toBe(false)
    const saveCall = fetchMock.mock.calls.find((call) => call[0].endsWith('/dashboards/overview') && call[1]?.method === 'PUT')
    expect(JSON.parse(saveCall?.[1]?.body as string).layout.widgets.map((row: {type:string}) => row.type)).toEqual(['vehicle-selector'])
  })

  it('shows one clean empty state instead of mounting broken data visualizations', async () => {
    const emptyVehicle = { ...vehicle, state:null }
    const dashboard = { id:'overview', name:'Overview', is_default:true, layout:{preset:'overview-v3',widgets:[
      {id:'map',type:'position-map',x:0,y:0,w:6,h:4},
      {id:'energy',type:'battery-gauge',x:6,y:0,w:3,h:2},
      {id:'telemetry',type:'telemetry-list',x:9,y:0,w:3,h:3},
      {id:'chart',type:'time-series',x:0,y:4,w:6,h:3,metric:'battery.soc'},
      {id:'health',type:'device-health',x:6,y:4,w:3,h:2},
      {id:'online',type:'online-status',x:9,y:4,w:3,h:2},
    ]}, created_at:'', updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([emptyVehicle]))
      if (url.includes('/history?')) return Promise.resolve(jsonResponse({
        vehicle_id:emptyVehicle.id,start:'',end:'',available_metrics:[],original_count:0,points:[],
      }))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div data-chart />'},VehicleMap:{template:'<div data-map />'}}} })
    await flushPromises()

    expect(wrapper.findAll('.dashboard-widget-empty')).toHaveLength(6)
    expect(wrapper.find('[data-map]').exists()).toBe(false)
    expect(wrapper.find('[data-chart]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('—')
  })

  it('submits a user-authored declarative vehicle profile', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResponse({ id:'profile-1' }, 201))
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehicleProfileEditor, { props:{open:true,profile:null}, global:{plugins:[i18n],stubs:{Teleport:true}} })
    await wrapper.get('.profile-editor input[required]').setValue('My EV')
    await wrapper.get('.signal-section .button').trigger('click')
    await wrapper.get('input[placeholder="battery.soc"]').setValue('battery.soc')
    await wrapper.get('input[placeholder="0x374"]').setValue('0x374')
    await wrapper.get('.signal-editor').trigger('submit')
    await flushPromises()
    await wrapper.get('.profile-editor').trigger('submit')
    await flushPromises()

    const body = JSON.parse(fetchMock.mock.calls[0]![1].body as string)
    expect(fetchMock.mock.calls[0]![0]).toBe('/api/v1/vehicle-profiles')
    expect(body.name).toBe('My EV')
    expect(body.signals[0].source).toEqual({ type:'can', can_id:0x374 })
    expect(body.signals[0]).not.toHaveProperty('status')
  })

  it('opens profile creation from a dedicated profiles page', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [] : []))))
    const wrapper = mount(ProfilesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    expect(wrapper.get('h1').text()).toBe('Telemetry profiles')
    expect(wrapper.find('.profile-editor').exists()).toBe(false)
    await wrapper.get('.page-header .button').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Create profile')
    expect(wrapper.get('.profile-editor').isVisible()).toBe(true)
  })

  it('hides opted-in widgets for a vehicle that cannot report them, and keeps the rest', async () => {
    // A standard OBD-II diesel: no traction battery, and no fuel-level PID support.
    const diesel = { ...vehicle, id:'vehicle-2', name:'Golf', photo_url:null, state:{ ...vehicle.state, metrics:{ 'engine.rpm':1800 } } }
    const dashboard = { id:'overview', name:'Overview', is_default:true, layout:{ preset:'overview-v4', widgets:[
      { id:'selector', type:'vehicle-selector', x:0, y:0, w:12, h:1 },
      { id:'energy', type:'battery-gauge', x:0, y:1, w:4, h:2, settings:{ hide_when_empty:true } },
      { id:'charge', type:'charging', x:4, y:1, w:4, h:2, settings:{ hide_when_empty:true } },
      { id:'live', type:'telemetry-list', x:8, y:1, w:4, h:3 },
    ] }, created_at:'', updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle, diesel]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div />'},VehicleMap:{template:'<div />'}}} })
    await flushPromises()

    // The EV reports both, so both are on the canvas.
    expect(wrapper.find('[data-widget-type="battery-gauge"]').exists()).toBe(true)
    expect(wrapper.find('[data-widget-type="charging"]').exists()).toBe(true)

    wrapper.getComponent(AppSelect).vm.$emit('update:modelValue', diesel.id)
    await flushPromises()
    expect(wrapper.find('[data-widget-type="battery-gauge"]').exists()).toBe(false)
    expect(wrapper.find('[data-widget-type="charging"]').exists()).toBe(false)
    // A widget that did not opt in stays, because it still has something to show.
    expect(wrapper.find('[data-widget-type="telemetry-list"]').exists()).toBe(true)

    // Editing must reveal them again or they could never be removed.
    await wrapper.get('.dashboard-menu-button').trigger('click')
    await wrapper.findAll('[role="menuitem"]').find((button) => button.text().includes('Edit dashboard'))!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-widget-type="battery-gauge"]').exists()).toBe(true)
  })
})
