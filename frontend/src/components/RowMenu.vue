<script setup lang="ts">
import { onBeforeUnmount, ref } from 'vue'
import AppIcon from './AppIcon.vue'

defineProps<{ label: string }>()
const root = ref<HTMLElement>()
const open = ref(false)

function close(): void { open.value = false }
function outside(event: PointerEvent): void {
  if (!root.value?.contains(event.target as Node)) close()
}

document.addEventListener('pointerdown', outside, true)
onBeforeUnmount(() => document.removeEventListener('pointerdown', outside, true))
</script>

<template>
  <div ref="root" class="row-menu" @keydown.esc="close">
    <button
      class="icon-button row-menu-button"
      type="button"
      :aria-label="label"
      aria-haspopup="menu"
      :aria-expanded="open"
      @click="open = !open"
    >
      <AppIcon name="more" :size="16" />
    </button>
    <!-- Clicking any item runs its own handler and then closes the menu, so no
         item has to remember to. -->
    <div v-if="open" class="row-menu-list panel" role="menu" @click="close"><slot /></div>
  </div>
</template>

<style scoped>
.row-menu{position:relative;display:flex;align-items:center}
.row-menu-button[aria-expanded="true"]{color:var(--text);background:var(--panel-2)}
.row-menu-list{position:absolute;z-index:1400;top:32px;right:0;width:max-content;min-width:172px;padding:4px;box-shadow:var(--shadow)}
.row-menu-list :slotted(button){width:100%;display:flex;align-items:center;gap:9px;padding:7px 9px;color:var(--text);background:transparent;border:0;border-radius:var(--radius);font-size:var(--font-body);text-align:left;white-space:nowrap;cursor:pointer;transition:background-color .12s}
.row-menu-list :slotted(button:hover){background:var(--panel-2)}
.row-menu-list :slotted(button.danger){color:var(--danger)}
.row-menu-list :slotted(button:disabled){opacity:.45;cursor:not-allowed}
</style>
