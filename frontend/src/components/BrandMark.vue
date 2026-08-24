<script setup lang="ts">
withDefaults(defineProps<{ size?: number }>(), { size: 38 })
</script>

<template>
  <span class="brand-symbol" :style="{ width: `${size}px`, height: `${size}px` }" aria-hidden="true">
    <svg viewBox="0 0 32 32" fill="none">
      <path d="M8 8h6v7h-3a3 3 0 0 1-3-3V8Zm10 0h6v13h-6V8Z" fill="currentColor" />
      <path d="M11 17h5.5l4.8 7H16l-5-5.3V17Z" fill="currentColor" opacity=".88" />
    </svg>
  </span>
</template>

<style scoped>
.brand-symbol{display:grid;place-items:center;border-radius:11px;color:white;background:linear-gradient(145deg,#ff985e,#ff5d20);box-shadow:0 8px 22px rgba(255,99,38,.24)}
.brand-symbol svg{width:68%;height:68%}
</style>
