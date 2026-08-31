import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../src/i18n'
import MetricKeyReference from '../src/components/MetricKeyReference.vue'
import { resetMetricKeys } from '../src/metricRegistry'
import { jsonResponse, mockApi } from './helpers'

const REGISTRY = {
  metrics: [
    { key: 'battery.soc', unit: '%', meaning: 'state of charge', kind: 'state', value_type: 'number', retained: true, freshness_seconds: 900 },
    { key: 'vehicle.speed', unit: 'km/h', meaning: 'road speed', kind: 'measurement', value_type: 'number', retained: false, freshness_seconds: 180 },
    { key: 'site.custom', unit: null, meaning: 'a kind this build has no word for', kind: 'ledger', value_type: 'number', retained: false, freshness_seconds: 60 },
  ],
}

function open() {
  return mount(MetricKeyReference, { props: { open: true }, global: { plugins: [i18n], stubs: { Teleport: true } } })
}

describe('metric key reference', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    resetMetricKeys()
  })

  it('lists what the server publishes, in the words an author reads elsewhere', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    const page = open()
    await flushPromises()
    const rows = page.findAll('.key-list li')
    expect(rows).toHaveLength(3)
    expect(rows[0]!.get('.key-name').text()).toBe('battery.soc')
    // The display-name catalogue supplies the label wherever the key is one the
    // interface already renders.
    expect(rows[0]!.get('.key-label').text()).toBe('Battery level')
    const facts = rows[0]!.get('.key-facts').text()
    expect(facts).toContain('State')
    expect(facts).toContain('Number')
    expect(facts).toContain('15 minutes')
    expect(facts).toContain('stays on screen')
    expect(rows[1]!.get('.key-facts').text()).toContain('clears once it goes stale')
  })

  it('shows a word the server invented rather than an empty space', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    const page = open()
    await flushPromises()
    expect(page.findAll('.key-list li')[2]!.get('.key-facts').text()).toContain('ledger')
  })

  it('narrows to what the search matches, by key or by meaning', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    const page = open()
    await flushPromises()
    await page.get('input[type="search"]').setValue('road')
    expect(page.findAll('.key-list li').map((row) => row.get('.key-name').text())).toEqual(['vehicle.speed'])
    await page.get('input[type="search"]').setValue('nothing here')
    expect(page.findAll('.key-list li')).toHaveLength(0)
    expect(page.text()).toContain('No key matches')
  })

  it('says so when the server has no registry to serve, and offers to ask again', async () => {
    // The endpoint can land in a later deploy than this page.
    const fetchMock = mockApi({ '/metrics/registry': jsonResponse({ detail: 'Not Found' }, 404) })
    const page = open()
    await flushPromises()
    expect(page.find('[role="alert"]').exists()).toBe(true)
    expect(page.text()).toContain('not available from this server')
    expect(page.findAll('.key-list li')).toHaveLength(0)

    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse(REGISTRY)))
    await page.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(page.findAll('.key-list li')).toHaveLength(3)
  })

  it('refuses a payload that is not a registry rather than rendering nothing', async () => {
    // An older server answers this path with something else entirely.
    mockApi({ '/metrics/registry': [{ id: 'a-vehicle' }] })
    const page = open()
    await flushPromises()
    expect(page.text()).toContain('not available from this server')
  })

  it('keeps its own words in French', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    i18n.global.locale.value = 'fr'
    const page = open()
    await flushPromises()
    const facts = page.findAll('.key-list li')[0]!.get('.key-facts').text()
    expect(facts).toContain('État')
    expect(facts).toContain('Nombre')
    expect(facts).toContain('reste affichée')
  })
})
