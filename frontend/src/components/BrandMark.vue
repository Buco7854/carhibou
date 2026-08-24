<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 38 })
</script>

<template>
  <span class="brand-symbol" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M5 7h8v8H5V7Zm14 0h8v18h-8V7Z" fill="currentColor" />
      <path d="M5 20h8v5H5v-5Zm8-9h6v10h-6V11Z" fill="currentColor" opacity=".56" />
      <path d="M2 16h28" stroke="currentColor" stroke-width="1.5" opacity=".34" />
    </svg>
  </span>
</template>

<style scoped>
.brand-symbol{display:grid;place-items:center;color:var(--ink-inverse);background:var(--petrol);border:1px solid color-mix(in srgb,var(--petrol) 76%,white);border-radius:3px;box-shadow:7px 7px 0 var(--signal)}
.brand-symbol svg{width:70%;height:70%}
</style>
