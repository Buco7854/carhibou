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
  position: {
    meaning: 'the GNSS fix: reported and stored as one indivisible observation - fields are never combined across instants',
    fields: [
      { key: 'latitude', unit: '\u00b0', meaning: 'north-positive angular distance from the equator' },
      { key: 'longitude', unit: '\u00b0', meaning: 'east-positive angular distance from the prime meridian' },
      { key: 'speed', unit: 'km/h', meaning: 'GNSS ground speed; a candidate for vehicle.speed' },
    ],
  },
}

/** What a server that predates the descriptor answers. */
const REGISTRY_WITHOUT_POSITION = { metrics: REGISTRY.metrics }

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

  it('pins the fix above the metrics, in the words the server chose', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    const page = open()
    await flushPromises()
    const entry = page.get('.position-entry')
    // The rule editor takes these namespaced, so the reference offers them that
    // way even though the registry names the bare field.
    expect(entry.findAll('.position-fields code').map((field) => field.text())).toEqual([
      'position.latitude', 'position.longitude', 'position.speed',
    ])
    expect(entry.get('.key-kind').text()).toBe('Fix')
    // Atomicity and the speed candidacy are the server's words, not ours.
    expect(entry.get('.key-meaning').text()).toContain('never combined across instants')
    expect(entry.text()).toContain('a candidate for vehicle.speed')
    expect(entry.text()).toContain('north-positive angular distance')
    // A fix is not a registry metric and must not be counted as one.
    expect(page.get('.reference-count').text()).toBe('3 keys')
    expect(page.findAll('.key-list li')).toHaveLength(3)
  })

  it('says nothing about position when the server does not describe it', async () => {
    mockApi({ '/metrics/registry': REGISTRY_WITHOUT_POSITION })
    const page = open()
    await flushPromises()
    expect(page.find('.position-entry').exists()).toBe(false)
    // The metrics still list, so absence of the descriptor costs nothing else.
    expect(page.findAll('.key-list li')).toHaveLength(3)
  })

  it('leaves the fix out when the search is about something else', async () => {
    mockApi({ '/metrics/registry': REGISTRY })
    const page = open()
    await flushPromises()
    await page.get('input[type="search"]').setValue('latitude')
    expect(page.find('.position-entry').exists()).toBe(true)
    expect(page.findAll('.key-list li')).toHaveLength(0)
    await page.get('input[type="search"]').setValue('battery')
    expect(page.find('.position-entry').exists()).toBe(false)
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
    // The fix's own words stay as the server sent them; only the chrome around
    // them is translated.
    expect(page.get('.position-entry').get('.key-kind').text()).toBe('Point')
  })
})
