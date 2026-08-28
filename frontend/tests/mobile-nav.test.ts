import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent } from 'vue'
import App from '../src/App.vue'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import en from '../src/i18n/locales/en'
import fr from '../src/i18n/locales/fr'
import { adminUser, memberUser } from './helpers'

// The shell reads the current route to close the sheet after navigating, which
// needs a router the mounted component can actually ask.
vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn(), currentRoute: { value: { fullPath: '/' } } }),
  RouterLink: { props: { to: { type: String, default: '' } }, template: '<a :href="to"><slot /></a>' },
  RouterView: { template: '<div />' },
}))

// The bar lays out a fixed number of columns, so an entry past the last one does
// not overflow, it wraps onto a second row behind the page. That is silent, which
// is why the count is asserted rather than eyeballed.
const BAR_SLOTS = 5

const stubs = {
  Teleport: true,
  RouterLink: defineComponent({ props: { to: { type: String, default: '' } }, template: '<a :href="to"><slot /></a>' }),
  RouterView: { template: '<div />' },
}

function shell() {
  return mount(App, { global: { plugins: [i18n], stubs } })
}

describe('mobile navigation', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.resolve(jsonEmpty())))
  })

  function jsonEmpty() {
    return { ok: true, status: 200, json: () => Promise.resolve([]) } as unknown as Response
  }

  it('fills the bar to the same width whoever is signed in', () => {
    for (const [role, user] of [['administrator', adminUser], ['member', memberUser]] as const) {
      auth.user = { ...user }
      const wrapper = shell()
      // Four destinations plus More: an administrator's extra pages must not take
      // a slot, which is exactly what pushed the bar onto a second row.
      const tabs = wrapper.findAll('.main-nav > a:not(.nav-secondary)')
      expect(tabs.length + 1, role).toBe(BAR_SLOTS)
      expect(wrapper.findAll('.nav-more').length, role).toBe(1)
      wrapper.unmount()
    }
  })

  it('keeps every destination reachable, and the account tools with them', () => {
    auth.user = { ...adminUser }
    const wrapper = shell()
    const routes = [
      ...wrapper.findAll('.main-nav > a').map((link) => link.attributes('href')),
    ]
    expect(new Set(routes)).toEqual(new Set(['/', '/vehicles', '/data-sources', '/profiles', '/hooks', '/settings', '/admin']))
    // The rail keeps these in a foot the phone hides, so the sheet has to carry
    // them or a phone has no way to sign out at all.
    const sheet = wrapper.find('.nav-sheet')
    expect(sheet.exists()).toBe(false)
    wrapper.unmount()
  })

  it('names every tab in both locales, short enough for a phone', () => {
    for (const [locale, messages] of [['en', en], ['fr', fr]] as const) {
      const short = messages.nav.short as Record<string, string>
      expect(Object.keys(short).sort(), locale).toEqual(['dashboards', 'dataSources', 'profiles', 'vehicles'])
      for (const [key, label] of Object.entries(short)) {
        expect(label.length, `${locale}.${key}`).toBeLessThanOrEqual(10)
      }
      expect(messages.nav.more.length, locale).toBeLessThanOrEqual(10)
    }
  })
})
