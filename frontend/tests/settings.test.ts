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
    // Addressed by what each control is, not by where it sits: a new preference
    // between them used to renumber every assertion below it.
    const selects = wrapper.findAllComponents(AppSelect)
    const control = (id: string) => selects.find((select) => select.props('id') === id)!
    control('theme').vm.$emit('update:modelValue', 'light')
    control('locale').vm.$emit('update:modelValue', 'fr')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('carhibou.theme')).toBe('light')
    expect(localStorage.getItem('carhibou.locale')).toBe('fr')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.text()).toContain('Apparence')
    await control('theme').get('.app-select-trigger').trigger('click')
    expect(wrapper.text()).toContain('Auto')

    // The map may be told to differ from the interface it sits in.
    control('map-theme').vm.$emit('update:modelValue', 'dark')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('carhibou.map-theme')).toBe('dark')
    expect(document.documentElement.dataset.theme, 'the interface is unmoved').toBe('light')
  })
})
