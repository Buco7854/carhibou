import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import VehicleProfileEditor from '../src/components/VehicleProfileEditor.vue'
import DashboardsView from '../src/views/DashboardsView.vue'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import ProfilesView from '../src/views/ProfilesView.vue'
import VehiclesView from '../src/views/VehiclesView.vue'
import type { DashboardWidget } from '../src/api/types'
import { needsSpecificData, widgetRegistry } from '../src/widgets/registry'
import { adminUser, agentImplementations, agentRow, connectorKinds, jsonResponse, vehicle } from './helpers'

vi.mock('gridstack', () => ({
  GridStack: {
    init: vi.fn(() => ({
      on: vi.fn(), makeWidget: vi.fn(), removeWidget: vi.fn(), destroy: vi.fn(), column:vi.fn(), enableMove:vi.fn(), enableResize:vi.fn(),
    })),
  },
}))

describe('vehicle and dashboard management', () => {
  // These flows exercise controls the access model reserves for administrators.
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

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

  it('shows stale agent status from the server freshness calculation', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
      if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([{
        ...agentRow({ id:'d1', name:'Pi Zero', hostname:'car', online:false, last_seen_at:'2026-01-01T00:00:00Z' }),
      }]))
      return Promise.resolve(jsonResponse([vehicle]))
    }))
    const wrapper = mount(DataSourcesView, { global:{plugins:[i18n]} })
    await flushPromises()
    expect(wrapper.text()).toContain('Pi Zero')
    expect(wrapper.text()).toContain('Parked / stale')
  })

  it('shows newly created vehicles in the agent enrollment selector', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
      if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith(`/vehicles/${vehicle.id}/enrollments`) && options?.method === 'POST') {
        return Promise.resolve(jsonResponse({ token:'tok-1', expires_at:'2026-01-01T00:30:00Z', setup_steps:[{ kind:'command', text:'', command:'curl -fsSL https://hub.example/install-agent | sudo sh', value:'', url:'' }] }, 201))
      }
      return Promise.resolve(jsonResponse([vehicle]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DataSourcesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')
    // The implementation is picked first, so the vehicle is the second combobox.
    expect(wrapper.findAll('[role="combobox"]')[1]!.text()).toContain('Éclair')
    await wrapper.get('.enrollment-panel').trigger('submit')
    await flushPromises()

    const created = fetchMock.mock.calls.find((call) => call[0].endsWith(`/vehicles/${vehicle.id}/enrollments`) && call[1]?.method === 'POST')
    expect(created).toBeDefined()
    expect(JSON.parse(created?.[1]?.body as string).implementation_id).toBe('carhibou.go')
  })

  it('picks an implementation from the catalog and renders every setup step kind', async () => {
    // One step of each kind, in the order the server sends them.
    const setupSteps = [
      { kind:'command', text:'', command:'curl -fsSL https://hub.example/install-agent | sudo sh', value:'', url:'' },
      { kind:'value', text:'Enrollment token', command:'', value:'tok-secret', url:'' },
      { kind:'link', text:'Protocol documentation', command:'', value:'', url:'https://hub.example/api/docs' },
      { kind:'manual', text:'Flash the image, then power the board with the SIM inserted.', command:'', value:'', url:'' },
    ]
    const fetchMock = vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
      if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([]))
      if (url.includes('/enrollments') && options?.method === 'POST') {
        return Promise.resolve(jsonResponse({ token:'tok-secret', expires_at:'2026-01-01T00:30:00Z', setup_steps:setupSteps }, 201))
      }
      return Promise.resolve(jsonResponse([vehicle]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DataSourcesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()
    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')

    // The bundled agent is preselected and described before a token is spent.
    const card = wrapper.get('.implementation-card')
    expect(card.text()).toContain('Carhibou Go agent')
    expect(card.text()).toContain('Bundled')
    expect(card.text()).toContain('Raspberry Pi')
    expect(card.text()).toContain('One command')
    expect(card.get('.implementation-docs').attributes('href')).toBe('https://carhibou.example/agent')

    // Choosing the built-in custom entry explains what it is for and links to
    // the protocol rather than to an agent's own documentation.
    wrapper.findAllComponents(AppSelect)[0]!.vm.$emit('update:modelValue', 'custom')
    await flushPromises()
    expect(wrapper.get('.implementation-card').text()).toContain('Custom agent')
    expect(wrapper.get('.implementation-card').text()).toContain('Guided steps')
    expect(wrapper.get('.implementation-card').text()).toContain('develop yourself')
    expect(wrapper.get('.implementation-docs').attributes('href')).toBe('/api/docs')

    await wrapper.get('.enrollment-panel').trigger('submit')
    await flushPromises()
    const body = JSON.parse(fetchMock.mock.calls.find((call) => String(call[0]).includes('/enrollments'))?.[1]?.body as string)
    expect(body.implementation_id).toBe('custom')
    // The enrollment schema forbids unknown fields, so the cadence preset's own
    // key must never travel with the four intervals it carries.
    expect(Object.keys(body).sort()).toEqual(['implementation_id', 'name', 'parked_sampling_seconds', 'parked_upload_seconds', 'sampling_seconds', 'upload_seconds', 'vehicle_profile'])

    const steps = wrapper.findAll('.setup-steps li')
    expect(steps).toHaveLength(4)
    // command: a copyable monospace block, with an instruction the manifest left out.
    expect(steps[0]!.get('.step-text').text()).toContain('Run this command')
    expect(steps[0]!.get('pre').text()).toContain('install-agent')
    // value: the label the server sent, next to the copyable value.
    expect(steps[1]!.get('.step-text').text()).toBe('Enrollment token')
    expect(steps[1]!.get('code').text()).toBe('tok-secret')
    expect(steps[1]!.get('.copy-button').attributes('aria-label')).toBe('Copy Enrollment token')
    // link: an anchor to a new tab, labelled by its text rather than its URL.
    const link = steps[2]!.get('.step-link a')
    expect(link.text()).toBe('Protocol documentation')
    expect(link.attributes('href')).toBe('https://hub.example/api/docs')
    expect(link.attributes('target')).toBe('_blank')
    // manual: instruction text only, with nothing to copy or follow.
    expect(steps[3]!.text()).toContain('Flash the image')
    expect(steps[3]!.find('.copy-button').exists()).toBe(false)
    expect(steps[3]!.find('a').exists()).toBe(false)

    const writeText = vi.mocked(navigator.clipboard.writeText)
    writeText.mockClear()
    await steps[0]!.get('.copy-button').trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('curl -fsSL https://hub.example/install-agent | sudo sh')
    expect(wrapper.get('.copy-feedback').text()).toBe('Copied')
  })

  it('filters the vehicle catalog by search and live status locally', async () => {
    const parked = { ...vehicle, id:'vehicle-2', name:'Nimbus', battery_nominal_capacity_kwh:null, state:{ ...vehicle.state, online:false, metrics:{'fuel.level':48,'engine.rpm':900} } }
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

  it('creates vehicles from a name alone, with no profile field and no optional specifications', async () => {
    const fetchMock = vi.fn().mockImplementation((_url: string, options?: RequestInit) => {
      if (_url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([{ id:'citroen-c-zero-v1', name:'C-Zero', description:'', type:'can', built_in:true, editable:false, definition:{ id:'citroen-c-zero-v1', name:'C-Zero', version:1, signals:[] }, created_at:null, updated_at:null }]))
      if (options?.method === 'POST') return Promise.resolve(jsonResponse(vehicle, 201))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(VehiclesView, { global:{plugins:[i18n],stubs:{Teleport:true,RouterLink:{template:'<a><slot /></a>'}}} })
    await flushPromises()
    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')
    expect(wrapper.text()).not.toContain('Propulsion')
    expect(wrapper.find('input[type="number"][step=".1"]').exists()).toBe(false)
    // The decoding profile belongs to the agent now, so the vehicle form has none.
    expect(wrapper.text()).not.toContain('Decoding profile')
    expect(wrapper.findAllComponents(AppSelect)).toHaveLength(0)

    await wrapper.get('input[required]').setValue('Touring')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    const created = JSON.parse(fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')?.[1]?.body as string)
    expect(created).toEqual({ name: 'Touring' })
  })

  it('sets an agent cadence at enrollment and edits it afterwards', async () => {
    const agent = agentRow()
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
      if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([agent]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.includes('/enrollments')) return Promise.resolve(jsonResponse({ token:'tok-1', expires_at:'2026-01-01T00:30:00Z', setup_steps:[{ kind:'command', text:'', command:'curl ...', value:'', url:'' }] }, 201))
      return Promise.resolve(jsonResponse(agent))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DataSourcesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')

    // A preset sets both intervals at once, and the estimate says what the
    // choice costs on a metered plan.
    const saver = wrapper.findAll('.cadence-presets .preset').find((button) => button.text().includes('Saver'))!
    await saver.trigger('click')
    expect(wrapper.get('.cadence-estimate').text()).toContain('MB')
    await wrapper.get('.enrollment-panel').trigger('submit')
    await flushPromises()
    const enrolled = JSON.parse(fetchMock.mock.calls.find((call) => String(call[0]).includes('/enrollments'))?.[1]?.body as string)
    // A preset carries both states, so a parked vehicle stops paying the driving rate.
    expect(enrolled.sampling_seconds).toBe(15)
    expect(enrolled.upload_seconds).toBe(15)
    expect(enrolled.parked_sampling_seconds).toBe(600)
    expect(enrolled.parked_upload_seconds).toBe(600)

    // The same two values are editable once the agent exists.
    await wrapper.findAll('.source-actions .button')[0]!.trigger('click')
    await flushPromises()
    // The enrollment modal is still mounted, so scope to the settings one.
    const settings = wrapper.findAll('[role="dialog"]').at(-1)!
    await settings.findAll('.cadence-states input')[0]!.setValue('60')
    await settings.get('form').trigger('submit')
    await flushPromises()
    const saved = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(String(saved?.[0])).toContain('/agents/agent-1')
    expect(JSON.parse(saved?.[1]?.body as string).sampling_seconds).toBe(60)
  })

  it('reports implementation identity and protocol compatibility apart from online state', async () => {
    const agent = agentRow({ implementation_id:'acme.esp32', protocol_version:7, agent_version:'2.4.0', compatibility:'incompatible' as const, last_seen_at:'2026-01-01T00:00:00Z' })
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
      if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
      if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([agent]))
      return Promise.resolve(jsonResponse([vehicle]))
    }))
    const wrapper = mount(DataSourcesView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    await flushPromises()

    const facts = wrapper.get('.source-facts').text()
    expect(facts).toContain('acme.esp32')
    expect(facts).toContain('2.4.0')
    expect(facts).toContain('7')
    expect(wrapper.get('.compat').text()).toBe('Unsupported protocol')
    // An unsupported protocol never demotes the reachability pill, and the
    // roster summary reports the two facts separately.
    expect(wrapper.get('.status').text()).toBe('Online')
    expect(wrapper.get('.status').classes()).toContain('online')
    expect(wrapper.get('.group-note').text()).toContain('1 of 1 reporting')
    expect(wrapper.get('.summary-flag').text()).toContain('1 on an unsupported protocol')
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
    const thermal = { ...vehicle, battery_nominal_capacity_kwh:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
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
    const thermal = { ...vehicle, battery_nominal_capacity_kwh:null, state:{...vehicle.state,metrics:{'fuel.level':52,'engine.rpm':1400}} }
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
    expect(body.layout.preset).toBe('overview-v7')
    // Ordered by the questions an owner asks: what is it doing, how fast, how
    // much is left, where is it, what happened recently, what did it cost.
    expect(body.layout.widgets.map((row: {type:string}) => row.type)).toEqual([
      'vehicle-selector', 'online-status', 'metric-card', 'battery-gauge', 'charging',
      'route-map', 'activity-feed', 'telemetry-list',
      'segment-stats', 'period-stats', 'vehicle-media', 'time-series', 'xy-chart',
    ])
    // The route map replaces the plain position map, which stays available to add.
    expect(widgetRegistry['position-map']).toBeDefined()
    const speed = body.layout.widgets.find((row: {type:string}) => row.type === 'metric-card')
    expect(speed.metric).toBe('vehicle.speed')
    // Both charts lead with a metric every vehicle can produce, or with the pair
    // that names the charge curve.
    expect(body.layout.widgets.find((row: {type:string}) => row.type === 'time-series').metric).toBe('vehicle.speed')
    const curve = body.layout.widgets.find((row: {type:string}) => row.type === 'xy-chart')
    expect([curve.x_metric, curve.y_metric]).toEqual(['battery.soc', 'charging.power'])
    // The principle: a card stays only if it adapts to whatever the vehicle
    // reports. Anything bound to a named metric hides, speed included, because a
    // GPS-only agent never sends vehicle.speed.
    const flagged = (want: boolean) => body.layout.widgets
      .filter((row: {settings?:{hide_when_empty?:boolean}}) => Boolean(row.settings?.hide_when_empty) === want)
      .map((row: {type:string}) => row.type)
    expect(flagged(false)).toEqual([
      'vehicle-selector', 'online-status', 'metric-card', 'route-map', 'activity-feed',
      'telemetry-list', 'segment-stats', 'period-stats', 'time-series',
    ])
    expect(flagged(true)).toEqual(['battery-gauge', 'charging', 'vehicle-media', 'xy-chart'])
    // The two speed cards show because speed is standard, not because the guard
    // is loose: rebinding either to a non-standard metric makes it specific again.
    for (const type of ['metric-card', 'time-series']) {
      const row = body.layout.widgets.find((widget: {type:string}) => widget.type === type)
      expect(row.metric, type).toBe('vehicle.speed')
      expect(needsSpecificData(row), type).toBe(false)
      expect(needsSpecificData({ ...row, metric: 'battery.soc' }), type).toBe(true)
      expect(needsSpecificData({ ...row, metric: '' }), type).toBe(true)
    }
    // Derived, not restated: the layout, the editor default and this assertion
    // all ask needsSpecificData, so the three cannot drift apart.
    for (const row of body.layout.widgets as DashboardWidget[]) {
      expect(Boolean(row.settings?.hide_when_empty), row.type).toBe(needsSpecificData(row))
    }
    // No widget lands on top of another, and none overflows the 12 columns.
    const cells = new Set<string>()
    for (const row of body.layout.widgets as Array<{x:number;y:number;w:number;h:number;type:string}>) {
      expect(row.x + row.w, row.type).toBeLessThanOrEqual(12)
      for (let x = row.x; x < row.x + row.w; x += 1) {
        for (let y = row.y; y < row.y + row.h; y += 1) {
          expect(cells.has(`${x},${y}`), `${row.type} at ${x},${y}`).toBe(false)
          cells.add(`${x},${y}`)
        }
      }
    }
    expect(wrapper.get('.dashboard-tabs').text()).toContain('Overview')
  })

  it('updates dynamic widgets from the vehicle selector and persists card deletion', async () => {
    const secondVehicle = { ...vehicle, id:'vehicle-2', name:'Nimbus', state:{...vehicle.state,metrics:{'fuel.level':25}} }
    const dashboard = { id:'overview', name:'Overview', is_default:true, layout:{preset:'overview-v7',widgets:[
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
      {id:'health',type:'agent-health',x:6,y:4,w:3,h:2},
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
    await wrapper.get('.page-header .button:not(.secondary)').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Create profile')
    expect(wrapper.get('.profile-editor').isVisible()).toBe(true)
  })

  it('inserts the charging curve preset as a preconfigured x-y chart', async () => {
    const dashboard = { id:'d1', name:'Overview', is_default:true, layout:{ preset:'overview-v7', widgets:[] }, created_at:'', updated_at:'' }
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([dashboard]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      return Promise.resolve(jsonResponse([]))
    })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div data-chart />'},VehicleMap:{template:'<div data-map />'}}} })
    await flushPromises()

    await wrapper.get('.dashboard-menu-button').trigger('click')
    await wrapper.findAll('.dashboard-menu button')[0]!.trigger('click')
    await wrapper.get('.dashboard-editor-bar .button.secondary').trigger('click')
    const typeSelect = wrapper.findAllComponents(AppSelect).find((row) => row.props('modelValue') === 'metric-card')!
    typeSelect.vm.$emit('update:modelValue', 'preset:charge-curve')
    await flushPromises()
    await wrapper.get('.widget-modal-form').trigger('submit')
    await flushPromises()

    const added = wrapper.vm.$el.querySelector('[data-widget-type="xy-chart"]')
    expect(added).toBeTruthy()
    const [widget] = (wrapper.vm as unknown as { active: { layout: { widgets: Array<Record<string, unknown>> } } }).active.layout.widgets
    expect(widget).toMatchObject({ type:'xy-chart', x_metric:'battery.soc', y_metric:'charging.power' })
  })

  it('renders a saved charge-curve layout as the x-y chart that replaced it', async () => {
    const legacy = { id:'d1', name:'Overview', is_default:true, layout:{ preset:'overview-v7', widgets:[
      { id:'legacy', type:'charge-curve', x:0, y:0, w:6, h:3 },
    ] }, created_at:'', updated_at:'' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/dashboards')) return Promise.resolve(jsonResponse([legacy]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      return Promise.resolve(jsonResponse([]))
    }))
    const wrapper = mount(DashboardsView, { global:{plugins:[i18n],stubs:{Teleport:true,TimeSeriesChart:{template:'<div data-chart />'},VehicleMap:{template:'<div data-map />'}}} })
    await flushPromises()

    // No crash, no blank card: the old type resolves to the generic widget.
    expect(wrapper.find('[data-widget-type="charge-curve"]').exists()).toBe(false)
    const card = wrapper.get('[data-widget-type="xy-chart"]')
    expect(card.find('.widget-card').exists()).toBe(true)
    expect(card.text()).toContain('Charge curve')
  })

  it('hides opted-in widgets for a vehicle that cannot report them, and keeps the rest', async () => {
    // A standard OBD-II diesel: no traction battery, and no fuel-level PID support.
    const diesel = { ...vehicle, id:'vehicle-2', name:'Golf', photo_url:null, state:{ ...vehicle.state, metrics:{ 'engine.rpm':1800 } } }
    const dashboard = { id:'overview', name:'Overview', is_default:true, layout:{ preset:'overview-v7', widgets:[
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
