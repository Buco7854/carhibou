<script setup lang="ts">
import { computed } from 'vue'
import { resolvedTheme } from '../theme'

withDefaults(defineProps<{ size?: number }>(), { size: 24 })
// The mark is transparent and self-colored, so a dark surface would swallow its
// navy ink. The dark variant lightens that one ink and nothing else; following
// the resolved theme rather than the mode makes "auto" track the system too.
const source = computed(() => resolvedTheme.value === 'dark' ? '/carhibou-mark-dark.svg' : '/carhibou-mark.svg')
</script>

<template>
  <img
    class="brand-symbol"
    :src="source"
    alt=""
    aria-hidden="true"
    :style="{ width: `${size}px`, height: `${size}px` }"
  />
</template>

<style scoped>
.brand-symbol{display:block;flex:none}
</style>
