import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter, type Router } from 'vue-router'
import i18n from '../src/i18n'
import HooksView from '../src/views/HooksView.vue'
import { acceptConfirm, closeConfirm, confirmRequest } from '../src/confirm'
import { jsonResponse, vehicle } from './helpers'

const hooks = [
  { id:'hook-1', name:'Low battery warning', description:'Warns below 20%', enabled:true, trigger_type:'telemetry.received',
    vehicle_id:null, source:'return\n', timeout_seconds:10, revision:2, created_at:'', updated_at:'', last_execution:null },
  { id:'hook-2', name:'Charge finished push', description:'', enabled:false, trigger_type:'telemetry.received',
    vehicle_id:null, source:'return\n', timeout_seconds:10, revision:1, created_at:'', updated_at:'', last_execution:null },
]

function stubApi(rows = hooks) {
  vi.stubGlobal('fetch', vi.fn().mockImplementation((url: string) => {
    if (url.endsWith('/hooks')) return Promise.resolve(jsonResponse(rows))
    if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
    if (url.endsWith('/secrets')) return Promise.resolve(jsonResponse([{ id:'s1',name:'gate_token',masked:'••••••••',created_at:'',updated_at:'' }]))
    return Promise.resolve(jsonResponse([]))
  }))
}

function makeRouter(): Router {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/hooks', name: 'hooks', component: HooksView },
      { path: '/hooks/:id', name: 'hook', component: HooksView },
    ],
  })
}

/**
 * Mounted through a router-view rather than directly.
 *
 * The unsaved-edit guard attaches to the matched route record, so a component
 * mounted outside one silently has no guard: testing it any other way would be
 * testing a page that cannot exist.
 */
async function open(path = '/hooks') {
  const router = makeRouter()
  router.push(path)
  await router.isReady()
  const wrapper = mount(
    { template: '<router-view />' },
    { global: { plugins: [i18n, router], stubs: { CodeEditor: { template: '<textarea data-editor />' }, Teleport: true } } },
  )
  await flushPromises()
  return { wrapper, router }
}

describe('hook editor', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    closeConfirm()
  })

  it('shows the privileged-code warning and masks secret input and stored values', async () => {
    stubApi([])
    const { wrapper } = await open()
    expect(wrapper.text()).toContain('Privileged code')
    expect(wrapper.find('input[type="password"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('••••••••')
    expect(wrapper.text()).not.toContain('plaintext-secret')
  })

  it('opens nothing on arrival, and says which absence it is', async () => {
    stubApi()
    const { wrapper, router } = await open()
    // Redirecting to an arbitrary hook would rewrite the address and leave the
    // reader with nothing to go back to.
    expect(router.currentRoute.value.path).toBe('/hooks')
    expect(wrapper.text()).toContain('Choose a hook')
    expect(wrapper.find('.detail-bar').exists()).toBe(false)
  })

  it('puts the open hook in the address, so it survives a reload and can be linked to', async () => {
    stubApi()
    const { wrapper, router } = await open()
    await wrapper.findAll('.hook-row')[1]!.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/hooks/hook-2')
    expect(wrapper.get('.detail-identity h2').text()).toBe('Charge finished push')

    // Arriving straight at the address opens the same hook.
    stubApi()
    const direct = await open('/hooks/hook-1')
    expect(direct.wrapper.get('.detail-identity h2').text()).toBe('Low battery warning')
  })

  it('marks the layout so a phone can show one pane at a time', async () => {
    stubApi()
    const { wrapper } = await open('/hooks/hook-1')
    expect(wrapper.get('.hooks-layout').classes()).toContain('detail-open')
    const { wrapper: list } = await open()
    expect(list.get('.hooks-layout').classes()).not.toContain('detail-open')
  })

  it('asks before leaving a hook with edits that were never saved', async () => {
    stubApi()
    const { wrapper, router } = await open('/hooks/hook-1')
    const name = wrapper.get('.hook-editor-form input.input')
    await name.setValue('Renamed but not saved')
    await flushPromises()

    void router.push('/hooks')
    await flushPromises()
    expect(confirmRequest.value?.title).toBe('Unsaved changes')
    expect(confirmRequest.value?.question).toContain('Low battery warning')
    // Refusing keeps the reader where their work is.
    closeConfirm()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/hooks/hook-1')

    void router.push('/hooks')
    await flushPromises()
    await acceptConfirm()
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/hooks')
  })

  it('leaves without a word when nothing was changed', async () => {
    stubApi()
    const { router } = await open('/hooks/hook-1')
    void router.push('/hooks')
    await flushPromises()
    expect(confirmRequest.value).toBeNull()
    expect(router.currentRoute.value.path).toBe('/hooks')
  })
})
