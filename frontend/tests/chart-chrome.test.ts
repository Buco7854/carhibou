import { mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../src/i18n'

const options: Array<Record<string, never>> = []
vi.mock('echarts/core', () => ({
  use: vi.fn(),
  init: () => ({
    setOption: (option: Record<string, never>) => { options.push(option) },
    resize: vi.fn(),
    dispose: vi.fn(),
  }),
}))
vi.mock('echarts/charts', () => ({ LineChart: {} }))
vi.mock('echarts/renderers', () => ({ CanvasRenderer: {} }))
vi.mock('echarts/components', () => ({
  DataZoomComponent: {}, GridComponent: {}, LegendComponent: {}, TooltipComponent: {},
}))

const { default: TimeSeriesChart } = await import('../src/components/TimeSeriesChart.vue')

interface Axis { name?: string }
interface Option {
  legend: { show?: boolean; data?: string[] }
  tooltip: { formatter?: (params: unknown) => string }
  xAxis: Axis
  yAxis: Axis
}

const points: Array<[string, number]> = [['2026-01-01T00:00:00Z', 1], ['2026-01-01T00:01:00Z', 2]]

interface ChartProps {
  series: Array<{ name: string; unit?: string; data: Array<[string | number, number]> }>
  xType?: 'time' | 'value'
  xUnit?: string
  yUnit?: string
  xName?: string
  yName?: string
  label?: string
}

function draw(props: ChartProps): Option {
  options.length = 0
  mount(TimeSeriesChart, { props, global: { plugins: [i18n] } })
  return options.at(-1) as unknown as Option
}

describe('chart chrome', () => {
  beforeEach(() => {
    i18n.global.locale.value = 'en'
    globalThis.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} } as never
  })

  it('draws no legend for a single series, because the title already named it', () => {
    const option = draw({ series: [{ name: 'Road speed', unit: 'km/h', data: points }] })
    expect(option.legend.show).toBe(false)
  })

  it('keeps the legend when it is the only thing telling the series apart', () => {
    const option = draw({ series: [
      { name: 'Road speed', unit: 'km/h', data: points },
      { name: 'Battery level', unit: '%', data: points },
    ] })
    expect(option.legend.show).not.toBe(false)
    expect(option.legend.data).toEqual(['Road speed', 'Battery level'])
  })

  it('leaves the series name out of a single-series tooltip, and keeps it in a shared one', () => {
    const single = draw({ series: [{ name: 'Charge rate', unit: 'kW', data: points }], xType: 'value', xUnit: '%' })
    const tip = single.tooltip.formatter!([{ axisValueLabel: '41', value: [41, 6.13] }])
    expect(tip).toContain('6.13 kW')
    expect(tip).toContain('41 %')
    // The card's heading says which metric this is; the tooltip would be the
    // second telling of it on the same card.
    expect(tip).not.toContain('Charge rate')

    const shared = draw({ series: [
      { name: 'Road speed', unit: 'km/h', data: points },
      { name: 'Battery level', unit: '%', data: points },
    ] })
    expect(shared.tooltip.formatter).toBeUndefined()
  })

  it('carries each unit once on its axis rather than on every tick', () => {
    const option = draw({ series: [{ name: 'Charge rate', unit: 'kW', data: points }], xType: 'value', xUnit: '%' })
    expect(option.xAxis.name).toBe('%')
    expect(option.yAxis.name).toBe('kW')
  })

  it('names the metric on the axis only when the title cannot have', () => {
    // A custom title need not mention the metrics, so the axes say which.
    const overridden = draw({
      series: [{ name: 'Charge rate', unit: 'kW', data: points }],
      xType: 'value', xUnit: '%', xName: 'Battery level', yName: 'Charge rate',
    })
    expect(overridden.xAxis.name).toBe('Battery level (%)')
    expect(overridden.yAxis.name).toBe('Charge rate (kW)')
  })

  it('describes itself to a reader who cannot see it, in their language', () => {
    expect(draw({ series: [{ name: 'x', data: points }], label: 'Charge rate vs Battery level' })).toBeTruthy()
    const chart = mount(TimeSeriesChart, {
      props: { series: [{ name: 'x', data: points }], label: 'Charge rate vs Battery level' },
      global: { plugins: [i18n] },
    })
    expect(chart.get('[role="img"]').attributes('aria-label')).toBe('Charge rate vs Battery level')

    i18n.global.locale.value = 'fr'
    const generic = mount(TimeSeriesChart, { props: { series: [{ name: 'x', data: points }] }, global: { plugins: [i18n] } })
    expect(generic.get('[role="img"]').attributes('aria-label')).toBe('Graphique de télémétrie')
  })
})
