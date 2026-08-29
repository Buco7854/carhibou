<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, type CSSProperties, useId } from 'vue'
import { layerHost } from '../layerHost'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ label: string }>()

/**
 * One sentence about a thing, available to everyone.
 *
 * A hover tooltip is unreachable by keyboard and unreliable on touch, so this is
 * a disclosure: a real button that toggles a real region, labelled by what it
 * explains. It teleports so a table cell or a panel with hidden overflow cannot
 * clip it, which means it is positioned here rather than by the layout.
 */
const root = ref<HTMLElement>()
const bubble = ref<HTMLElement>()
const open = ref(false)
const host = computed(layerHost)
const style = ref<CSSProperties>({})
const helpId = `help-${useId()}`


function place(): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  const edge = 8
  const width = Math.min(300, window.innerWidth - edge * 2)
  const height = bubble.value?.offsetHeight ?? 0
  const below = bounds.bottom + 6
  const flip = height > 0 && below + height > window.innerHeight - edge
  style.value = {
    top: `${flip ? Math.max(edge, bounds.top - height - 6) : below}px`,
    left: `${Math.min(Math.max(edge, bounds.left - 8), window.innerWidth - width - edge)}px`,
    width: `${width}px`,
  }
}

async function show(): Promise<void> {
  open.value = true
  await nextTick()
  place()
  place()
  window.addEventListener('resize', place)
  window.addEventListener('scroll', place, true)
}

function close(): void {
  open.value = false
  window.removeEventListener('resize', place)
  window.removeEventListener('scroll', place, true)
}

function toggle(): void { if (open.value) close(); else void show() }

function outside(event: PointerEvent): void {
  const target = event.target as Node
  if (!root.value?.contains(target) && !bubble.value?.contains(target)) close()
}

document.addEventListener('pointerdown', outside, true)
onBeforeUnmount(() => {
  close()
  document.removeEventListener('pointerdown', outside, true)
})
</script>

<template>
  <span ref="root" class="app-help" @keydown.esc="close">
    <button
      class="app-help-button"
      type="button"
      :aria-label="props.label"
      :aria-expanded="open"
      :aria-controls="helpId"
      @click="toggle"
    >
      <AppIcon name="info" :size="14" />
    </button>
    <Teleport :to="host">
      <span v-if="open" :id="helpId" ref="bubble" class="app-help-bubble" role="tooltip" :style="style"><slot /></span>
    </Teleport>
  </span>
</template>

<style scoped>
.app-help{display:inline-flex;vertical-align:middle}
.app-help-button{display:inline-grid;place-items:center;width:20px;height:20px;padding:0;color:var(--muted-2);background:transparent;border:0;border-radius:50%;cursor:pointer;transition:color .12s,background-color .12s}
.app-help-button:hover,.app-help-button[aria-expanded="true"]{color:var(--accent);background:var(--accent-soft)}
</style>

<style>
.app-help-bubble{position:fixed;z-index:2200;display:block;padding:10px 12px;color:var(--text);background:var(--panel);border-radius:var(--radius);box-shadow:0 0 0 1px var(--line),var(--shadow);font-size:var(--font-caption);font-weight:400;line-height:1.5;text-transform:none;letter-spacing:normal}
.app-help-bubble dl{display:grid;gap:5px;margin:0}
.app-help-bubble dt{color:var(--text);font-weight:600}
.app-help-bubble dd{margin:0 0 4px;color:var(--muted)}
.app-help-bubble dd:last-child{margin-bottom:0}
</style>
