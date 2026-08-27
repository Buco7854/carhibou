import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import { metricDefinition, metricLabel } from '../src/vehicleDisplay'
import { adminUser, agentImplementations, canProfile, connectorKinds, connectorRow, agentIdentity, jsonResponse, mappingProfile, memberUser, vehicle } from './helpers'

const enrolledAgent = {
  id: 'agent-1', vehicle_id: vehicle.id, name: 'Pi', credential_version: 1, ...agentIdentity,
  hostname: 'pi', hardware: {}, sampling_seconds: 5, upload_seconds: 5, parked_sampling_seconds: 300,
  parked_upload_seconds: 300, online: true, last_seen_at: null, last_config_sync_at: null,
  config_version: 1, revoked_at: null, created_at: '2026-01-01T00:00:00Z',
}

function mockApi(options: { agents?: unknown[]; connectors?: unknown[]; vehicles?: unknown[] } = {}) {
  const fetchMock = vi.fn().mockImplementation((url: string) => {
    if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
    if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse(options.connectors ?? []))
    if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
    if (url.endsWith('/vehicle-profiles')) return Promise.resolve(jsonResponse([canProfile, mappingProfile]))
    if (url.endsWith('/agents')) return Promise.resolve(jsonResponse(options.agents ?? []))
    return Promise.resolve(jsonResponse(options.vehicles ?? [vehicle]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

/** The form labels its inputs, so a test can name a field the way an operator sees it. */
function field(wrapper: ReturnType<typeof mount>, label: string) {
  const target = wrapper.findAll('.connector-form .field').find((item) => item.find('span').exists() && item.get('span').text() === label)
  if (!target) throw new Error(`no data source field labelled "${label}"`)
  return target.get('input')
}

function body(fetchMock: ReturnType<typeof vi.fn>, method: string, fragment: string): Record<string, unknown> {
  const call = fetchMock.mock.calls.filter((entry) => entry[1]?.method === method && String(entry[0]).includes(fragment)).at(-1)
  if (!call) throw new Error(`no ${method} to ${fragment}`)
  return JSON.parse(call[1]?.body as string)
}

describe('external data connectors', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('lists a data source for every runtime status', async () => {
    const rows = [
      connectorRow({ id: 'c-connected', name: 'Connected source', status: 'connected' }),
      connectorRow({ id: 'c-connecting', name: 'Connecting source', status: 'connecting', last_message_at: null }),
      connectorRow({ id: 'c-error', name: 'Broken source', status: 'error', last_error: 'broker refused the credentials' }),
      connectorRow({ id: 'c-disabled', name: 'Paused source', status: 'disabled', enabled: false, last_message_at: null }),
    ]
    mockApi({ connectors: rows })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    const chips = wrapper.findAll('.connector-row .connector-status')
    expect(chips.map((chip) => chip.text())).toEqual(['Connected', 'Connecting', 'Error', 'Disabled'])
    expect(chips[0]!.classes()).toContain('connected')
    expect(chips[2]!.classes()).toContain('error')
    expect(chips[3]!.classes()).toContain('disabled')

    const connected = wrapper.findAll('.connector-row')[0]!
    expect(connected.text()).toContain('TeslaMate (MQTT)')
    expect(connected.text()).toContain('mqtt.local:1883')
    expect(connected.text()).toContain(new Date('2026-01-01T00:05:00Z').toLocaleString())
    // A connector that has never received anything says so rather than showing a blank.
    expect(wrapper.findAll('.connector-row')[1]!.text()).toContain('Never')
    // The last error is the only thing that explains an error chip, so it is on the row.
    expect(wrapper.findAll('.connector-row')[2]!.get('.connector-error').text()).toBe('broker refused the credentials')
    expect(connected.find('.connector-error').exists()).toBe(false)
    // Disabling is how a data source is stood down, so the action reads as the inverse.
    expect(wrapper.findAll('.connector-row')[3]!.text()).toContain('Enable')
    expect(connected.text()).toContain('Disable')
  })

  it('creates a data source with exactly the fields the catalog contract defines', async () => {
    const fetchMock = mockApi()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.get('.header-actions .button.secondary').trigger('click')
    expect(wrapper.get('.connector-form').text()).toContain('TeslaMate (MQTT)')
    // The hints name the broker to point at and where the data turns up.
    expect(wrapper.get('.connector-form').text()).toContain('Mosquitto')
    expect(wrapper.get('.connector-form').text()).toContain('teslamate.')

    await field(wrapper, 'Name').setValue('Garage broker')
    await field(wrapper, 'Host').setValue('mqtt.local')
    await field(wrapper, 'Port').setValue('8883')
    // The certificate escape hatch only exists once TLS is on.
    expect(wrapper.findAll('.connector-form input[type="checkbox"]')).toHaveLength(1)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(true)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[1]!.setValue(true)
    await field(wrapper, 'Username').setValue('carhibou')
    await field(wrapper, 'Password').setValue('hunter2')
    await field(wrapper, 'Namespace (optional)').setValue('garage')
    await field(wrapper, 'Car id').setValue('2')
    await field(wrapper, 'Sample interval (seconds)').setValue('30')
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()

    const created = fetchMock.mock.calls.find((call) => call[1]?.method === 'POST')
    expect(created?.[0]).toBe(`/api/v1/vehicles/${vehicle.id}/connectors`)
    // Exact: the server forbids unknown keys, so enabled and vehicle_id must not travel.
    expect(JSON.parse(created?.[1]?.body as string)).toEqual({
      kind: 'teslamate.mqtt',
      name: 'Garage broker',
      mapping_profile: 'teslamate-mqtt-v1',
      config: {
        host: 'mqtt.local', port: 8883, tls: true, tls_accept_invalid_certs: true,
        username: 'carhibou', namespace: 'garage', car_id: 2, sample_seconds: 30,
      },
      password: 'hunter2',
    })
  })

  it('carries the sample interval bounds the runtime enforces', async () => {
    mockApi()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')

    const interval = field(wrapper, 'Sample interval (seconds)')
    expect(interval.attributes('min')).toBe('1')
    expect(interval.attributes('max')).toBe('3600')
    expect((interval.element as HTMLInputElement).value).toBe('10')
    expect((field(wrapper, 'Port').element as HTMLInputElement).value).toBe('1883')
    expect((field(wrapper, 'Car id').element as HTMLInputElement).value).toBe('1')
  })

  it('treats the password as write-only when editing an existing data source', async () => {
    const fetchMock = mockApi({ connectors: [connectorRow()] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.get('.connector-row .source-actions .button').trigger('click')
    const password = field(wrapper, 'Password')
    // Nothing stored is echoed back: the field is empty and the marker is a hint.
    expect((password.element as HTMLInputElement).value).toBe('')
    expect(password.attributes('placeholder')).toBe('••••••••')
    expect(wrapper.get('.connector-form').text()).toContain('never shown')
    expect((field(wrapper, 'Host').element as HTMLInputElement).value).toBe('mqtt.local')

    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()
    const kept = body(fetchMock, 'PUT', '/connectors/connector-1')
    expect(kept).not.toHaveProperty('password')
    expect(kept).toEqual({ name: 'Garage broker', enabled: true, mapping_profile: 'teslamate-mqtt-v1', config: connectorRow().config })

    await wrapper.get('.connector-row .source-actions .button').trigger('click')
    await field(wrapper, 'Password').setValue('replacement')
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()
    expect(body(fetchMock, 'PUT', '/connectors/connector-1').password).toBe('replacement')
  })

  it('never sends the certificate escape hatch without the TLS it depends on', async () => {
    const fetchMock = mockApi()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')
    await field(wrapper, 'Host').setValue('mqtt.local')

    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(true)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[1]!.setValue(true)
    // Turning TLS back off retracts the sub-toggle, which the server rejects alone.
    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(false)
    expect(wrapper.findAll('.connector-form input[type="checkbox"]')).toHaveLength(1)
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()

    const config = body(fetchMock, 'POST', '/connectors').config as Record<string, unknown>
    expect(config.tls).toBe(false)
    expect(config.tls_accept_invalid_certs).toBe(false)
  })

  it('disables a data source without disturbing its configuration', async () => {
    const fetchMock = mockApi({ connectors: [connectorRow()] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.findAll('.connector-row .source-actions .button')[1]!.trigger('click')
    await flushPromises()
    expect(body(fetchMock, 'PUT', '/connectors/connector-1')).toEqual({
      name: 'Garage broker', enabled: false, mapping_profile: 'teslamate-mqtt-v1', config: connectorRow().config,
    })
  })

  it('keeps connector-backed shadow agents out of the agents list', async () => {
    const shadow = {
      ...enrolledAgent, id: 'agent-shadow', name: 'Garage broker shadow',
      implementation_id: 'connector.teslamate.mqtt',
    }
    mockApi({ agents: [enrolledAgent, shadow], connectors: [connectorRow()] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    const agents = wrapper.findAll('.source-row:not(.connector-row)')
    expect(agents).toHaveLength(1)
    expect(agents[0]!.text()).toContain('Pi')
    expect(wrapper.find('.source-list').text()).not.toContain('Garage broker shadow')
    expect(wrapper.text()).not.toContain('connector.teslamate.mqtt')
    // The roster summary counts agents, so the shadow row must not inflate it.
    expect(wrapper.get('.group-note').text()).toContain('1 of 1 reporting')
  })

  it('hides data source management from a viewer', async () => {
    auth.user = { ...memberUser }
    const viewed = { ...vehicle, access: 'view' as const }
    mockApi({ connectors: [connectorRow()], vehicles: [viewed] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    // The row itself is readable; only the operator actions are absent.
    expect(wrapper.get('.connector-row').text()).toContain('Garage broker')
    expect(wrapper.find('.connector-row .source-actions').exists()).toBe(false)
    expect(wrapper.find('.header-actions .button.secondary').exists()).toBe(false)
  })

  it('renders teslamate-prefixed keys through the existing metric fallback', async () => {
    // Passthrough keys have no definition, so dashboards and history fall back to
    // the key itself rather than dropping the reading.
    const definition = metricDefinition('teslamate.inside_temp')
    expect(definition.labelKey).toBe('')
    expect(metricLabel(definition, (key) => key)).toBe('teslamate.inside_temp')
    // A canonical target keeps its translated label, so a mapping never duplicates one.
    expect(metricDefinition('battery.soc').labelKey).toBe('metrics.batterySoc')
  })
})
