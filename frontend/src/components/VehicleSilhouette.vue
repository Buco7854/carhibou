<script setup lang="ts">
withDefaults(defineProps<{ color?: string }>(), { color: '#315fcf' })
</script>

<template>
  <svg class="vehicle-silhouette" viewBox="0 0 360 150" fill="none" aria-hidden="true">
    <ellipse cx="181" cy="132" rx="145" ry="6" fill="currentColor" opacity=".07" />

    <path
      d="M29 106 33 88c2-8 7-12 16-15l43-8 30-31c7-7 15-10 27-10h68c14 0 23 4 31 14l23 29 47 10c10 2 16 8 18 18l2 12c1 6-3 10-10 10H39c-7 0-11-4-10-11Z"
      :fill="color"
      fill-opacity=".11"
    />
    <path
      d="M29 106 33 88c2-8 7-12 16-15l43-8 30-31c7-7 15-10 27-10h68c14 0 23 4 31 14l23 29 47 10c10 2 16 8 18 18l2 12c1 6-3 10-10 10H39c-7 0-11-4-10-11Z"
      :stroke="color"
      stroke-width="2.6"
      stroke-linejoin="round"
    />

    <path d="m101 65 29-29c4-4 10-6 17-6h20v35h-66Z" fill="var(--panel)" :stroke="color" stroke-width="1.8" />
    <path d="M175 30h40c9 0 15 3 21 10l20 25h-81V30Z" fill="var(--panel)" :stroke="color" stroke-width="1.8" />
    <path d="M168 29v88m88-50 14 50M97 66l-9 51M34 91h38m200-15h43" :stroke="color" stroke-width="1.6" stroke-linecap="round" opacity=".68" />
    <path d="M45 91h33m201-7h33M134 77h15m55 0h15M49 105h259" :stroke="color" stroke-width="2" stroke-linecap="round" opacity=".76" />

    <circle cx="100" cy="115" r="20" fill="var(--panel)" stroke="currentColor" stroke-width="5" />
    <circle cx="100" cy="115" r="9" :fill="color" fill-opacity=".15" :stroke="color" stroke-width="2" />
    <circle cx="282" cy="115" r="20" fill="var(--panel)" stroke="currentColor" stroke-width="5" />
    <circle cx="282" cy="115" r="9" :fill="color" fill-opacity=".15" :stroke="color" stroke-width="2" />

    <path d="M29 99h13c4 0 6 2 6 6v4H30m291-17h13l2 12h-18" :stroke="color" stroke-width="2" stroke-linejoin="round" />
    <path d="M328 83h-12v8h17M34 84h10v7H32" :fill="color" fill-opacity=".5" />
  </svg>
</template>

<style scoped>
.vehicle-silhouette{display:block;width:100%;height:auto;color:var(--text)}
</style>
