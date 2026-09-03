import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it } from 'vitest'
import i18n from '../src/i18n'
import MetricKeyReference from '../src/components/MetricKeyReference.vue'
import { resetMetricKeys } from '../src/metricRegistry'
import { jsonResponse, mockApi } from './helpers'

const REGISTRY = {
  metrics: [
    { key: 'battery.soc', unit: '%', meaning: 'how much charge is left in the main battery, from zero to one hundred', kind: 'state', value_type: 'number', retained: true, freshness_seconds: 900 },
    { key: 'vehicle.speed', unit: 'km/h', meaning: 'how fast the vehicle is moving', kind: 'measurement', value_type: 'number', retained: false, freshness_seconds: 180 },
    { key: 'site.custom', unit: null, meaning: 'a kind this build has no word for', kind: 'ledger', value_type: 'number', retained: false, freshness_seconds: 60 },
  ],
  // The server's own words, in the register it publishes them in: these are
  // read straight onto the screen, so a fixture in another voice would be
  // testing prose the reader never sees.
  position: {
    meaning: "the vehicle's location, recorded as one whole: latitude, longitude, altitude, speed, heading and accuracy always come from the same moment and are never mixed between moments",
    fields: [
      { key: 'latitude', unit: '\u00b0', meaning: 'how far north or south of the equator, in degrees' },
      { key: 'longitude', unit: '\u00b0', meaning: 'how far east or west of the prime meridian, in degrees' },
      { key: 'speed', unit: 'km/h', meaning: 'how fast the vehicle is moving, measured by the receiver rather than the vehicle' },
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
    // That a fix holds together, and where its speed comes from, are the
    // server's words rather than ours, and they reach the screen unaltered.
    expect(entry.get('.key-meaning').text()).toContain('never mixed between moments')
    expect(entry.text()).toContain('measured by the receiver rather than the vehicle')
    expect(entry.text()).toContain('how far north or south of the equator')
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
