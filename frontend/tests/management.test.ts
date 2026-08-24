import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import DashboardsView from '../src/views/DashboardsView.vue'
import DevicesView from '../src/views/DevicesView.vue'
import VehiclesView from '../src/views/VehiclesView.vue'
import { jsonResponse, vehicle } from './helpers'

vi.mock('gridstack', () => ({
  GridStack: {
    init: vi.fn(() => ({
      on: vi.fn(), makeWidget: vi.fn(), removeWidget: vi.fn(), destroy: vi.fn(),
    })),
  },
}))

describe('vehicle and dashboard management', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('creates a vehicle through the real form/API contract', async () => {
    let created = false
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (options?.method === 'POST') { created = true; return Promise.resolve(jsonResponse(vehicle, 201)) }
      return Promise.resolve(jsonResponse(created ? [vehicle] : []))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('header button').trigger('click')
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

  it('filters the vehicle catalog by search and live status locally', async () => {
    const parked = { ...vehicle, id:'vehicle-2', name:'Nimbus', propulsion_type:'petrol', battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{ ...vehicle.state, online:false, metrics:{'fuel.level':48,'engine.rpm':900} } }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([vehicle, parked])))
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{RouterLink:{template:'<a><slot /></a>'}}} })
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
    expect(wrapper.get('.vehicle-card').text()).toContain('Petrol')
    expect(wrapper.get('.vehicle-card').text()).not.toContain('Battery level')
    i18n.global.locale.value = 'fr'
    await flushPromises()
    expect(wrapper.get('.vehicle-card').text()).toContain('Niveau de carburant')
    expect(wrapper.get('.vehicle-card').text()).toContain('Essence')
  })

  it('removes EV-only creation fields when a combustion propulsion is selected', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, options?: RequestInit) => {
      if (options?.method === 'POST') return Promise.resolve(jsonResponse(vehicle, 201))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('header button').trigger('click')
    await wrapper.get('select').setValue('petrol')

    expect(wrapper.find('input[type="number"][step=".1"]').exists()).toBe(false)
    await wrapper.get('input[required]').setValue('Touring')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const createCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    const body = JSON.parse(createCall?.[1]?.body as string)
    expect(body.propulsion_type).toBe('petrol')
    expect(body.battery_nominal_capacity_kwh).toBeNull()
    expect(body.vehicle_profile).toBeNull()
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
      return Promise.resolve(jsonResponse([{ ...vehicleWithoutTelemetry, photo_url: photoUrl }]))
    })
    vi.stubGlobal('fetch', fetchMock)
    vi.stubGlobal('confirm', vi.fn(() => true))
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()

    expect(wrapper.get('.vehicle-photo-placeholder').attributes('aria-label')).toBe('No photo for Éclair')
    expect(wrapper.find('.vehicle-photo-placeholder .app-icon').exists()).toBe(true)
    expect(wrapper.find('.vehicle-color').exists()).toBe(false)
    expect(wrapper.get('.charge-reading strong').text()).toBe('—')
    expect(wrapper.get('.vehicle-readings dd.is-empty').text()).toBe('—')
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

  it('persists the registry-backed custom dashboard layout', async () => {
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{widgets:[{id:'soc',type:'metric-card',vehicle_id:vehicle.id,metric:'battery.soc',title:'SOC',unit:'%',x:0,y:0,w:3,h:2}]},created_at:'',updated_at:'' }
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/dashboards') && !options?.method) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith(`/vehicles/${vehicle.id}`)) return Promise.resolve(jsonResponse(vehicle))
      if (url.endsWith('/dashboards/dash-1') && options?.method === 'PUT') return Promise.resolve(jsonResponse(dashboard))
      return Promise.resolve(jsonResponse({}))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n]} })
    await flushPromises()
    await wrapper.get('header .button:not(.secondary)').trigger('click')
    await flushPromises()
    const saveCall = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(saveCall?.[0]).toBe('/api/v1/dashboards/dash-1')
    expect(JSON.parse(saveCall?.[1]?.body as string).layout.widgets[0].type).toBe('metric-card')
  })

  it('suggests drivetrain metrics that match the selected vehicle', async () => {
    const thermal = { ...vehicle, propulsion_type:'diesel', battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{widgets:[]},created_at:'',updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([thermal]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n]} })
    await flushPromises()
    await wrapper.get('header .button.secondary').trigger('click')
    await wrapper.get('.modal select').setValue('multi-series')
    expect((wrapper.get('.modal input[placeholder]').element as HTMLInputElement).value).toBe('fuel.level, engine.rpm')
    expect(wrapper.get('.modal').text()).toContain('Energy gauge')
  })

  it('adapts the energy gauge to fuel for a combustion vehicle', async () => {
    const thermal = { ...vehicle, propulsion_type:'petrol', battery_nominal_capacity_kwh:null, vehicle_profile:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
    const dashboard = { id:'dash-1',name:'My dashboard',is_default:true,layout:{widgets:[{id:'energy',type:'battery-gauge',vehicle_id:thermal.id,x:0,y:0,w:3,h:3}]},created_at:'',updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith(`/vehicles/${thermal.id}`)) return Promise.resolve(jsonResponse(thermal))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([thermal]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n]} })
    await flushPromises()

    expect(wrapper.get('.gauge').text()).toBe('52%')
    expect(wrapper.get('.widget-card').text()).toContain('Fuel level')
    expect(wrapper.get('.widget-card').text()).not.toContain('Battery level')
  })
})
