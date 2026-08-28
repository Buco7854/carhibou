<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, type CSSProperties } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps<{ label: string }>()
const root = ref<HTMLElement>()
const menu = ref<HTMLElement>()
const open = ref(false)
const menuStyle = ref<CSSProperties>({})

/**
 * The menu is teleported and positioned against the viewport.
 *
 * A row lives inside a panel that clips its own rounded corners, so a menu
 * absolutely positioned within the row was cut off at the card's edge. Escaping
 * the ancestor means there is no overflow left to be trapped by, at the cost of
 * having to place it here rather than in the layout.
 */
function place(): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  const edge = 8
  const width = 190
  const height = menu.value?.offsetHeight ?? 0
  const below = bounds.bottom + 4
  const above = bounds.top - height - 4
  const flip = height > 0 && below + height > window.innerHeight - edge && above > edge
  menuStyle.value = {
    top: `${flip ? above : below}px`,
    left: `${Math.max(edge, Math.min(bounds.right - width, window.innerWidth - width - edge))}px`,
    minWidth: `${width}px`,
  }
}

async function show(): Promise<void> {
  open.value = true
  await nextTick()
  place()
  // Measuring the menu needs it rendered, so the flip decision runs once more.
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
  if (!root.value?.contains(target) && !menu.value?.contains(target)) close()
}

document.addEventListener('pointerdown', outside, true)
onBeforeUnmount(() => {
  close()
  document.removeEventListener('pointerdown', outside, true)
})
</script>

<template>
  <div ref="root" class="row-menu" @keydown.esc="close">
    <button
      class="icon-button row-menu-button"
      type="button"
      :aria-label="label"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="toggle"
    >
      <AppIcon name="more" :size="16" />
    </button>
    <Teleport to="body">
      <!-- Clicking any item runs its own handler and then closes the menu, so no
           item has to remember to. -->
      <div v-if="open" ref="menu" class="row-menu-list" :style="menuStyle" role="menu" @click="close"><slot /></div>
    </Teleport>
  </div>
</template>

<style scoped>
.row-menu{position:relative;display:flex;align-items:center}
.row-menu-button[aria-expanded="true"]{color:var(--text);background:var(--panel-2)}
</style>

<style>
.row-menu-list{position:fixed;z-index:2000;width:max-content;padding:4px;background:var(--panel);border-radius:var(--radius-lg);box-shadow:0 0 0 1px var(--line),var(--shadow)}
.row-menu-list button{width:100%;display:flex;align-items:center;gap:9px;padding:7px 9px;color:var(--text);background:transparent;border:0;border-radius:var(--radius);font-size:var(--font-body);text-align:left;white-space:nowrap;cursor:pointer;transition:background-color .12s}
.row-menu-list button:hover{background:var(--panel-2)}
.row-menu-list button.danger{color:var(--danger)}
.row-menu-list button:disabled{opacity:.45;cursor:not-allowed}
</style>
