<script setup lang="ts">
withDefaults(defineProps<{ name: string; size?: number }>(), { size: 20 })
</script>

<template>
  <svg class="app-icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" aria-hidden="true">
    <template v-if="name === 'dashboard'">
      <rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="11" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="18" width="7" height="3" rx="1.5" />
    </template>
    <template v-else-if="name === 'vehicle'">
      <path d="M4 15.5V10l2-5h10.5l3.5 5v5.5" /><path d="M6.5 10h11L15.8 6.8H8L6.5 10Z" /><circle cx="7" cy="16.5" r="2" /><circle cx="17" cy="16.5" r="2" /><path d="M9 16.5h6M3 13h2m14 0h2" />
    </template>
    <template v-else-if="name === 'grid'">
      <rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16m6-16v16M3 10h18" />
    </template>
    <template v-else-if="name === 'hooks'">
      <path d="M8 3v5a4 4 0 0 0 8 0V3M6 3h4m4 0h4M12 12v4a4 4 0 0 0 4 4h2" /><circle cx="19" cy="20" r="2" />
    </template>
    <template v-else-if="name === 'devices'">
      <rect x="7" y="3" width="10" height="18" rx="2.5" /><path d="M10 6h4m-3 12h2" />
    </template>
    <template v-else-if="name === 'settings'">
      <circle cx="12" cy="12" r="3" /><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1-2.8 2.8-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21h-4v-.1a1.7 1.7 0 0 0-1-1.5 1.7 1.7 0 0 0-1.9.3l-.1.1L4.2 17l.1-.1a1.7 1.7 0 0 0 .3-1.9A1.7 1.7 0 0 0 3.1 14H3v-4h.1a1.7 1.7 0 0 0 1.5-1 1.7 1.7 0 0 0-.3-1.9L4.2 7 7 4.2l.1.1A1.7 1.7 0 0 0 9 4.6a1.7 1.7 0 0 0 1-1.5V3h4v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1L19.8 7l-.1.1a1.7 1.7 0 0 0-.3 1.9 1.7 1.7 0 0 0 1.5 1h.1v4h-.1a1.7 1.7 0 0 0-1.5 1Z" />
    </template>
    <template v-else-if="name === 'search'">
      <circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 4.5 4.5" />
    </template>
    <template v-else-if="name === 'plus'">
      <path d="M12 5v14M5 12h14" />
    </template>
    <template v-else-if="name === 'signout'">
      <path d="M10 4H5a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h5m5-4 4-4-4-4m4 4H8" />
    </template>
    <template v-else-if="name === 'location'">
      <path d="M20 10c0 5-8 11-8 11S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" />
    </template>
    <template v-else-if="name === 'battery'">
      <rect x="3" y="7" width="17" height="10" rx="2" /><path d="M22 10v4M6 10v4m3-4v4m3-4v4" />
    </template>
    <template v-else-if="name === 'speed'">
      <path d="M4.2 17.5a9 9 0 1 1 15.6 0" /><path d="m12 13 4-4" /><circle cx="12" cy="13" r="1.5" />
    </template>
    <template v-else-if="name === 'signal'">
      <path d="M5 19v-3m4 3v-6m4 6V9m4 10V5" />
    </template>
    <template v-else-if="name === 'charging'">
      <path d="m13 2-7 11h6l-1 9 7-12h-6l1-8Z" />
    </template>
    <template v-else-if="name === 'history'">
      <path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5m4-1v5l3 2" />
    </template>
    <template v-else-if="name === 'camera'">
      <path d="M4 7h3l1.5-2h7L17 7h3a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V9a2 2 0 0 1 2-2Z" /><circle cx="12" cy="13" r="4" />
    </template>
    <template v-else-if="name === 'image-missing'">
      <rect x="3" y="4" width="18" height="16" rx="2.5" />
      <circle cx="8.5" cy="9" r="1.5" />
      <path d="m4 17 4.5-4.5 3.5 3.5 2-2 6 6M4 4l16 16" />
    </template>
    <template v-else-if="name === 'trash'">
      <path d="M4 7h16m-10-3h4l1 3M7 7l1 14h8l1-14M10 11v6m4-6v6" />
    </template>
    <template v-else-if="name === 'theme'">
      <circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M2 12h2m16 0h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </template>
    <template v-else>
      <circle cx="12" cy="12" r="8" /><circle cx="12" cy="12" r="2" />
    </template>
  </svg>
</template>

<style scoped>
.app-icon{display:block;flex:none;stroke:currentColor;stroke-width:1.65;stroke-linecap:round;stroke-linejoin:round}
</style>
