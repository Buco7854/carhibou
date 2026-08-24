<script setup lang="ts">
withDefaults(defineProps<{ color?: string }>(), { color: '#315fcf' })
</script>

<template>
  <svg class="vehicle-silhouette" viewBox="0 0 520 190" fill="none" aria-hidden="true">
    <ellipse cx="262" cy="169" rx="222" ry="8" fill="currentColor" opacity=".08" />

    <!-- A low three-box saloon: separate boot, flowing cabin and long bonnet. -->
    <path
      d="M24 139c2-14 7-26 21-33 16-8 43-11 73-15l38-31c14-12 30-19 51-23 38-7 88-8 130-1 22 4 38 13 53 31l19 24 57 11c16 3 27 13 31 27l4 13c2 7-3 12-12 12h-25c-2-30-20-46-44-46-25 0-42 17-45 46H152c-3-29-21-46-46-46-24 0-42 17-45 46H36c-9 0-14-6-12-15Z"
      :fill="color"
      :stroke="color"
      stroke-width="2.5"
      stroke-linejoin="round"
    />

    <!-- Dark continuous glasshouse keeps the illustration graphic rather than photographic. -->
    <path
      d="m137 90 32-27c11-9 23-14 40-17 16-3 34-4 53-4v48H137Z"
      fill="#17212d"
      stroke="rgb(255 255 255/.5)"
      stroke-width="2"
      stroke-linejoin="round"
    />
    <path
      d="M273 42c21 0 40 2 58 5 17 3 29 11 40 24l16 19H273V42Z"
      fill="#17212d"
      stroke="rgb(255 255 255/.5)"
      stroke-width="2"
      stroke-linejoin="round"
    />
    <path d="M146 84c26-20 58-31 99-34m37-1c29 0 54 5 71 16" stroke="white" stroke-width="2" stroke-linecap="round" opacity=".16" />

    <!-- Body construction and directional details. -->
    <path d="M32 124c103-20 263-25 440-3v28H30Z" fill="black" opacity=".1" />
    <path d="M45 111c113-17 285-18 427 2M130 95l-9 22m143-75v109m130-58 14 29" stroke="white" stroke-width="1.8" stroke-linecap="round" opacity=".34" />
    <path d="M177 105h24m91 0h24" stroke="white" stroke-width="2.5" stroke-linecap="round" opacity=".58" />
    <path d="M155 144h220" stroke="black" stroke-width="2" stroke-linecap="round" opacity=".22" />
    <path d="m390 87 10-7 15 2-8 10h-17Z" fill="#17212d" :stroke="color" stroke-width="1.8" stroke-linejoin="round" />

    <!-- Rear and front have deliberately different light signatures. -->
    <path d="m33 105 22-4-3 15-24 5Z" fill="#d75252" />
    <path d="m464 108 21 5 5 12-31-3Z" fill="#f4f7fb" stroke="#a9b5c2" stroke-width="1.7" stroke-linejoin="round" />
    <path d="M493 131h-23m26 7h-29" stroke="#17212d" stroke-width="2" stroke-linecap="round" />
    <circle cx="81" cy="109" r="6" fill="none" stroke="white" stroke-width="1.7" opacity=".45" />

    <g>
      <circle cx="106" cy="153" r="28" fill="#18212b" />
      <circle cx="106" cy="153" r="17" fill="#c6ced8" />
      <circle cx="106" cy="153" r="9" :fill="color" />
      <path d="m106 139 4 10 10 4-10 4-4 10-4-10-10-4 10-4Z" fill="#657181" />
    </g>
    <g>
      <circle cx="420" cy="153" r="28" fill="#18212b" />
      <circle cx="420" cy="153" r="17" fill="#c6ced8" />
      <circle cx="420" cy="153" r="9" :fill="color" />
      <path d="m420 139 4 10 10 4-10 4-4 10-4-10-10-4 10-4Z" fill="#657181" />
    </g>
  </svg>
</template>

<style scoped>
.vehicle-silhouette{display:block;width:100%;height:auto;color:var(--text);filter:drop-shadow(0 7px 5px rgb(16 24 40/.12))}
</style>
