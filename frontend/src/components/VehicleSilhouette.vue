<script setup lang="ts">
withDefaults(defineProps<{ color?: string }>(), { color: '#315fcf' })
</script>

<template>
  <svg class="vehicle-silhouette" viewBox="0 0 400 160" fill="none" aria-hidden="true">
    <ellipse cx="198" cy="142" rx="166" ry="6" fill="currentColor" opacity=".07" />

    <!-- A deliberately directional three-box saloon: boot at left, bonnet at right. -->
    <path
      d="M23 118 29 99c3-9 9-14 20-17l43-7 32-32c9-9 20-13 35-13h66c16 0 28 5 38 18l23 29 51 8c14 2 24 10 28 22l4 13c2 7-3 12-11 12H34c-9 0-13-5-11-14Z"
      :fill="color"
      fill-opacity=".11"
    />
    <path
      d="M23 118 29 99c3-9 9-14 20-17l43-7 32-32c9-9 20-13 35-13h66c16 0 28 5 38 18l23 29 51 8c14 2 24 10 28 22l4 13c2 7-3 12-11 12H34c-9 0-13-5-11-14Z"
      :stroke="color"
      stroke-width="2.6"
      stroke-linejoin="round"
    />

    <!-- The unequal glass angles make the front and rear immediately legible. -->
    <path
      d="m106 74 25-26c7-7 15-10 27-10h27v36h-79Z"
      fill="var(--panel)"
      :stroke="color"
      stroke-width="1.8"
      stroke-linejoin="round"
    />
    <path
      d="M194 38h30c12 0 20 4 27 14l17 22h-74V38Z"
      fill="var(--panel)"
      :stroke="color"
      stroke-width="1.8"
      stroke-linejoin="round"
    />
    <path d="m269 71 9-5 12 3-5 8h-16Z" :fill="color" fill-opacity=".24" :stroke="color" stroke-width="1.5" stroke-linejoin="round" />

    <!-- Panel construction and shoulder line. -->
    <path d="M96 76 86 129m101-91v91m83-52 14 52M42 93h43m202-15 47 7" :stroke="color" stroke-width="1.5" stroke-linecap="round" opacity=".62" />
    <path d="M48 94c67-8 181-9 291-1M126 84h22m64 0h22" :stroke="color" stroke-width="2" stroke-linecap="round" opacity=".72" />
    <path d="M48 97h18v9H34m313-8h14l4 12h-22" :stroke="color" stroke-width="2" stroke-linejoin="round" />

    <!-- Rear lamp, front headlamp and grille reinforce the orientation. -->
    <path d="M31 88h13v13H28" :fill="color" fill-opacity=".48" />
    <path d="M344 91h15l4 10h-22Z" fill="var(--panel)" :stroke="color" stroke-width="1.6" stroke-linejoin="round" />
    <path d="M363 106h-13m15 6h-17" :stroke="color" stroke-width="1.5" stroke-linecap="round" opacity=".72" />
    <circle cx="72" cy="87" r="5" :stroke="color" stroke-width="1.5" opacity=".62" />

    <circle cx="91" cy="129" r="21" fill="var(--panel)" stroke="currentColor" stroke-width="5" />
    <circle cx="91" cy="129" r="9" :fill="color" fill-opacity=".15" :stroke="color" stroke-width="2" />
    <circle cx="310" cy="129" r="21" fill="var(--panel)" stroke="currentColor" stroke-width="5" />
    <circle cx="310" cy="129" r="9" :fill="color" fill-opacity=".15" :stroke="color" stroke-width="2" />
  </svg>
</template>

<style scoped>
.vehicle-silhouette{display:block;width:100%;height:auto;color:var(--text)}
</style>
