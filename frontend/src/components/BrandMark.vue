<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 24 })
</script>

<template>
  <span class="brand-symbol" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <!-- An owl in the mark's existing language: strokes and filled dots. Ear
         tufts, two large eyes, a beak dot and a chest arc; eyes dominate so it
         still reads at 16px. -->
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M7 6.5 10.5 10M25 6.5 21.5 10" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
      <circle cx="10.5" cy="15" r="4" stroke="currentColor" stroke-width="3" />
      <circle cx="21.5" cy="15" r="4" stroke="currentColor" stroke-width="3" />
      <circle cx="16" cy="20.5" r="1.8" fill="currentColor" />
      <path d="M10 25.5c3.5 2.5 8.5 2.5 12 0" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
    </svg>
  </span>
</template>

<style scoped>
.brand-symbol{display:grid;place-items:center;flex:none;color:var(--primary-contrast);background:var(--primary);border-radius:5px}
.brand-symbol svg{width:78%;height:78%}
</style>
