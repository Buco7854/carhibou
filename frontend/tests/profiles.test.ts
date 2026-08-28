import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import ProfilesView from '../src/views/ProfilesView.vue'
import { adminUser, agentImplementations, agentRow, canProfile, connectorKinds, connectorRow, field, lastBody, mappingProfile, mockApi, vehicle } from './helpers'

const stubs = { Teleport: true }

function api(options: { agents?: unknown[]; profiles?: unknown[]; connectors?: unknown[] } = {}) {
  return mockApi({
    '/vehicle-profiles': options.profiles ?? [canProfile, mappingProfile],
    '/agent-implementations': agentImplementations,
    '/connector-kinds': connectorKinds,
    '/connectors': options.connectors ?? [],
    '/agents': options.agents ?? [],
    '/enrollments': { token: 'tok', expires_at: '2026-01-01T00:30:00Z', setup_steps: [] },
    default: [vehicle],
  })
}

/** AppSelect builds its listbox from slot vnodes, so options exist only once open. */
async function optionsOf(select: ReturnType<ReturnType<typeof mount>['findComponent']>): Promise<string[]> {
  await select.get('.app-select-trigger').trigger('click')
  const labels = select.findAll('[role="option"]').map((option) => option.text())
  await select.get('.app-select-trigger').trigger('click')
  return labels
}

describe('source profiles', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
  })

  it('chooses a decoding profile at enrollment and sizes the estimate from it', async () => {
    // Enough signals that the monthly estimate visibly moves when the profile is chosen.
    const rich = { ...canProfile, definition: { ...canProfile.definition, signals: Array.from({ length: 40 }, (_item, index) => ({ ...canProfile.definition.signals[0]!, name: `metric.${index}` })) } }
    const fetchMock = api({ profiles: [rich, mappingProfile] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    await wrapper.get('.header-actions .button:not(.secondary)').trigger('click')

    // Only CAN profiles decode frames, so the mapping profile is not on offer.
    const picker = field(wrapper, '.enrollment-fields', 'Decoding profile').findComponent(AppSelect)
    const options = await optionsOf(picker)
    expect(options).toContain('C-Zero')
    expect(options).not.toContain('TeslaMate (MQTT)')

    const before = wrapper.get('.cadence-estimate').text()
    picker.vm.$emit('update:modelValue', rich.id)
    await flushPromises()
    expect(wrapper.get('.cadence-estimate').text()).not.toBe(before)

    await wrapper.get('.enrollment-panel').trigger('submit')
    await flushPromises()
    expect(lastBody(fetchMock, 'POST').vehicle_profile).toBe(rich.id)
  })

  it('changes an agent profile from its settings', async () => {
    const fetchMock = api({ agents: [agentRow({ vehicle_profile: canProfile.id })] })
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    await wrapper.get('.source-details-toggle').trigger('click')
    expect(wrapper.get('.source-facts').text()).toContain('C-Zero')
    await wrapper.get('.source-actions .button').trigger('click')
    const picker = field(wrapper, '.stack-form', 'Decoding profile').findComponent(AppSelect)
    picker.vm.$emit('update:modelValue', null)
    await flushPromises()
    await wrapper.get('.stack-form').trigger('submit')
    await flushPromises()
    expect(lastBody(fetchMock, 'PUT').vehicle_profile).toBeNull()
  })

  it('selects a mapping profile on the connector form', async () => {
    const fetchMock = api()
    const wrapper = mount(DataSourcesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')

    const picker = field(wrapper, '.connector-form', 'Mapping profile').findComponent(AppSelect)
    expect(await optionsOf(picker)).toEqual(['TeslaMate (MQTT)'])

    await field(wrapper, '.connector-form', 'Host').get('input').setValue('mqtt.local')
    await wrapper.get('.connector-form').trigger('submit')
    await flushPromises()
    expect(lastBody(fetchMock, 'POST').mapping_profile).toBe(mappingProfile.id)
  })

  it('lists both profile types with their own counts', async () => {
    const custom = { ...mappingProfile, id: 'mine', name: 'Mine', built_in: false, editable: true }
    api({ profiles: [canProfile, mappingProfile, custom], agents: [agentRow({ vehicle_profile: canProfile.id })], connectors: [connectorRow()] })
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    const badges = wrapper.findAll('.type-badge').map((badge) => badge.text())
    expect(badges).toContain('CAN')
    expect(badges).toContain('Mapping')
    const canCard = wrapper.findAll('.profile-card').find((card) => card.text().includes('C-Zero'))!
    expect(canCard.text()).toContain('1 signals')
    expect(canCard.text()).toContain('Assigned to 1')
    const mappingCard = wrapper.findAll('.profile-card').find((card) => card.text().includes('TeslaMate'))!
    expect(mappingCard.text()).toContain('2 rules')
    expect(mappingCard.text()).toContain('Assigned to 1')
  })

  it('creates a mapping profile from a rule list', async () => {
    const fetchMock = api({ profiles: [] })
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Create mapping profile')

    await field(wrapper, '.profile-editor', 'Profile name').get('input').setValue('Broker map')
    await field(wrapper, '.profile-editor', 'Passthrough prefix').get('input').setValue('teslamate')
    await field(wrapper, '.profile-editor', 'Ignored keys').get('input').setValue('latitude, longitude')

    await wrapper.get('.signal-section .button').trigger('click')
    await field(wrapper, '.signal-editor', 'Incoming key').get('input').setValue('charging_state')
    await field(wrapper, '.signal-editor', 'Target').get('input').setValue('charging.active')
    field(wrapper, '.signal-editor', 'Transform').findComponent(AppSelect).vm.$emit('update:modelValue', 'enum')
    await flushPromises()
    await wrapper.get('.enum-field textarea').setValue('Charging = true\n* = false')
    await wrapper.get('.signal-editor').trigger('submit')
    await flushPromises()

    expect(wrapper.get('.signal-row').text()).toContain('charging_state')
    await wrapper.get('.profile-editor').trigger('submit')
    await flushPromises()

    expect(lastBody(fetchMock, 'POST')).toEqual({
      name: 'Broker map',
      description: '',
      type: 'mapping',
      passthrough_prefix: 'teslamate',
      ignore: ['latitude', 'longitude'],
      rules: [{ match: 'charging_state', target: 'charging.active', transform: { enum: { Charging: true, '*': false } } }],
    })
  })

  it('refuses a rule with an invalid target or a duplicate key', async () => {
    api({ profiles: [] })
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    await wrapper.get('.header-actions .button.secondary').trigger('click')
    await wrapper.get('.signal-section .button').trigger('click')

    await field(wrapper, '.signal-editor', 'Incoming key').get('input').setValue('elevation')
    await field(wrapper, '.signal-editor', 'Target').get('input').setValue('position.nowhere')
    await wrapper.get('.signal-editor').trigger('submit')
    expect(wrapper.get('.signal-editor .error').text()).toContain('valid target')

    await field(wrapper, '.signal-editor', 'Target').get('input').setValue('position.altitude')
    await wrapper.get('.signal-editor').trigger('submit')
    await flushPromises()
    expect(wrapper.findAll('.signal-row')).toHaveLength(1)

    await wrapper.get('.signal-section .button').trigger('click')
    await field(wrapper, '.signal-editor', 'Incoming key').get('input').setValue('elevation')
    await field(wrapper, '.signal-editor', 'Target').get('input').setValue('position.speed')
    await wrapper.get('.signal-editor').trigger('submit')
    expect(wrapper.get('.signal-editor .error').text()).toContain('already has a rule')
  })

  it('edits a custom mapping profile in place and clones a bundled one', async () => {
    const custom = { ...mappingProfile, id: 'mine', name: 'Mine', built_in: false, editable: true }
    const fetchMock = api({ profiles: [custom, mappingProfile] })
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    const customCard = wrapper.findAll('.profile-card').find((card) => card.text().includes('Mine'))!
    await customCard.get('.profile-actions .icon-button').trigger('click')
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Edit mapping profile')
    expect(wrapper.findAll('.signal-row')).toHaveLength(2)
    await wrapper.get('.profile-editor').trigger('submit')
    await flushPromises()
    const edited = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(String(edited?.[0])).toContain('/vehicle-profiles/mine')

    const bundledCard = wrapper.findAll('.profile-card').find((card) => card.text().includes('TeslaMate'))!
    await bundledCard.get('.profile-actions .icon-button').trigger('click')
    // A clone starts as a new profile, prefilled and renamed.
    expect(wrapper.get('[role="dialog"]').attributes('aria-label')).toBe('Create mapping profile')
    expect((field(wrapper, '.profile-editor', 'Profile name').get('input').element as HTMLInputElement).value).toBe('TeslaMate (MQTT) copy')
    expect(wrapper.findAll('.signal-row')).toHaveLength(2)
    await wrapper.get('.profile-editor').trigger('submit')
    await flushPromises()
    const cloned = fetchMock.mock.calls.filter((call) => call[1]?.method === 'POST').at(-1)
    expect(String(cloned?.[0])).toBe('/api/v1/vehicle-profiles')
    expect(lastBody(fetchMock, 'POST').rules).toHaveLength(2)
  })
})
