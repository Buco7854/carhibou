<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, type CSSProperties } from 'vue'
import { useI18n } from 'vue-i18n'
import type { ColumnChoice, ColumnPreference } from '../columnPreference'
import { layerHost } from '../layerHost'
import AppIcon from './AppIcon.vue'

const props = defineProps<{ columns: ColumnChoice[]; preference: ColumnPreference; hiddenCount: number }>()
const emit = defineEmits<{ toggle: [key: string]; move: [key: string, direction: -1 | 1]; reset: [] }>()
const { t } = useI18n()

const open = ref(false)
const host = computed(layerHost)
const tools = ref<HTMLElement>()
const menu = ref<HTMLElement>()
const style = ref<CSSProperties>({})

/**
 * Anchored to its button but drawn against the viewport, because the panel it
 * sits in clips its own overflow to keep the table's corners.
 */
function place(): void {
  const bounds = tools.value?.getBoundingClientRect()
  if (!bounds) return
  const edge = 8
  const width = 260
  const height = menu.value?.offsetHeight ?? 0
  const below = bounds.bottom + 6
  const flip = height > 0 && below + height > window.innerHeight - edge && bounds.top - height - 6 > edge
  style.value = {
    top: `${flip ? bounds.top - height - 6 : below}px`,
    left: `${Math.min(Math.max(edge, bounds.right - width), window.innerWidth - width - edge)}px`,
  }
}

async function toggleOpen(): Promise<void> {
  if (open.value) return close()
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

function outside(event: PointerEvent): void {
  const target = event.target as Node
  if (!tools.value?.contains(target) && !menu.value?.contains(target)) close()
}

document.addEventListener('pointerdown', outside, true)
onBeforeUnmount(() => {
  close()
  document.removeEventListener('pointerdown', outside, true)
})
</script>

<template>
  <div ref="tools" class="column-picker" @keydown.esc="close">
    <button class="button secondary" type="button" aria-haspopup="true" :aria-expanded="open" @click="toggleOpen">
      <AppIcon name="columns" :size="15" />
      {{ t('history.columnsButton') }}<span v-if="props.hiddenCount"> · {{ props.hiddenCount }}</span>
    </button>
    <Teleport :to="host">
      <div v-if="open" ref="menu" class="columns-menu panel" :style="style">
        <div class="columns-menu-head">
          <strong>{{ t('history.columnsTitle') }}</strong>
          <button class="link-button" type="button" @click="emit('reset')">{{ t('history.reset') }}</button>
        </div>
        <ul>
          <li v-for="(column, index) in props.columns" :key="column.key">
            <label :title="column.hint">
              <input type="checkbox" :checked="!props.preference.hidden.includes(column.key)" @change="emit('toggle', column.key)" />
              <span>{{ column.label }}</span>
            </label>
            <button class="icon-button" type="button" :disabled="index === 0" :aria-label="t('history.moveUp', { name: column.label })" @click="emit('move', column.key, -1)"><AppIcon name="chevron-up" :size="14" /></button>
            <button class="icon-button" type="button" :disabled="index === props.columns.length - 1" :aria-label="t('history.moveDown', { name: column.label })" @click="emit('move', column.key, 1)"><AppIcon name="chevron-down" :size="14" /></button>
          </li>
        </ul>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.column-picker{display:inline-flex}
</style>

<style>
.columns-menu{position:fixed;z-index:1400;width:260px;max-height:340px;display:flex;flex-direction:column;overflow:hidden;box-shadow:var(--shadow)}
.columns-menu-head{display:flex;align-items:baseline;justify-content:space-between;gap:12px;padding:10px 12px;border-bottom:1px solid var(--line)}
.columns-menu-head strong{font-size:var(--font-caption);font-weight:600}
.columns-menu ul{list-style:none;margin:0;padding:4px;min-height:0;overflow-y:auto}
.columns-menu li{display:grid;grid-template-columns:minmax(0,1fr) 24px 24px;align-items:center;gap:2px;padding:1px 4px}
.columns-menu label{min-width:0;display:flex;align-items:center;gap:8px;padding:5px 4px;font-size:var(--font-caption);cursor:pointer}
.columns-menu label span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.columns-menu input{width:13px;height:13px;flex:none;accent-color:var(--accent)}
.columns-menu .icon-button{width:24px;height:24px}
</style>
