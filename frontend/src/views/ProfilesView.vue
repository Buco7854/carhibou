<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import type { Vehicle, VehicleProfile } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import VehicleProfileEditor from '../components/VehicleProfileEditor.vue'

const { t } = useI18n()
const profiles = ref<VehicleProfile[]>([])
const vehicles = ref<Vehicle[]>([])
const editorOpen = ref(false)
const selectedProfile = ref<VehicleProfile | null>(null)
const error = ref('')
const customProfiles = computed(() => profiles.value.filter((profile) => !profile.built_in))
const builtInProfiles = computed(() => profiles.value.filter((profile) => profile.built_in))

async function load(): Promise<void> {
  ;[profiles.value, vehicles.value] = await Promise.all([
    api<VehicleProfile[]>('/vehicle-profiles'),
    api<Vehicle[]>('/vehicles'),
  ])
}

function createProfile(): void {
  selectedProfile.value = null
  editorOpen.value = true
}

function editProfile(profile: VehicleProfile): void {
  selectedProfile.value = profile
  editorOpen.value = true
}

function assignedCount(profile: VehicleProfile): number {
  return vehicles.value.filter((vehicle) => vehicle.vehicle_profile === profile.id).length
}

async function remove(profile: VehicleProfile): Promise<void> {
  if (!window.confirm(t('profiles.deleteConfirm', { name: profile.name }))) return
  error.value = ''
  try {
    await api(`/vehicle-profiles/${profile.id}`, { method: 'DELETE' })
    await load()
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : t('common.error')
  }
}

async function saved(): Promise<void> { await load() }
onMounted(load)
</script>

<template>
  <div class="page profiles-page">
    <header class="page-header">
      <div>
        <h1>{{ t('profiles.title') }}</h1>
        <p>{{ t('profiles.pageHint') }}</p>
      </div>
      <div class="header-actions">
        <button class="button" type="button" @click="createProfile"><AppIcon name="plus" :size="15" />{{ t('profiles.new') }}</button>
      </div>
    </header>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <section class="profile-section" aria-labelledby="custom-profile-title">
      <div class="section-head">
        <h2 id="custom-profile-title">{{ t('profiles.customTitle') }}</h2>
        <span class="count">{{ customProfiles.length }}</span>
      </div>
      <div class="profile-grid">
        <article v-for="profile in customProfiles" :key="profile.id" class="profile-card panel">
          <header>
            <h3>{{ profile.name }}</h3>
            <div class="profile-actions">
              <button class="icon-button" type="button" :aria-label="t('profiles.edit')" @click="editProfile(profile)"><AppIcon name="edit" :size="15" /></button>
              <button class="icon-button danger-text" type="button" :aria-label="t('common.delete')" @click="remove(profile)"><AppIcon name="trash" :size="15" /></button>
            </div>
          </header>
          <p>{{ profile.description || t('profiles.noDescription') }}</p>
          <div class="metric-chips"><code v-for="item in profile.definition.signals.slice(0,6)" :key="item.name">{{ item.name }}</code><span v-if="profile.definition.signals.length>6">+{{ profile.definition.signals.length-6 }}</span></div>
          <footer><span>{{ t('profiles.signalCount', { count:profile.definition.signals.length }) }}</span><span>{{ t('profiles.assignedCount', { count:assignedCount(profile) }) }}</span><span>v{{ profile.definition.version }}</span></footer>
        </article>
        <button v-if="!customProfiles.length" class="empty-profile panel" type="button" @click="createProfile">
          <strong>{{ t('profiles.createFirst') }}</strong>
          <span>{{ t('profiles.noCustom') }}</span>
        </button>
      </div>
    </section>

    <section class="profile-section" aria-labelledby="built-in-profile-title">
      <div class="section-head">
        <h2 id="built-in-profile-title">{{ t('profiles.builtInTitle') }}</h2>
        <span class="count">{{ builtInProfiles.length }}</span>
      </div>
      <div class="profile-grid">
        <article v-for="profile in builtInProfiles" :key="profile.id" class="profile-card panel">
          <header>
            <h3>{{ profile.name }}</h3>
            <span class="readonly-badge">{{ t('profiles.readOnly') }}</span>
          </header>
          <p>{{ profile.description || t('profiles.noDescription') }}</p>
          <div class="metric-chips"><code v-for="item in profile.definition.signals.slice(0,6)" :key="item.name">{{ item.name }}</code><span v-if="profile.definition.signals.length>6">+{{ profile.definition.signals.length-6 }}</span></div>
          <footer><span>{{ t('profiles.signalCount', { count:profile.definition.signals.length }) }}</span><span>{{ t('profiles.assignedCount', { count:assignedCount(profile) }) }}</span><span>v{{ profile.definition.version }}</span></footer>
        </article>
      </div>
    </section>

    <VehicleProfileEditor :open="editorOpen" :profile="selectedProfile" @close="editorOpen=false" @saved="saved" />
  </div>
</template>

<style scoped>
.profiles-page{max-width:1100px;margin-left:0;display:grid;gap:26px}
.profiles-page>.page-header{margin-bottom:0}
.profile-section{display:grid}
.profile-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
.profile-card{min-width:0;display:flex;flex-direction:column;padding:15px 16px}
.profile-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.profile-card h3{margin:0;font-size:14px;font-weight:600}
.profile-card>p{margin:8px 0 12px;color:var(--muted);font-size:12px;line-height:1.5}
.profile-actions{display:flex;align-items:center;gap:2px;margin:-4px -4px 0 0}
.danger-text{color:var(--danger)}
.danger-text:hover{color:var(--danger);background:var(--danger-soft)}
.readonly-badge{flex:none;padding:2px 6px;color:var(--muted);background:var(--panel-2);border-radius:4px;font-size:11px}
.metric-chips{display:flex;align-items:center;flex-wrap:wrap;gap:4px}
.metric-chips code{padding:2px 6px;color:var(--text);background:var(--panel-2);border-radius:4px;font-family:var(--mono);font-size:11px}
.metric-chips span{color:var(--muted);font-size:11px}
.profile-card>footer{display:flex;align-items:center;flex-wrap:wrap;gap:4px 14px;margin-top:auto;padding-top:12px;color:var(--muted);font-size:12px}
.profile-card>footer>span+span::before{content:"·";margin-right:14px}
.empty-profile{min-height:96px;display:grid;place-items:center;align-content:center;gap:4px;padding:22px;color:var(--muted);border-style:dashed;cursor:pointer}
.empty-profile:hover{border-color:var(--muted-2)}
.empty-profile strong{color:var(--text);font-size:13px;font-weight:500}
.empty-profile span{font-size:12px}
@media(max-width:560px){.profile-grid{grid-template-columns:1fr}}
</style>
