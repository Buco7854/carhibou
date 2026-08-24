import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import LoginView from '../src/views/LoginView.vue'
import { jsonResponse } from './helpers'

describe('login', () => {
  beforeEach(() => {
    localStorage.clear()
    i18n.global.locale.value = 'en'
  })

  it('logs in with a server-side session flow and can render French', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/setup')) return Promise.resolve(jsonResponse({ registration_open: false }))
      return Promise.resolve(jsonResponse({
        user: { id: 'u1', email: 'driver@example.com', display_name: 'Driver', permissions: {} },
        csrf_token: 'csrf_test',
      }))
    })
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/login')
    const wrapper = mount(LoginView, { global: { plugins: [router, i18n] } })
    await flushPromises()
    expect(wrapper.text()).not.toContain('Sources')
    expect(wrapper.text()).not.toContain('PostgreSQL history')
    expect(wrapper.text()).not.toContain('Create the initial administrator')
    await wrapper.get('#email').setValue('driver@example.com')
    await wrapper.get('#password').setValue('long-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/login', expect.objectContaining({ credentials: 'same-origin' }))

    i18n.global.locale.value = 'fr'
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('Espace de télémétrie automobile')
  })

  it('offers one-time administrator setup only while the instance is empty', async () => {
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/auth/setup')) return Promise.resolve(jsonResponse({ registration_open: true }))
      return Promise.resolve(jsonResponse({
        user: { id: 'u1', email: 'owner@example.com', display_name: 'Owner', permissions: { 'system.admin': true } },
        csrf_token: 'csrf_test',
      }, 201))
    })
    vi.stubGlobal('fetch', fetchMock)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/', component: { template: '<div />' } }] })
    await router.push('/login')
    const wrapper = mount(LoginView, { global: { plugins: [router, i18n] } })
    await flushPromises()

    expect(wrapper.get('h2').text()).toBe('Create the administrator account')
    await wrapper.get('#name').setValue('Owner')
    await wrapper.get('#email').setValue('owner@example.com')
    await wrapper.get('#password').setValue('first-owner-password')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(fetchMock).toHaveBeenCalledWith('/api/v1/auth/register', expect.objectContaining({ method: 'POST' }))
  })
})
