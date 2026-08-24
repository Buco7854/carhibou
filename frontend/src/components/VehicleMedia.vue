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
  <div class="vehicle-media" :style="{ '--vehicle-color': vehicle.color || '#315fcf' }">
    <img
      v-if="vehicle.photo_url && !imageFailed"
      :src="vehicle.photo_url"
      :alt="t('vehicles.photoAlt', { name: vehicle.name })"
      @error="imageFailed = true"
    />
    <div v-else class="vehicle-photo-placeholder" role="img" :aria-label="t('vehicles.noPhoto', { name: vehicle.name })">
      <span class="placeholder-mark"><AppIcon name="vehicle" :size="30" /></span>
      <span><strong>{{ vehicle.manufacturer || vehicle.name }}</strong><small>{{ imageFailed ? t('vehicles.photoUnavailable') : t('vehicles.photoHint') }}</small></span>
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
.vehicle-media{--vehicle-color:var(--accent);position:relative;width:100%;height:100%;min-height:96px;overflow:hidden;background:var(--panel-2);border:1px solid var(--line);border-radius:8px}.vehicle-media>img{width:100%;height:100%;display:block;object-fit:cover}.vehicle-photo-placeholder{position:relative;width:100%;height:100%;display:flex;align-items:flex-end;gap:11px;padding:15px;color:var(--text);background:linear-gradient(140deg,color-mix(in srgb,var(--vehicle-color) 18%,var(--panel)) 0 48%,color-mix(in srgb,var(--vehicle-color) 7%,var(--panel-2)) 48% 100%)}.vehicle-photo-placeholder::after{content:"";position:absolute;right:-12%;bottom:28%;width:72%;height:1px;background:var(--vehicle-color);box-shadow:0 7px 0 color-mix(in srgb,var(--vehicle-color) 30%,transparent);opacity:.35;transform:rotate(-8deg)}.placeholder-mark{position:relative;z-index:1;width:48px;height:48px;display:grid;flex:none;place-items:center;color:var(--vehicle-color);background:color-mix(in srgb,var(--panel) 88%,transparent);border:1px solid color-mix(in srgb,var(--vehicle-color) 28%,var(--line));border-radius:8px;box-shadow:var(--shadow-soft)}.vehicle-photo-placeholder>span:last-child{position:relative;z-index:1;min-width:0}.vehicle-photo-placeholder strong,.vehicle-photo-placeholder small{display:block;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.vehicle-photo-placeholder strong{font-size:11px}.vehicle-photo-placeholder small{max-width:150px;margin-top:4px;color:var(--muted);font-size:8px}.media-actions{position:absolute;right:8px;bottom:8px;display:flex;gap:5px}.media-action{min-height:31px;display:inline-flex;align-items:center;justify-content:center;gap:6px;padding:6px 9px;color:var(--text);background:color-mix(in srgb,var(--panel) 92%,transparent);border:1px solid var(--line);border-radius:6px;box-shadow:var(--shadow-soft);font-size:8px;font-weight:600;cursor:pointer;backdrop-filter:blur(8px)}.media-action:hover{color:var(--accent);border-color:var(--accent)}.media-action.remove{width:31px;padding:6px;color:var(--danger)}.media-action:disabled,.media-action.disabled{opacity:.55;cursor:wait}.media-busy{position:absolute;inset:0;display:grid;place-items:center;color:var(--text);background:color-mix(in srgb,var(--panel) 76%,transparent);font-size:9px;font-weight:600;backdrop-filter:blur(3px)}
</style>
