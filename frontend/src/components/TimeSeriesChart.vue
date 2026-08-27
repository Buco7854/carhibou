<script setup lang="ts">
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolvedTheme } from '../theme'

const props = withDefaults(defineProps<{
  series: Array<{ name: string; unit?: string; data: Array<[string | number, number]> }>
  height?: number | string
  xType?: 'time' | 'value'
  xUnit?: string
}>(), { xType: 'time', xUnit: '' })
const element = ref<HTMLDivElement>()
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
  chart?.setOption({
    backgroundColor: 'transparent',
    animationDuration: 350,
    tooltip: {
      trigger: 'axis',
      backgroundColor: panel,
      borderColor: line,
      textStyle: { color: text, fontFamily: 'IBM Plex Sans', fontSize: 12 },
      axisPointer: { type: 'line', lineStyle: { color: muted, width: 1, type: 'dashed' } },
    },
    legend: multiple
      ? { data: props.series.map((item) => item.name), textStyle: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 12 }, top: 0, icon: 'roundRect', itemWidth: 10, itemHeight: 3 }
      : { show: false },
    grid: { left: 12, right: 16, top: multiple ? 34 : 12, bottom: 6, containLabel: true },
    xAxis: {
      type: props.xType,
      axisLabel: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 11, formatter: props.xUnit ? `{value} ${props.xUnit}` : undefined },
      axisLine: { lineStyle: { color: line } },
      axisTick: { show: false },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: muted, fontFamily: 'IBM Plex Sans', fontSize: 11 },
      splitLine: { lineStyle: { color: line } },
    },
    dataZoom: [{ type: 'inside' }],
    series: props.series.map((item, index) => ({
      name: item.name,
      type: 'line',
      showSymbol: false,
      smooth: 0.22,
      data: item.data,
      tooltip: item.unit ? { valueFormatter: (value: unknown) => `${value} ${item.unit}` } : undefined,
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
watch(() => [props.series, props.xType, props.xUnit], render, { deep: true })
watch(resolvedTheme, () => window.requestAnimationFrame(render))
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="element" :style="{ height: typeof height === 'number' ? `${height}px` : (height ?? '280px'), minHeight: 0 }" role="img" aria-label="Telemetry chart" /></template>
