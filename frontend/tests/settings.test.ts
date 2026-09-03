import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { auth } from '../src/api/auth'
import AppSelect from '../src/components/AppSelect.vue'
import i18n, { detectBrowserLocale } from '../src/i18n'
import { mapPreferences, setMapPreferences } from '../src/mapPreferences'
import { DEFAULT_MAP_PREFERENCES } from '../src/mapStyle'
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
    setMapPreferences(DEFAULT_MAP_PREFERENCES)
    auth.user = { id:'u1',email:'owner@example.com',display_name:'Owner',permissions:{} }
    const wrapper = mount(SettingsView, { global:{plugins:[i18n],stubs:{Teleport:true}} })
    // Addressed by what each control is, not by where it sits: a new preference
    // between them used to renumber every assertion below it.
    const control = (id: string) => wrapper.findAllComponents(AppSelect)
      .find((select) => select.props('id') === id)!
    control('theme').vm.$emit('update:modelValue', 'light')
    control('locale').vm.$emit('update:modelValue', 'fr')
    await wrapper.vm.$nextTick()
    expect(localStorage.getItem('carhibou.theme')).toBe('light')
    expect(localStorage.getItem('carhibou.locale')).toBe('fr')
    expect(document.documentElement.dataset.theme).toBe('light')
    expect(wrapper.text()).toContain('Apparence')
    await control('theme').get('.app-select-trigger').trigger('click')
    expect(wrapper.text()).toContain('Auto')

    expect(control('map-light-style').props('modelValue')).toBe('liberty')
    expect(control('map-dark-style').props('modelValue')).toBe('dark')
    expect(wrapper.find('#map-fixed-style').exists()).toBe(false)

    control('map-light-style').vm.$emit('update:modelValue', 'positron')
    control('map-dark-style').vm.$emit('update:modelValue', 'fiord')
    control('map-mode').vm.$emit('update:modelValue', 'fixed')
    await wrapper.vm.$nextTick()
    control('map-fixed-style').vm.$emit('update:modelValue', 'bright')
    await wrapper.vm.$nextTick()
    expect(mapPreferences.value).toEqual({
      providerId: 'openfreemap',
      mode: 'fixed',
      lightStyleId: 'positron',
      darkStyleId: 'fiord',
      fixedStyleId: 'bright',
    })
    expect(JSON.parse(localStorage.getItem('carhibou.map-preferences') ?? '{}'))
      .toEqual(mapPreferences.value)
    expect(document.documentElement.dataset.theme, 'the interface is unmoved').toBe('light')
  })
})
