import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import { metricDefinition, metricLabel } from '../src/vehicleDisplay'
import { adminUser, agentImplementations, agentRow, canProfile, connectorKinds, connectorRow, field, lastBody, mappingProfile, memberUser, mockApi, vehicle } from './helpers'

function api(options: { agents?: unknown[]; connectors?: unknown[]; vehicles?: unknown[] } = {}) {
  return mockApi({
    '/connector-kinds': connectorKinds,
    '/connectors': options.connectors ?? [],
    '/agent-implementations': agentImplementations,
    '/vehicle-profiles': [canProfile, mappingProfile],
    '/agents': options.agents ?? [],
    default: options.vehicles ?? [vehicle],
  })
}

const connectorField = (wrapper: ReturnType<typeof mount>, label: string) => field(wrapper, '.connector-form', label).get('input')

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
    api({ connectors: rows })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    const chips = wrapper.findAll('.connector-row .status')
    expect(chips.map((chip) => chip.text())).toEqual(['Connected', 'Connecting', 'Error', 'Disabled'])
    // The chip carries the shared tone, not a per-status class of its own.
    expect(chips[0]!.classes()).toContain('online')
    expect(chips[1]!.classes()).toContain('warning')
    expect(chips[2]!.classes()).toContain('failed')
    expect(chips[3]!.classes()).toEqual(['status'])

    const connected = wrapper.findAll('.connector-row')[0]!
    // Kind, broker and interval live behind the row's details disclosure.
    await connected.get('.source-details-toggle').trigger('click')
    expect(connected.text()).toContain('TeslaMate (MQTT)')
    expect(connected.text()).toContain('mqtt.local:1883')
    expect(connected.text()).toContain(new Date('2026-01-01T00:05:00Z').toLocaleString())
    // A connector that has never received anything says so rather than showing a blank.
    expect(wrapper.findAll('.connector-row')[1]!.text()).toContain('Never')
    // The last error is the only thing that explains an error chip, so it is on the row.
    expect(wrapper.findAll('.connector-row')[2]!.get('.connector-error').text()).toBe('broker refused the credentials')
    expect(connected.find('.connector-error').exists()).toBe(false)
    // Disabling is how a data source is stood down, so the action reads as the
    // inverse. It sits in the row menu, which each row opens for itself.
    const paused = wrapper.findAll('.connector-row')[3]!
    await paused.get('.row-menu-button').trigger('click')
    expect(paused.get('.row-menu-list').text()).toContain('Enable')
    await connected.get('.row-menu-button').trigger('click')
    expect(connected.get('.row-menu-list').text()).toContain('Disable')
  })

  it('creates a data source with exactly the fields the catalog contract defines', async () => {
    const fetchMock = api()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.get('.header-actions .button.secondary').trigger('click')
    expect(wrapper.get('.connector-form').text()).toContain('TeslaMate (MQTT)')
    // The hints name the broker to point at and where the data turns up.
    expect(wrapper.get('.connector-form').text()).toContain('Mosquitto')
    expect(wrapper.get('.connector-form').text()).toContain('teslamate.')

    await connectorField(wrapper, 'Name').setValue('Garage broker')
    await connectorField(wrapper, 'Host').setValue('mqtt.local')
    await connectorField(wrapper, 'Port').setValue('8883')
    // The certificate escape hatch only exists once TLS is on.
    expect(wrapper.findAll('.connector-form input[type="checkbox"]')).toHaveLength(1)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(true)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[1]!.setValue(true)
    await connectorField(wrapper, 'Username').setValue('carhibou')
    await connectorField(wrapper, 'Password').setValue('hunter2')
    await connectorField(wrapper, 'Namespace (optional)').setValue('garage')
    await connectorField(wrapper, 'Car id').setValue('2')
    await connectorField(wrapper, 'Read every (seconds)').setValue('30')
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
    api()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')

    const interval = connectorField(wrapper, 'Read every (seconds)')
    expect(interval.attributes('min')).toBe('1')
    expect(interval.attributes('max')).toBe('3600')
    expect((interval.element as HTMLInputElement).value).toBe('10')
    expect((connectorField(wrapper, 'Port').element as HTMLInputElement).value).toBe('1883')
    expect((connectorField(wrapper, 'Car id').element as HTMLInputElement).value).toBe('1')
  })

  it('treats the password as write-only when editing an existing data source', async () => {
    const fetchMock = api({ connectors: [connectorRow()] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.get('.connector-row .source-actions .button').trigger('click')
    const password = connectorField(wrapper, 'Password')
    // Nothing stored is echoed back: the field is empty and the marker is a hint.
    expect((password.element as HTMLInputElement).value).toBe('')
    expect(password.attributes('placeholder')).toBe('••••••••')
    expect(wrapper.get('.connector-form').text()).toContain('never shown')
    expect((connectorField(wrapper, 'Host').element as HTMLInputElement).value).toBe('mqtt.local')

    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()
    const kept = lastBody(fetchMock, 'PUT', '/connectors/connector-1')
    expect(kept).not.toHaveProperty('password')
    expect(kept).toEqual({ name: 'Garage broker', enabled: true, mapping_profile: 'teslamate-mqtt-v1', config: connectorRow().config })

    await wrapper.get('.connector-row .source-actions .button').trigger('click')
    await connectorField(wrapper, 'Password').setValue('replacement')
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()
    expect(lastBody(fetchMock, 'PUT', '/connectors/connector-1').password).toBe('replacement')
  })

  it('never sends the certificate escape hatch without the TLS it depends on', async () => {
    const fetchMock = api()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')
    await connectorField(wrapper, 'Host').setValue('mqtt.local')

    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(true)
    await wrapper.findAll('.connector-form input[type="checkbox"]')[1]!.setValue(true)
    // Turning TLS back off retracts the sub-toggle, which the server rejects alone.
    await wrapper.findAll('.connector-form input[type="checkbox"]')[0]!.setValue(false)
    expect(wrapper.findAll('.connector-form input[type="checkbox"]')).toHaveLength(1)
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()

    const config = lastBody(fetchMock, 'POST', '/connectors').config as Record<string, unknown>
    expect(config.tls).toBe(false)
    expect(config.tls_accept_invalid_certs).toBe(false)
  })

  it('disables a data source without disturbing its configuration', async () => {
    const fetchMock = api({ connectors: [connectorRow()] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true } } })
    await flushPromises()

    await wrapper.get('.connector-row .row-menu-button').trigger('click')
    await wrapper.get('.connector-row .row-menu-list button').trigger('click')
    await flushPromises()
    expect(lastBody(fetchMock, 'PUT', '/connectors/connector-1')).toEqual({
      name: 'Garage broker', enabled: false, mapping_profile: 'teslamate-mqtt-v1', config: connectorRow().config,
    })
  })

  it('keeps connector-backed shadow agents out of the agents list', async () => {
    const shadow = {
      ...agentRow(), id: 'agent-shadow', name: 'Garage broker shadow',
      implementation_id: 'connector.teslamate.mqtt',
    }
    api({ agents: [agentRow(), shadow], connectors: [connectorRow()] })
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
    api({ connectors: [connectorRow()], vehicles: [viewed] })
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
