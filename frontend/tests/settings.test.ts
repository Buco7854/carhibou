import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import i18n, { detectBrowserLocale } from '../src/i18n'
import SettingsView from '../src/views/SettingsView.vue'
import { jsonResponse } from './helpers'

describe('preferences', () => {
  it('detects the first supported browser language and falls back to English', () => {
    expect(detectBrowserLocale(['de-DE', 'fr-FR', 'en-US'])).toBe('fr')
    expect(detectBrowserLocale(['en-GB', 'fr-FR'])).toBe('en')
    expect(detectBrowserLocale(['de-DE'])).toBe('en')
  })

  it('persists French and explicit light theme while keeping Auto available', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(jsonResponse([])))
    auth.user = { id:'u1',email:'owner@example.com',display_name:'Owner',permissions:{} }
    const wrapper = mount(SettingsView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    const selects = wrapper.findAllComponents(AppSelect)
    selects[0]!.vm.$emit('update:modelValue', 'light')
    selects[1]!.vm.$emit('update:modelValue', 'fr')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('carhibou.theme')).toBe('light')
    expect(localStorage.getItem('carhibou.locale')).toBe('fr')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.text()).toContain('Apparence')
    await selects[0]!.get('.app-select-trigger').trigger('click')
    expect(wrapper.text()).toContain('Auto')
  })
})
