<script setup lang="ts">
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ChartDatum } from '../chartData'
import { formatNumber } from '../numberFormat'
import { resolvedTheme } from '../theme'

const props = withDefaults(defineProps<{
  series: Array<{ name: string; unit?: string; data: ChartDatum[] }>
  height?: number | string
  xType?: 'time' | 'value'
  xUnit?: string
  yUnit?: string
  /**
   * The metric an axis stands for, and only when the card's own title does not
   * already say it. A title naming both metrics is the common case, so an axis
   * normally carries its unit and nothing else.
   */
  xName?: string
  yName?: string
  /** What the chart is, for a reader who cannot see it. */
  label?: string
}>(), { xType: 'time', xUnit: '', yUnit: '', xName: '', yName: '', label: '' })
const element = ref<HTMLDivElement>()
const { t, locale } = useI18n()

/** One rendition each: the name if the title has not said it, then the unit. */
function axisName(name: string, unit: string): string {
  if (name && unit) return `${name} (${unit})`
  return name || unit
}
echarts.use([LineChart, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
let chart: echarts.EChartsType | undefined
let observer: ResizeObserver | undefined

function render() {
  const styles = getComputedStyle(document.documentElement)
  const muted = styles.getPropertyValue('--muted').trim()
  const panel = styles.getPropertyValue('--panel').trim()
  const line = styles.getPropertyValue('--line').trim()
  const text = styles.getPropertyValue('--text').trim()
  const palette = [1, 2, 3, 4].map((slot) => styles.getPropertyValue(`--chart-${slot}`).trim())
  const multiple = props.series.length > 1
  const xLabel = axisName(props.xName, props.xUnit)
  const yLabel = axisName(props.yName, props.yUnit || props.series[0]?.unit || '')
  chart?.setOption({
    backgroundColor: 'transparent',
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      backgroundColor: panel,
      borderColor: line,
      textStyle: { color: text, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      axisPointer: { type: 'line', lineStyle: { color: muted, width: 1, type: 'dashed' } },
      // With one series the card's title has already named it, so the tooltip
      // carries the reading and not the name a third time. With several, the
      // name is the only thing telling the rows apart, so it stays.
      formatter: multiple ? undefined : (params: unknown) => {
        const point = (Array.isArray(params) ? params[0] : params) as
          { axisValueLabel?: string; value?: [unknown, number] } | undefined
        if (!point) return ''
        const reading = Array.isArray(point.value) ? point.value[1] : undefined
        // A break in the line stands for a span the source said nothing about,
        // so a pointer landing on one shows no card rather than a blank reading.
        if (typeof reading !== 'number' || !Number.isFinite(reading)) return ''
        const unit = props.series[0]?.unit
        const axisValue = Array.isArray(point.value) ? point.value[0] : point.axisValueLabel
        const at = [typeof axisValue === 'number' ? formatNumber(axisValue, locale.value) : axisValue, props.xUnit].filter(Boolean).join(' ')
        const value = [formatNumber(reading, locale.value), unit].filter((part) => part !== undefined && part !== '').join(' ')
        return `<span style="color:${muted}">${at}</span><br><strong>${value}</strong>`
      },
    },
    legend: multiple
      ? { data: props.series.map((item) => item.name), textStyle: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 12 }, top: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 3 }
      : { show: false },
    grid: { left: 12, right: xLabel ? 26 : 16, top: multiple ? 34 : (yLabel ? 24 : 12), bottom: xLabel ? 16 : 6, containLabel: true },
    xAxis: {
      type: props.xType,
      // The unit belongs to the axis, not to each of its ticks: it used to be
      // repeated on every one of them.
      name: xLabel,
      nameLocation: 'end',
      nameGap: 8,
      nameTextStyle: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 11, align: 'right', verticalAlign: 'top' },
      axisLabel: {
        color: muted,
        fontFamily: 'IBM Plex Sans',
        fontSize: 11,
        formatter: props.xType === 'value' ? (value: number) => formatNumber(value, locale.value) : undefined,
      },
      axisLine: { lineStyle: { color: line } },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      // The axis carrying the reading had no unit at all, so the only place to
      // learn it was the title or a tooltip.
      name: yLabel,
      nameLocation: 'end',
      nameGap: 9,
      nameTextStyle: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 11, align: 'left' },
      axisLabel: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 11, formatter: (value: number) => formatNumber(value, locale.value) },
      splitLine: { lineStyle: { color: line } },
    },
    dataZoom: [{ type: 'inside' }],
    series: props.series.map((item, index) => ({
      name: item.name,
      type: 'line',
      showSymbol: false,
      smooth: 0.22,
      smoothMonotone: props.xType === 'value' ? 'x' : undefined,
      connectNulls: false,
      data: item.data,
      tooltip: item.unit ? { valueFormatter: (value: unknown) => `${typeof value === 'number' ? formatNumber(value, locale.value) : value} ${item.unit}` } : undefined,
      lineStyle: { width: 2, color: palette[index % palette.length] },
      itemStyle: { color: palette[index % palette.length] },
      areaStyle: multiple ? undefined : { color: `${palette[0]}14` },
    })),
  }, true)
}
onMounted(() => {
  chart = echarts.init(element.value!)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value!)
  render()
})
watch(() => [props.series, props.xType, props.xUnit, locale.value], render, { deep: true })
watch(resolvedTheme, () => window.requestAnimationFrame(render))
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="element" :style="{ height: typeof height === 'number' ? `${height}px` : (height ?? '280px'), minHeight: 0 }" role="img" :aria-label="label || t('dashboards.chartLabel')" /></template>
