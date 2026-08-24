import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import HooksView from '../src/views/HooksView.vue'
import { jsonResponse, vehicle } from './helpers'

describe('hook editor', () => {
  it('shows the privileged-code warning and masks secret input and stored values', async () => {
    vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
      if (url.endsWith('/hooks')) return Promise.resolve(jsonResponse([]))
      if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
      if (url.endsWith('/secrets')) return Promise.resolve(jsonResponse([{ id:'s1',name:'gate_token',masked:'••••••••',created_at:'',updated_at:'' }]))
      return Promise.resolve(jsonResponse({}))
    }))
    const wrapper = mount(HooksView, { global: { plugins:[i18n], stubs:{CodeEditor:{template:'<textarea data-editor />'}} } })
    await flushPromises()
    expect(wrapper.text()).toContain('Privileged code')
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('••••••••')
    expect(wrapper.text()).not.toContain('plaintext-secret')
  })
})
