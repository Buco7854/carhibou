<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Circle } from 'lucide-vue-next'
import { ICONS } from './icons'

const props = withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })

const icon = computed<Component>(() => ICONS[props.name] ?? Circle)
</script>

<template>
  <component :is="icon" class="app-icon" :size="size" aria-hidden="true" />
</template>

<style scoped>
/* The library draws at stroke-width 2, which is heavy beside 12 and 13px text.
   Setting it here rather than per icon keeps one weight for the whole set, and
   CSS wins over the attribute the component renders. */
.app-icon{display:block;flex:none;stroke-width:1.75}
</style>
