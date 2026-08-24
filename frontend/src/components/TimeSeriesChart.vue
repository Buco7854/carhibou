<script setup lang="ts">
import { LineChart } from 'echarts/charts'
import { DataZoomComponent, GridComponent, LegendComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { resolvedTheme } from '../theme'

const props = defineProps<{
  series: Array<{ name: string; unit?: string; data: Array<[string, number]> }>
  height?: number
}>()
const element = ref<HTMLDivElement>()
echarts.use([LineChart, DataZoomComponent, GridComponent, LegendComponent, TooltipComponent, CanvasRenderer])
let chart: echarts.EChartsType | undefined
let observer: ResizeObserver | undefined

function render() {
  const styles = getComputedStyle(document.documentElement)
  const muted = styles.getPropertyValue('--muted').trim()
  const panel = styles.getPropertyValue('--panel-2').trim()
  const line = styles.getPropertyValue('--line').trim()
  const text = styles.getPropertyValue('--text').trim()
  const petrol = styles.getPropertyValue('--petrol').trim()
  const signal = styles.getPropertyValue('--signal').trim()
  const rust = styles.getPropertyValue('--rust').trim()
  chart?.setOption({
    backgroundColor: 'transparent',
    animationDuration: 350,
    tooltip: { trigger: 'axis', backgroundColor: panel, borderColor: line, textStyle: { color: text, fontFamily: 'IBM Plex Mono' } },
    legend: { data: props.series.map((item) => item.name), textStyle: { color: muted, fontFamily: 'IBM Plex Mono', fontSize: 9 }, top: 0 },
    grid: { left: 20, right: 20, top: 45, bottom: 24, containLabel: true },
    xAxis: { type: 'time', axisLabel: { color: muted, fontFamily: 'IBM Plex Mono', fontSize: 9 }, axisLine: { lineStyle: { color: line } }, splitLine: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: muted, fontFamily: 'IBM Plex Mono', fontSize: 9 }, splitLine: { lineStyle: { color: line } } },
    dataZoom: [{ type: 'inside' }],
    series: props.series.map((item, index) => ({
      name: item.name,
      type: 'line',
      showSymbol: false,
      smooth: 0.12,
      data: item.data,
      lineStyle: { width: 2.1, color: [petrol, signal, rust, text][index % 4] },
      areaStyle: index === 0 ? { color: `${petrol}18` } : undefined,
    })),
  }, true)
}
onMounted(() => {
  chart = echarts.init(element.value!)
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value!)
  render()
})
watch(() => props.series, render, { deep: true })
watch(resolvedTheme, () => window.requestAnimationFrame(render))
onBeforeUnmount(() => { observer?.disconnect(); chart?.dispose() })
</script>

<template><div ref="element" :style="{ height: `${height ?? 280}px` }" aria-label="Telemetry chart" /></template>
