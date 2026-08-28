<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useAttrs, useId, useSlots, type CSSProperties, type VNode, type VNodeChild } from 'vue'
import AppIcon from './AppIcon.vue'

defineOptions({ inheritAttrs: false })

const props = defineProps<{
  id?: string
  compact?: boolean
  searchable?: boolean
  searchPlaceholder?: string
  noResultsText?: string
}>()

type SelectValue = string | number | null
interface SelectOption { value: SelectValue; label: string; disabled: boolean; group: string }

const model = defineModel<SelectValue>({ required: true })
const attrs = useAttrs()
const slots = useSlots()
const root = ref<HTMLElement>()
const menu = ref<HTMLElement>()
const searchInput = ref<HTMLInputElement>()
const open = ref(false)
const activeIndex = ref(0)
const query = ref('')
const menuStyle = ref<CSSProperties>({})
const listboxId = `select-${useId()}`
const disabled = computed(() => attrs.disabled !== undefined && attrs.disabled !== false)
const ariaLabel = computed(() => typeof attrs['aria-label'] === 'string' ? attrs['aria-label'] : undefined)
const ariaDescribedby = computed(() => typeof attrs['aria-describedby'] === 'string' ? attrs['aria-describedby'] : undefined)

function nodeText(value: unknown): string {
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  if (Array.isArray(value)) return value.map(nodeText).join('')
  if (value && typeof value === 'object' && '__v_isVNode' in value) return nodeText((value as unknown as VNode).children)
  return ''
}

const options = computed<SelectOption[]>(() => {
  const result: SelectOption[] = []
  function visit(node: VNodeChild, group: string): void {
    if (Array.isArray(node)) {
      node.forEach((child) => visit(child, group))
      return
    }
    if (!node || typeof node !== 'object' || !('__v_isVNode' in node)) return
    const vnode = node as VNode
    if (vnode.type === 'option') {
      const hasValue = Object.prototype.hasOwnProperty.call(vnode.props ?? {}, 'value')
      result.push({
        value: (hasValue ? vnode.props?.value : nodeText(vnode.children)) as SelectValue,
        label: nodeText(vnode.children).trim(),
        disabled: Boolean(vnode.props?.disabled),
        group,
      })
      return
    }
    const nested = vnode.type === 'optgroup' ? String(vnode.props?.label ?? '') : group
    if (Array.isArray(vnode.children)) vnode.children.forEach((child) => visit(child, nested))
  }
  slots.default?.().forEach((node) => visit(node, ''))
  return result
})

const selected = computed(() => options.value.find((option) => Object.is(option.value, model.value)) ?? options.value[0])
const normalizedQuery = computed(() => query.value.trim().normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase())
const visibleOptions = computed(() => options.value.flatMap((option, index) => {
  if (!normalizedQuery.value) return [{ option, index }]
  const label = option.label.normalize('NFD').replace(/\p{Diacritic}/gu, '').toLocaleLowerCase()
  return label.includes(normalizedQuery.value) ? [{ option, index }] : []
}))

/**
 * Visible options split into their groups, so a grouped list can be announced as
 * such. An ungrouped list stays one nameless run and renders exactly as before.
 */
const visibleGroups = computed(() => {
  const groups: Array<{ label: string; items: typeof visibleOptions.value }> = []
  for (const entry of visibleOptions.value) {
    const last = groups.at(-1)
    if (last && last.label === entry.option.group) last.items.push(entry)
    else groups.push({ label: entry.option.group, items: [entry] })
  }
  return groups
})

function positionMenu(): void {
  const bounds = root.value?.getBoundingClientRect()
  if (!bounds) return
  const edge = 8
  const desiredHeight = Math.min(320, options.value.length * 39 + 10 + (props.searchable ? 40 : 0))
  const roomBelow = window.innerHeight - bounds.bottom - edge
  const roomAbove = bounds.top - edge
  const above = roomBelow < Math.min(180, desiredHeight) && roomAbove > roomBelow
  const maxHeight = Math.max(96, Math.min(desiredHeight, above ? roomAbove - 6 : roomBelow - 6))
  const width = Math.min(Math.max(bounds.width, 120), window.innerWidth - edge * 2)
  menuStyle.value = {
    left: `${Math.min(Math.max(edge, bounds.left), window.innerWidth - width - edge)}px`,
    top: above ? `${Math.max(edge, bounds.top - maxHeight - 6)}px` : `${bounds.bottom + 6}px`,
    width: `${width}px`,
    maxHeight: `${maxHeight}px`,
  }
}

function selectableIndex(start: number, direction: 1 | -1): number {
  const indexes = visibleOptions.value
    .filter(({ option }) => !option.disabled)
    .map(({ index }) => index)
  if (!indexes.length) return -1
  const position = indexes.indexOf(start)
  if (position < 0) return direction === 1 ? indexes[0]! : indexes.at(-1)!
  return indexes[(position + direction + indexes.length) % indexes.length]!
}

async function show(): Promise<void> {
  if (disabled.value || !options.value.length) return
  const current = options.value.findIndex((option) => Object.is(option.value, model.value))
  query.value = ''
  activeIndex.value = current >= 0 ? current : selectableIndex(-1, 1)
  open.value = true
  await nextTick()
  positionMenu()
  searchInput.value?.focus()
  window.addEventListener('resize', positionMenu)
  window.addEventListener('scroll', positionMenu, true)
}

function hide(): void {
  open.value = false
  query.value = ''
  window.removeEventListener('resize', positionMenu)
  window.removeEventListener('scroll', positionMenu, true)
}

function toggle(): void { if (open.value) hide(); else void show() }

function choose(index: number): void {
  const option = options.value[index]
  if (!option || option.disabled) return
  model.value = option.value
  activeIndex.value = index
  hide()
  root.value?.querySelector<HTMLButtonElement>('.app-select-trigger')?.focus()
}

function onKeydown(event: KeyboardEvent): void {
  if (disabled.value) return
  if (event.key === 'Escape') {
    if (open.value) { event.preventDefault(); hide() }
    return
  }
  if (event.key === 'Tab') { hide(); return }
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    if (open.value) choose(activeIndex.value)
    else void show()
    return
  }
  if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    if (!open.value) void show()
    else activeIndex.value = selectableIndex(activeIndex.value, event.key === 'ArrowDown' ? 1 : -1)
    return
  }
  if (open.value && (event.key === 'Home' || event.key === 'End')) {
    event.preventDefault()
    activeIndex.value = event.key === 'Home' ? selectableIndex(-1, 1) : selectableIndex(0, -1)
  }
}

function onSearchKeydown(event: KeyboardEvent): void {
  if (event.key === 'Escape') {
    event.preventDefault()
    hide()
    root.value?.querySelector<HTMLButtonElement>('.app-select-trigger')?.focus()
  } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
    event.preventDefault()
    activeIndex.value = selectableIndex(activeIndex.value, event.key === 'ArrowDown' ? 1 : -1)
  } else if (event.key === 'Enter' && activeIndex.value >= 0) {
    event.preventDefault()
    choose(activeIndex.value)
  }
}

function filterOptions(): void {
  activeIndex.value = selectableIndex(-1, 1)
}

function outside(event: PointerEvent): void {
  const target = event.target as Node
  if (!root.value?.contains(target) && !menu.value?.contains(target)) hide()
}

document.addEventListener('pointerdown', outside, true)
onBeforeUnmount(() => {
  hide()
  document.removeEventListener('pointerdown', outside, true)
})
</script>

<template>
  <span ref="root" :class="['app-select', { compact, open }, attrs.class]">
    <button
      :id="props.id"
      class="app-select-trigger"
      type="button"
      role="combobox"
      aria-haspopup="listbox"
      :aria-expanded="open"
      :aria-controls="listboxId"
      :aria-activedescendant="open && activeIndex >= 0 ? `${listboxId}-${activeIndex}` : undefined"
      :aria-label="ariaLabel"
      :aria-describedby="ariaDescribedby"
      :disabled="disabled"
      @click="toggle"
      @keydown="onKeydown"
    >
      <span>{{ selected?.label }}</span>
      <AppIcon class="app-select-arrow" name="chevron-down" :size="15" />
    </button>
    <Teleport to="body">
      <div v-if="open" ref="menu" class="app-select-menu" :style="menuStyle">
        <label v-if="searchable" class="app-select-search">
          <AppIcon name="search" :size="15" />
          <input ref="searchInput" v-model="query" type="search" :placeholder="searchPlaceholder" :aria-label="searchPlaceholder" @input="filterOptions" @keydown="onSearchKeydown" />
        </label>
        <div :id="listboxId" class="app-select-options" role="listbox">
          <template v-for="group in visibleGroups" :key="group.label">
            <div v-if="group.label" role="group" :aria-label="group.label">
              <p class="app-select-group">{{ group.label }}</p>
              <button
                v-for="{ option, index } in group.items"
                :id="`${listboxId}-${index}`"
                :key="`${String(option.value)}-${index}`"
                type="button"
                role="option"
                :aria-selected="Object.is(option.value, model)"
                :class="{ active:index===activeIndex, selected:Object.is(option.value, model) }"
                :disabled="option.disabled"
                @pointerdown.prevent
                @mouseenter="activeIndex=index"
                @click="choose(index)"
              >
                <span>{{ option.label }}</span><AppIcon v-if="Object.is(option.value, model)" name="check" :size="15" />
              </button>
            </div>
            <button
              v-for="{ option, index } in (group.label ? [] : group.items)"
              :id="`${listboxId}-${index}`"
              :key="`${String(option.value)}-${index}`"
              type="button"
              role="option"
              :aria-selected="Object.is(option.value, model)"
              :class="{ active:index===activeIndex, selected:Object.is(option.value, model) }"
              :disabled="option.disabled"
              @pointerdown.prevent
              @mouseenter="activeIndex=index"
              @click="choose(index)"
            >
              <span>{{ option.label }}</span><AppIcon v-if="Object.is(option.value, model)" name="check" :size="15" />
            </button>
          </template>
          <p v-if="!visibleOptions.length" class="app-select-no-results">{{ noResultsText }}</p>
        </div>
      </div>
    </Teleport>
  </span>
</template>

<style scoped>
.app-select{position:relative;min-width:0;display:block}
.app-select-trigger{
  width:100%;min-height:34px;display:grid;grid-template-columns:minmax(0,1fr) 15px;align-items:center;gap:8px;
  padding:6px 8px 6px 10px;color:var(--text);background:var(--input);
  border:1px solid var(--line-strong);border-radius:var(--radius);outline:none;
  text-align:left;font-size:13px;cursor:pointer;transition:border-color .12s,box-shadow .12s;
}
.app-select-trigger>span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.app-select-trigger:hover{border-color:var(--muted-2)}
/* Focus and open are the same edge, drawn once. The border takes the accent and a
   1px spread thickens it to 2px, so there is a single ring in a single colour
   where a saturated border inside a pale halo used to read as two. */
.app-select-trigger:focus-visible,.app-select.open .app-select-trigger{border-color:var(--accent);box-shadow:var(--focus-ring)}
.app-select-arrow{justify-self:end;color:var(--muted);transition:transform .12s,color .12s}
.app-select.open .app-select-arrow{color:var(--accent);transform:rotate(180deg)}
.app-select.compact{width:max-content}
.app-select.compact .app-select-trigger{min-width:52px;min-height:30px;padding:4px 6px 4px 9px;background:transparent;border-color:transparent;font-size:12px}
.app-select.compact .app-select-trigger:hover{border-color:var(--line-strong)}
.app-select-trigger:disabled{opacity:.5;cursor:not-allowed}
</style>

<style>
.app-select-menu{position:fixed;z-index:5000;min-height:0;display:flex;flex-direction:column;overflow:hidden;padding:4px;background:var(--panel);border-radius:var(--radius-lg);box-shadow:0 0 0 1px var(--line),var(--shadow)}
.app-select-options{min-height:0;overflow:auto}
.app-select-menu button{width:100%;min-height:32px;display:grid;grid-template-columns:minmax(0,1fr) 15px;align-items:center;gap:8px;padding:6px 8px;color:var(--text);background:transparent;border:0;border-radius:var(--radius);text-align:left;font-size:13px;cursor:pointer}
.app-select-menu button span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.app-select-menu button:hover,.app-select-menu button.active{background:var(--panel-2)}
.app-select-menu button.selected{font-weight:500}
.app-select-menu button.selected{color:var(--accent)}
.app-select-menu button.selected .app-icon{color:var(--accent)}
.app-select-menu button:disabled{opacity:.4;cursor:not-allowed}
/* A boxed field inside a bordered menu is a frame inside a frame, so the search
   is a flush header the hairline separates instead of a control of its own. */
.app-select-search{height:36px;display:grid;grid-template-columns:15px minmax(0,1fr);align-items:center;gap:8px;margin:-4px -4px 4px;padding:0 11px;color:var(--muted-2);border-bottom:1px solid var(--line)}
.app-select-search:focus-within{color:var(--accent)}
.app-select-search input{min-width:0;width:100%;padding:0;color:var(--text);background:transparent;border:0;outline:0;font:inherit;font-size:13px}
.app-select-search input::placeholder{color:var(--muted-2)}
.app-select-group{margin:6px 8px 3px;color:var(--muted);font-size:var(--font-caption);font-weight:500}
.app-select-no-results{margin:0;padding:12px 8px;color:var(--muted);font-size:13px;text-align:center}
</style>
