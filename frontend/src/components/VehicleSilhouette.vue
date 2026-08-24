<script setup lang="ts">
withDefaults(defineProps<{ color?: string }>(), { color: '#ff682d' })
</script>

<template>
  <svg class="vehicle-silhouette" viewBox="0 0 320 150" fill="none" aria-hidden="true">
    <ellipse cx="160" cy="132" rx="122" ry="6" fill="currentColor" opacity=".08" />
    <path d="M42 105V82c0-9 7-16 16-18l41-8 28-34c4-5 10-8 17-8h48c11 0 21 6 27 15l22 36 31 9c11 3 19 13 19 25v14H42v-8Z" fill="currentColor" opacity=".12" />
    <path d="M58 98V78l47-9 33-40c3-4 8-6 13-6h37c9 0 16 4 21 12l23 39 32 9c7 2 12 8 12 16v12H58V98Z" :stroke="color" stroke-width="3" stroke-linejoin="round" />
    <path d="M114 68 143 33h17v35h-46Zm54 0V33h18c6 0 11 3 14 8l16 27h-48Z" fill="currentColor" opacity=".1" :stroke="color" stroke-width="2" />
    <path d="M58 84h25m151-3h30M90 106h131M163 24v85" :stroke="color" stroke-width="2" stroke-linecap="round" opacity=".72" />
    <circle cx="96" cy="112" r="22" fill="var(--panel)" :stroke="color" stroke-width="3" /><circle cx="96" cy="112" r="9" fill="currentColor" opacity=".16" :stroke="color" stroke-width="2" />
    <circle cx="235" cy="112" r="22" fill="var(--panel)" :stroke="color" stroke-width="3" /><circle cx="235" cy="112" r="9" fill="currentColor" opacity=".16" :stroke="color" stroke-width="2" />
    <path d="M49 93h15v9H49m210-9h17v9h-17" :stroke="color" stroke-width="2" />
  </svg>
</template>

<style scoped>
.vehicle-silhouette{display:block;width:100%;height:auto;color:var(--text)}
</style>
