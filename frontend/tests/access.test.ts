import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import AdminView from '../src/views/AdminView.vue'
import DevicesView from '../src/views/DevicesView.vue'
import ProfilesView from '../src/views/ProfilesView.vue'
import VehiclesView from '../src/views/VehiclesView.vue'
import { adminUser, agentImplementations, deviceIdentity, jsonResponse, memberUser, vehicle } from './helpers'

const stubs = { Teleport: true, RouterLink: { template: '<a><slot /></a>' } }

const profile = {
  id: 'citroen-c-zero-v1', name: 'C-Zero', description: '', built_in: true, editable: false,
  definition: { id: 'citroen-c-zero-v1', name: 'C-Zero', version: 1, signals: [] },
  created_at: null, updated_at: null,
}

describe('permission-gated controls', () => {
  beforeEach(() => { i18n.global.locale.value = 'en' })

  it('shows a viewer the vehicle without any operate or admin control', async () => {
    auth.user = { ...memberUser }
    const viewed = { ...vehicle, access: 'view' as const }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [profile] : [viewed]))))
    const wrapper = mount(VehiclesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    expect(wrapper.text()).not.toContain('Add vehicle')
    expect(wrapper.find('.card-profile-select').exists()).toBe(false)
    // The assigned profile is a fact the viewer may read, just not change.
    expect(wrapper.get('.card-profile-name').text()).toBe('C-Zero')
    expect(wrapper.text()).not.toContain('Clear data')
    expect(wrapper.find('.vehicle-card footer .danger').exists()).toBe(false)
    expect(wrapper.find('input[type="file"]').exists()).toBe(false)
  })

  it('gives an operator the vehicle controls but not the administrator ones', async () => {
    auth.user = { ...memberUser }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [profile] : [vehicle]))))
    const wrapper = mount(VehiclesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    expect(wrapper.find('.card-profile-select').exists()).toBe(true)
    expect(wrapper.text()).toContain('Clear data')
    expect(wrapper.find('input[type="file"]').exists()).toBe(true)
    // Creating and deleting vehicles stays with the administrator.
    expect(wrapper.text()).not.toContain('Add vehicle')
    expect(wrapper.find('.vehicle-card footer .danger').exists()).toBe(false)
  })

  it('hides enrollment and agent actions from a viewer', async () => {
    auth.user = { ...memberUser }
    const viewed = { ...vehicle, access: 'view' as const }
    const device = { id: 'd1', vehicle_id: viewed.id, name: 'Pi Zero', credential_version: 1, ...deviceIdentity, hostname: 'car', hardware: {}, sampling_seconds: 5, upload_seconds: 5, parked_sampling_seconds: 300, parked_upload_seconds: 300, online: true, last_seen_at: null, last_config_sync_at: null, config_version: 1, revoked_at: null, created_at: '2026-01-01T00:00:00Z' }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(url.endsWith('/agent-implementations') ? agentImplementations : url.endsWith('/devices') ? [device] : url.endsWith('/vehicle-profiles') ? [profile] : [viewed]))))
    const wrapper = mount(DevicesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    expect(wrapper.text()).toContain('Pi Zero')
    expect(wrapper.find('.page-header .button').exists()).toBe(false)
    expect(wrapper.find('.device-actions').exists()).toBe(false)
  })

  it('hides profile creation without the permission and editing without editability', async () => {
    auth.user = { ...memberUser }
    const mine = { ...profile, id: 'p-mine', name: 'Mine', built_in: false, editable: true }
    const theirs = { ...profile, id: 'p-theirs', name: 'Theirs', built_in: false, editable: false }
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) =>
      Promise.resolve(jsonResponse(url.endsWith('/vehicle-profiles') ? [mine, theirs] : []))))
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    expect(wrapper.find('.header-actions .button').exists()).toBe(false)
    const cards = wrapper.findAll('.profile-card')
    const editable = cards.find((card) => card.text().includes('Mine'))!
    const readOnly = cards.find((card) => card.text().includes('Theirs'))!
    expect(editable.find('.profile-actions').exists()).toBe(true)
    expect(readOnly.find('.profile-actions').exists()).toBe(false)
    expect(readOnly.find('.readonly-badge').exists()).toBe(true)
  })

  it('offers profile creation to a holder of the dedicated permission', async () => {
    auth.user = { ...memberUser, permissions: { 'profiles.create': true } }
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonResponse([]))))
    const wrapper = mount(ProfilesView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    expect(wrapper.get('.header-actions .button').text()).toContain('New profile')
    expect(wrapper.find('.empty-profile').exists()).toBe(true)
  })

  function adminFetch(grants: Array<Record<string, unknown>>) {
    const accounts = [
      { id: adminUser.id, email: adminUser.email, display_name: adminUser.display_name, is_active: true, is_admin: true, can_create_profiles: false, created_at: '' },
      { id: 'member-1', email: 'member@example.com', display_name: 'Member', is_active: true, is_admin: false, can_create_profiles: false, created_at: '' },
      { id: 'member-2', email: 'other@example.com', display_name: 'Other', is_active: true, is_admin: false, can_create_profiles: false, created_at: '' },
    ]
    return vi.fn().mockImplementation((url: string, options?: RequestInit) => {
      if (url.endsWith(`/vehicles/${vehicle.id}/access`) && options?.method === 'PUT') {
        const saved = JSON.parse(options.body as string) as Array<{ user_id: string; level: string }>
        return Promise.resolve(jsonResponse(saved.map((grant) => ({ ...grant, email: 'x@example.com', display_name: 'X' }))))
      }
      if (url.endsWith(`/vehicles/${vehicle.id}/access`)) return Promise.resolve(jsonResponse(grants))
      if (url.endsWith('/admin/default-access') && options?.method === 'PUT') {
        return Promise.resolve(jsonResponse(JSON.parse(options.body as string)))
      }
      if (url.endsWith('/admin/default-access')) return Promise.resolve(jsonResponse({ profiles_create: false, grants: [] }))
      if (url.endsWith('/users')) return Promise.resolve(jsonResponse(accounts))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith('/system/diagnostics')) return Promise.resolve(jsonResponse({ version: 'test', database: 'ok', pending_jobs: 0, failed_jobs: 0, hook_failures: 0, stale_devices: 0, workers: [] }))
      return Promise.resolve(jsonResponse({}))
    })
  }

  it('replaces a vehicle\'s grants wholesale from the admin page', async () => {
    auth.user = { ...adminUser }
    const fetchMock = adminFetch([{ user_id: 'member-1', email: 'member@example.com', display_name: 'Member', level: 'view' }])
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    wrapper.get('.grant-list li').getComponent(AppSelect).vm.$emit('update:modelValue', 'operate')
    wrapper.get('.grant-add').getComponent(AppSelect).vm.$emit('update:modelValue', 'member-2')
    await flushPromises()
    await wrapper.get('.grant-add .button').trigger('click')
    await wrapper.findAll('.save-row .button')[0]!.trigger('click')
    await flushPromises()

    const put = fetchMock.mock.calls.find((call) => call[1]?.method === 'PUT')
    expect(put?.[0]).toBe(`/api/v1/vehicles/${vehicle.id}/access`)
    // Full replacement: what is on screen is exactly what is sent.
    expect(JSON.parse(put?.[1]?.body as string)).toEqual([
      { user_id: 'member-1', level: 'operate' },
      { user_id: 'member-2', level: 'view' },
    ])
  })

  it('saves the default-access template as one document', async () => {
    auth.user = { ...adminUser }
    const fetchMock = adminFetch([])
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(AdminView, { global: { plugins: [i18n], stubs } })
    await flushPromises()

    await wrapper.get('.settings-block .check input').setValue(true)
    await wrapper.findAll('.save-row .button')[1]!.trigger('click')
    await flushPromises()

    const put = fetchMock.mock.calls.find((call) => String(call[0]).endsWith('/admin/default-access') && call[1]?.method === 'PUT')
    expect(JSON.parse(put?.[1]?.body as string)).toEqual({ profiles_create: true, grants: [] })
  })
})
