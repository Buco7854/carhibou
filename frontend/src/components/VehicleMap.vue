<script setup lang="ts">
import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { Position } from '../api/types'

const props = defineProps<{
  position: Position | null | undefined
  route?: Array<[number, number]> | undefined
}>()
const element = ref<HTMLDivElement>()
let map: L.Map | undefined
let marker: L.CircleMarker | undefined
let polyline: L.Polyline | undefined

function update() {
  if (!map) return
  if (props.route?.length) {
    polyline?.remove()
    polyline = L.polyline(props.route, { color: '#65e0ad', weight: 4, opacity: 0.82 }).addTo(map)
    map.fitBounds(polyline.getBounds(), { padding: [28, 28], maxZoom: 15 })
  }
  if (props.position) {
    const point = L.latLng(props.position.latitude, props.position.longitude)
    marker?.remove()
    marker = L.circleMarker(point, { radius: 8, color: '#07110e', weight: 3, fillColor: '#65e0ad', fillOpacity: 1 }).addTo(map)
    if (!props.route?.length) map.setView(point, 14)
  }
}

onMounted(() => {
  map = L.map(element.value!, { zoomControl: false, attributionControl: true }).setView([48.8566, 2.3522], 11)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '© OpenStreetMap',
    maxZoom: 19,
  }).addTo(map)
  L.control.zoom({ position: 'bottomright' }).addTo(map)
  update()
})
watch(() => [props.position, props.route], update, { deep: true })
onBeforeUnmount(() => map?.remove())
</script>

<template><div ref="element" class="vehicle-map" aria-label="Vehicle map" /></template>

<style scoped>
.vehicle-map { width:100%; min-height:300px; height:100%; background:var(--panel); }
:global([data-theme="dark"]) :deep(.leaflet-tile-pane) { filter: brightness(.7) saturate(.55) hue-rotate(90deg); }
:deep(.leaflet-control-attribution) { color:var(--muted); background:color-mix(in srgb,var(--panel) 85%,transparent); font-size:9px; }
:deep(.leaflet-control-attribution a) { color:var(--accent); }
</style>
