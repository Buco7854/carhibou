<script lang="ts">
let openModalCount = 0
</script>

<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import AppIcon from './AppIcon.vue'

const props = withDefaults(defineProps<{ open: boolean; title: string; wide?: boolean; inactive?: boolean }>(), { wide: false, inactive: false })
const emit = defineEmits<{ close: [] }>()
const dialog = ref<HTMLElement>()
let previousFocus: HTMLElement | null = null
let ownsBodyLock = false

function lockBody(): void {
  if (ownsBodyLock) return
  ownsBodyLock = true
  openModalCount += 1
  document.body.classList.add('modal-open')
}

function unlockBody(): void {
  if (!ownsBodyLock) return
  ownsBodyLock = false
  openModalCount = Math.max(0, openModalCount - 1)
  if (!openModalCount) document.body.classList.remove('modal-open')
}

function close(): void { emit('close') }
function onKeydown(event: KeyboardEvent): void { if (props.open && event.key === 'Escape') close() }

watch(() => props.open, async (value) => {
  if (value) {
    previousFocus = document.activeElement as HTMLElement | null
    lockBody()
    await nextTick()
    const autofocus = dialog.value?.querySelector<HTMLElement>('[autofocus]')
    const firstControl = dialog.value?.querySelector<HTMLElement>('input, textarea, button, [tabindex="0"]')
    ;(autofocus ?? firstControl)?.focus()
  } else {
    unlockBody()
    previousFocus?.focus()
  }
}, { immediate: true })

document.addEventListener('keydown', onKeydown)
onBeforeUnmount(() => {
  document.removeEventListener('keydown', onKeydown)
  unlockBody()
})
</script>

<template>
  <Teleport to="body">
    <div v-if="open" class="app-modal-backdrop" @pointerdown.self="close">
      <section ref="dialog" :class="['app-modal panel', { wide, inactive }]" role="dialog" :aria-modal="!inactive" :aria-hidden="inactive || undefined" :inert="inactive || undefined" :aria-label="title">
        <header class="app-modal-heading">
          <h2>{{ title }}</h2>
          <button class="icon-button" type="button" :aria-label="$t('common.close')" @click="close"><AppIcon name="close" :size="16" /></button>
        </header>
        <div class="app-modal-content"><slot /></div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.app-modal-backdrop{position:fixed;inset:0;z-index:3000;display:grid;place-items:center;padding:20px;background:rgba(10,14,10,.5)}
.app-modal{width:min(100%,500px);max-height:calc(100vh - 40px);max-height:calc(100dvh - 40px);display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--shadow)}
.app-modal.wide{width:min(100%,900px)}
.app-modal.inactive{pointer-events:none}
.app-modal-heading{min-height:50px;display:flex;align-items:center;justify-content:space-between;gap:16px;padding:12px 14px 12px 18px;border-bottom:1px solid var(--line)}
.app-modal-heading h2{margin:0;font-size:15px;font-weight:600}
.app-modal-content{min-height:0;overflow-y:auto;overscroll-behavior:contain;padding:18px;scroll-padding-top:18px}
.app-modal-content :deep(.field){scroll-margin-top:18px}
@media(max-width:620px){
  .app-modal-backdrop{align-items:end;padding:0}
  /* A bottom sheet is anchored to the backdrop bottom, so any height it takes
     beyond the visible viewport is spent above the top edge, hiding the
     heading and the first field label. 100vh is the large viewport on
     mobile: it excludes the URL bar and does not shrink for the keyboard,
     so it overshoots exactly when the keyboard opens on the autofocused
     name field. 100dvh tracks what the reader can actually see. */
  .app-modal,.app-modal.wide{width:100%;max-height:calc(100vh - 16px);max-height:calc(100dvh - 16px);border-radius:var(--radius-lg) var(--radius-lg) 0 0}
  .app-modal-content{padding:16px}
}
</style>

<style>
body.modal-open{overflow:hidden}
</style>
