import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'
import { auth } from '../src/api/auth'
import DataSourcesView from '../src/views/DataSourcesView.vue'
import { acceptConfirm, closeConfirm, confirmOption, confirmRequest } from '../src/confirm'
import { adminUser, agentImplementations, agentRow, connectorKinds, connectorRow, jsonResponse, vehicle } from './helpers'

const connector = connectorRow()

const retired = [
  { source_id: 'agent-old', name: 'Garage Pi', source_kind: 'agent', retired_at: '2026-08-01T09:00:00Z', samples: 4210, oldest: '2026-05-02T06:00:00Z', newest: '2026-07-31T21:40:00Z' },
  { source_id: 'conn-old', name: 'TeslaMate feed', source_kind: 'connector', retired_at: '2026-08-10T09:00:00Z', samples: 900, oldest: '2026-06-01T06:00:00Z', newest: '2026-08-09T21:40:00Z' },
  { source_id: 'agent-blank', name: 'Bench unit', source_kind: 'agent', retired_at: '2026-08-20T12:00:00Z', samples: 0, oldest: null, newest: null },
]

function api(options: { retired?: unknown[] } = {}) {
  const calls: Array<{ url: string; method: string }> = []
  const fetchMock = vi.fn().mockImplementation((url: string, init?: RequestInit) => {
    calls.push({ url, method: (init?.method ?? 'GET').toUpperCase() })
    if (url.endsWith('/agents/retired')) return Promise.resolve(jsonResponse(options.retired ?? retired))
    if ((url.includes('/agents/') || url.includes('/connectors/')) && (init?.method ?? '') === 'DELETE') return Promise.resolve(new Response(null, { status: 204 }))
    if (url.endsWith('/connectors')) return Promise.resolve(jsonResponse([connector]))
    if (url.endsWith('/agents')) return Promise.resolve(jsonResponse([agentRow()]))
    if (url.endsWith('/vehicles')) return Promise.resolve(jsonResponse([vehicle]))
    if (url.endsWith('/agent-implementations')) return Promise.resolve(jsonResponse(agentImplementations))
    if (url.endsWith('/connector-kinds')) return Promise.resolve(jsonResponse(connectorKinds))
    return Promise.resolve(jsonResponse([]))
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

function open() {
  return mount(DataSourcesView, { global: { plugins: [i18n], stubs: { Teleport: true, RouterLink: { template: '<a><slot /></a>' } } } })
}

describe('removing an agent, and what it leaves behind', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    auth.user = { ...adminUser }
    closeConfirm()
  })

  it('retires by default, keeping everything the agent recorded', async () => {
    const calls = api()
    const page = open()
    await flushPromises()
    await page.get('.source-actions .row-menu-button').trigger('click')
    await page.findAll('.source-actions .row-menu-list button').at(-1)!.trigger('click')
    await flushPromises()

    expect(confirmRequest.value?.title).toBe('Remove agent')
    expect(confirmRequest.value?.detail).toContain('remain')
    // The purge is offered here, and it is off until it is chosen.
    expect(confirmRequest.value?.option?.label).toContain('Also delete')
    await acceptConfirm()
    await flushPromises()

    const deletes = calls.filter((call) => call.method === 'DELETE')
    expect(deletes).toHaveLength(1)
    expect(deletes[0]!.url).not.toContain('purge_telemetry')
  })

  it('purges only when the destructive choice is taken', async () => {
    const calls = api()
    const page = open()
    await flushPromises()
    await page.get('.source-actions .row-menu-button').trigger('click')
    await page.findAll('.source-actions .row-menu-list button').at(-1)!.trigger('click')
    await flushPromises()
    confirmOption.value = true
    await acceptConfirm()
    await flushPromises()

    expect(calls.find((call) => call.method === 'DELETE')?.url).toContain('purge_telemetry=true')
  })

  it('accounts for what each retired source still holds', async () => {
    api()
    const page = open()
    await flushPromises()
    const rows = page.findAll('.retired-row')
    expect(rows).toHaveLength(3)
    expect(rows[0]!.text()).toContain('Garage Pi')
    expect(rows[0]!.text()).toContain('4210 readings')
    // Both kinds retire into the same list, and each says which it was.
    expect(rows[0]!.text()).toContain('Agent')
    expect(rows[1]!.text()).toContain('Connector')
    // A source that never reported has no range to state, and says so.
    expect(rows[2]!.text()).toContain('Never reported')
  })

  it('purges a retired connector on its own path, not the agent one', async () => {
    const calls = api()
    const page = open()
    await flushPromises()
    await page.findAll('.retired-row')[1]!.get('.row-menu-button').trigger('click')
    await page.findAll('.retired-row')[1]!.get('.row-menu-list .danger').trigger('click')
    await flushPromises()
    expect(confirmRequest.value?.question).toContain('TeslaMate feed')
    await acceptConfirm()
    await flushPromises()
    expect(calls.find((call) => call.method === 'DELETE')?.url).toContain('/connectors/conn-old?purge_telemetry=true')
  })

  it('offers a connector the same retire-or-purge choice an agent gets', async () => {
    const calls = api()
    const page = open()
    await flushPromises()
    const menu = page.findAll('.source-actions .row-menu-button')
    await menu.at(-1)!.trigger('click')
    await page.findAll('.row-menu-list button').at(-1)!.trigger('click')
    await flushPromises()

    expect(confirmRequest.value?.title).toBe('Remove connector')
    expect(confirmRequest.value?.detail).toContain('stops collecting')
    expect(confirmRequest.value?.option?.label).toContain('Also delete')
    confirmOption.value = true
    await acceptConfirm()
    await flushPromises()
    expect(calls.find((call) => call.method === 'DELETE')?.url).toContain('/connectors/')
    expect(calls.find((call) => call.method === 'DELETE')?.url).toContain('purge_telemetry=true')
  })

  it('says how much a purge deletes before it deletes it', async () => {
    const calls = api()
    const page = open()
    await flushPromises()
    await page.get('.retired-row .row-menu-button').trigger('click')
    await page.get('.retired-row .row-menu-list .danger').trigger('click')
    await flushPromises()

    expect(confirmRequest.value?.question).toContain('Garage Pi')
    expect(confirmRequest.value?.detail).toContain('4210 readings')
    await acceptConfirm()
    await flushPromises()
    expect(calls.find((call) => call.method === 'DELETE')?.url).toContain('/agents/agent-old?purge_telemetry=true')
  })

  it('says so plainly when nothing is retired', async () => {
    api({ retired: [] })
    const page = open()
    await flushPromises()
    expect(page.findAll('.retired-row')).toHaveLength(0)
    expect(page.text()).toContain('No retired sources.')
  })
})
