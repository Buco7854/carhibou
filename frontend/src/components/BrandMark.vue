<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>

<template>
  <span class="brand-symbol" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M7.5 8.5 16 23.5 24.5 8.5" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" />
      <circle cx="7.5" cy="8.5" r="2.5" fill="currentColor" />
      <circle cx="16" cy="23.5" r="2.5" fill="currentColor" />
      <circle cx="24.5" cy="8.5" r="2.5" fill="currentColor" />
    </svg>
  </span>
</template>

<style scoped>
.brand-symbol{display:grid;place-items:center;flex:none;color:var(--primary-contrast);background:var(--primary);border-radius:5px}
.brand-symbol svg{width:74%;height:74%}
</style>
