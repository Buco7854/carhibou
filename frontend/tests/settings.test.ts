import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { auth } from '../src/api/auth'
import i18n from '../src/i18n'
import SettingsView from '../src/views/SettingsView.vue'
import { jsonResponse } from './helpers'

describe('preferences', () => {
  it('persists French and explicit light theme while keeping Auto available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])))
    auth.user = { id:'u1',email:'owner@example.com',display_name:'Owner',permissions:{} }
    const wrapper = mount(SettingsView, { global:{plugins:[i18n]} })
    const selects = wrapper.findAll('select')
    await selects[0]!.setValue('light')
    await selects[1]!.setValue('fr')
    expect(localStorage.getItem('vehinode.theme')).toBe('light')
    expect(localStorage.getItem('vehinode.locale')).toBe('fr')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.text()).toContain('Apparence')
    expect(wrapper.find('option[value="auto"]').exists()).toBe(true)
  })
})
