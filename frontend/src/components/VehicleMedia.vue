<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import type { Vehicle } from '../api/types'
import AppIcon from './AppIcon.vue'

const props = withDefaults(defineProps<{ vehicle: Vehicle; editable?: boolean; busy?: boolean }>(), {
  editable: false,
  busy: false,
})
const emit = defineEmits<{ select: [file: File]; remove: [] }>()
const { t } = useI18n()
const imageFailed = ref(false)

watch(() => props.vehicle.photo_url, () => { imageFailed.value = false })

function selectPhoto(event: Event): void {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (file) emit('select', file)
  input.value = ''
}
</script>

<template>
  <div class="vehicle-media" :style="{ '--vehicle-color': vehicle.color || 'var(--muted)' }">
    <img
      v-if="vehicle.photo_url && !imageFailed"
      :src="vehicle.photo_url"
      :alt="t('vehicles.photoAlt', { name: vehicle.name })"
      @error="imageFailed = true"
    />
    <div v-else class="vehicle-photo-placeholder" role="img" :aria-label="imageFailed ? t('vehicles.photoUnavailable') : t('vehicles.noPhoto', { name: vehicle.name })">
      <AppIcon name="image-missing" :size="34" />
    </div>

    <div v-if="editable" class="media-actions">
      <label :class="['media-action', { disabled: busy }]">
        <AppIcon name="camera" :size="14" />
        <span>{{ vehicle.photo_url ? t('vehicles.changePhoto') : t('vehicles.addPhoto') }}</span>
        <input class="sr-only" type="file" accept="image/jpeg,image/png,image/webp" :disabled="busy" @change="selectPhoto" />
      </label>
      <button v-if="vehicle.photo_url" class="media-action remove" type="button" :disabled="busy" :aria-label="t('vehicles.removePhoto')" :title="t('vehicles.removePhoto')" @click="emit('remove')">
        <AppIcon name="trash" :size="14" />
      </button>
    </div>
    <span v-if="busy" class="media-busy" role="status">{{ t('vehicles.uploadingPhoto') }}</span>
  </div>
</template>

<style scoped>
.vehicle-media{--vehicle-color:var(--muted);position:relative;width:100%;height:100%;min-height:96px;overflow:hidden;color:var(--text);background:var(--panel-2)}
.vehicle-media>img{width:100%;height:100%;display:block;object-fit:cover}
.vehicle-photo-placeholder{width:100%;height:100%;display:grid;place-items:center;padding:16px;color:var(--muted-2);background:var(--panel-2)}
.media-actions{position:absolute;right:6px;bottom:6px;display:flex;gap:4px}
.media-action{
  height:26px;display:inline-flex;align-items:center;justify-content:center;gap:5px;padding:0 8px;
  color:var(--text);background:color-mix(in srgb,var(--panel) 92%,transparent);
  border:1px solid var(--line-strong);border-radius:var(--radius);
  font-size:12px;cursor:pointer;backdrop-filter:blur(8px);
}
.media-action:hover{border-color:var(--muted-2)}
.media-action:has(input:focus){outline:2px solid var(--accent);outline-offset:2px}
.media-action.remove{width:26px;padding:0;color:var(--danger)}
.media-action:disabled,.media-action.disabled{opacity:.55;cursor:wait}
.media-busy{position:absolute;inset:0;display:grid;place-items:center;color:var(--text);background:color-mix(in srgb,var(--panel) 82%,transparent);font-size:12px;backdrop-filter:blur(3px)}
</style>
