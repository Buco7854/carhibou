import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AppSelect from '../src/components/AppSelect.vue'
import HistoryTable from '../src/components/HistoryTable.vue'
import i18n from '../src/i18n'
import { jsonResponse, readings } from './helpers'

const BUCKET_START = '2026-01-01T10:05:00Z'
const BUCKET_END = '2026-01-01T10:06:00Z'

// One row measured in its own bucket, one carried from an hour earlier, and a
// row standing for several identical buckets.
function table(overrides: Record<string, unknown> = {}) {
  return {
    vehicle_id: 'vehicle-1',
    start: '2026-01-01T00:00:00Z',
    end: '2026-01-01T12:00:00Z',
    step_seconds: 60,
    total: 240,
    limit: 100,
    offset: 0,
    rows: [
      {
        bucket_start: BUCKET_START,
        bucket_end: BUCKET_END,
        collapsed_buckets: 1,
        readings: {
          ...readings({ 'vehicle.speed': 42 }, { observed_at: '2026-01-01T10:05:30Z' }),
          ...readings({ 'battery.soc': 61 }, { observed_at: '2026-01-01T09:05:00Z' }),
        },
        position: null,
        agent: {},
      },
      {
        bucket_start: '2026-01-01T09:00:00Z',
        bucket_end: '2026-01-01T09:20:00Z',
        collapsed_buckets: 20,
        readings: readings({ 'battery.soc': 61 }, { observed_at: '2026-01-01T09:00:10Z' }),
        position: null,
        agent: {},
      },
    ],
    ...overrides,
  }
}

function mountTable() {
  return mount(HistoryTable, {
    props: { vehicleId: 'vehicle-1', days: 1 },
    global: { plugins: [i18n], stubs: { Teleport: true } },
  })
}

function lastQuery(fetchMock: ReturnType<typeof vi.fn>): URLSearchParams {
  return new URL(String(fetchMock.mock.calls.at(-1)?.[0]), 'http://localhost').searchParams
}

describe('history snapshot table', () => {
  let fetchMock: ReturnType<typeof vi.fn>

  beforeEach(() => {
    fetchMock = vi.fn().mockImplementation(() => Promise.resolve(jsonResponse(table())))
    vi.stubGlobal('fetch', fetchMock)
  })

  it('asks the table endpoint for a supported step', async () => {
    mountTable()
    await flushPromises()
    const query = lastQuery(fetchMock)
    expect(String(fetchMock.mock.calls.at(-1)?.[0])).toContain('/history/table')
    // Chosen from the range rather than typed by the reader: a day of history
    // asks for five-minute rows, which the route accepts from its own list.
    expect(query.get('step_seconds')).toBe('300')
    expect(query.get('limit')).toBe('100')
    expect(query.get('offset')).toBe('0')
  })

  it('marks a carried value as old and leaves a measured one alone', async () => {
    const wrapper = mountTable()
    await flushPromises()

    const cells = wrapper.findAll('tbody tr')[0]!.findAll('td')
    const text = cells.map((cell) => cell.text()).join(' | ')
    expect(text).toContain('42')
    expect(text).toContain('61')
    // The speed was observed inside its bucket, so it reads as measured.
    const speedCell = cells.find((cell) => cell.text().includes('42'))!
    expect(speedCell.find('.is-carried').exists()).toBe(false)
    // The charge was observed an hour before this bucket, so it is dimmed and
    // says how old it is rather than passing for a fresh reading.
    const socCell = cells.find((cell) => cell.text().includes('61'))!
    expect(socCell.find('.is-carried').exists()).toBe(true)
    expect(socCell.find('.carried-age').text()).not.toBe('')
  })

  it('reports how many buckets a collapsed row stands for', async () => {
    const wrapper = mountTable()
    await flushPromises()
    // The server collapses identical consecutive rows; re-materializing them
    // client-side is exactly what the contract asks callers not to do.
    expect(wrapper.findAll('tbody tr')).toHaveLength(2)
    expect(wrapper.findAll('tbody tr')[1]!.text()).toContain('20')
  })

  it('pages through the server total instead of fetching it whole', async () => {
    const wrapper = mountTable()
    await flushPromises()
    await wrapper.findAll('.table-pager .button')[1]!.trigger('click')
    await flushPromises()
    expect(lastQuery(fetchMock).get('offset')).toBe('100')
  })

  it('starts again from the first page when the resolution changes', async () => {
    const wrapper = mountTable()
    await flushPromises()
    await wrapper.findAll('.table-pager .button')[1]!.trigger('click')
    await flushPromises()

    wrapper.getComponent(AppSelect).vm.$emit('update:modelValue', 3600)
    await flushPromises()
    const query = lastQuery(fetchMock)
    expect(query.get('step_seconds')).toBe('3600')
    // A coarser step means different rows, so the old page number means nothing.
    expect(query.get('offset')).toBe('0')
  })
})
