<script setup lang="ts">
import L from 'leaflet'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Position } from '../api/types'

const props = defineProps<{
  position: Position | null | undefined
  route?: Array<[number, number]> | undefined
}>()
const element = ref<HTMLDivElement>()
const { t } = useI18n()
let map: L.Map | undefined
let marker: L.CircleMarker | undefined
let polyline: L.Polyline | undefined

function update() {
  if (!map) return
  if (props.route?.length) {
    polyline?.remove()
    polyline = L.polyline(props.route, { color: '#ff6428', weight: 4, opacity: 0.88 }).addTo(map)
    map.fitBounds(polyline.getBounds(), { padding: [28, 28], maxZoom: 15 })
  }
  if (props.position) {
    const point = L.latLng(props.position.latitude, props.position.longitude)
    marker?.remove()
    marker = L.circleMarker(point, { radius: 8, color: '#ffffff', weight: 3, fillColor: '#ff6428', fillOpacity: 1 }).addTo(map)
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

<template><div ref="element" class="vehicle-map" :aria-label="t('history.route')" /></template>

<style scoped>
.vehicle-map { width:100%; min-height:300px; height:100%; background:var(--panel); }
:global([data-theme="dark"]) :deep(.leaflet-tile-pane) { filter: brightness(.62) saturate(.28) contrast(1.08); }
:deep(.leaflet-control-attribution) { color:var(--muted); background:color-mix(in srgb,var(--panel) 85%,transparent); font-size:9px; }
:deep(.leaflet-control-attribution a) { color:var(--accent); }
</style>
