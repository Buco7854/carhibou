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
      <div><span class="eyebrow">{{ t('profiles.eyebrow') }}</span><h1>{{ t('profiles.title') }}</h1><p>{{ t('profiles.pageHint') }}</p></div>
      <button class="button" type="button" @click="createProfile"><AppIcon name="plus" :size="15" />{{ t('profiles.new') }}</button>
    </header>

    <section class="profile-intro panel">
      <div class="intro-icon"><AppIcon name="profile" :size="22" /></div>
      <div><h2>{{ t('profiles.whatTitle') }}</h2><p>{{ t('profiles.explanation') }}</p></div>
      <p class="profile-safety"><AppIcon name="signal" :size="16" />{{ t('profiles.safety') }}</p>
    </section>

    <p v-if="error" class="error panel profile-error" role="alert">{{ error }}</p>

    <section class="profile-section" aria-labelledby="custom-profile-title">
      <header class="section-heading"><div><h2 id="custom-profile-title">{{ t('profiles.customTitle') }}</h2><p>{{ t('profiles.customHint') }}</p></div><span>{{ customProfiles.length }}</span></header>
      <div class="profile-grid">
        <article v-for="profile in customProfiles" :key="profile.id" class="profile-card panel">
          <header><div><span class="profile-kind">{{ t('profiles.custom') }}</span><h3>{{ profile.name }}</h3></div><div class="profile-actions"><button class="icon-button" type="button" :aria-label="t('profiles.edit')" @click="editProfile(profile)"><AppIcon name="edit" :size="16" /></button><button class="icon-button danger-text" type="button" :aria-label="t('common.delete')" @click="remove(profile)"><AppIcon name="trash" :size="16" /></button></div></header>
          <p>{{ profile.description || t('profiles.noDescription') }}</p>
          <div class="metric-chips"><code v-for="item in profile.definition.signals.slice(0,6)" :key="item.name">{{ item.name }}</code><span v-if="profile.definition.signals.length>6">+{{ profile.definition.signals.length-6 }}</span></div>
          <footer><span>{{ t('profiles.signalCount', { count:profile.definition.signals.length }) }}</span><span>{{ t('profiles.assignedCount', { count:assignedCount(profile) }) }}</span><span>v{{ profile.definition.version }}</span></footer>
        </article>
        <button v-if="!customProfiles.length" class="empty-profile panel" type="button" @click="createProfile"><AppIcon name="plus" :size="20" /><strong>{{ t('profiles.createFirst') }}</strong><span>{{ t('profiles.noCustom') }}</span></button>
      </div>
    </section>

    <section class="profile-section" aria-labelledby="built-in-profile-title">
      <header class="section-heading"><div><h2 id="built-in-profile-title">{{ t('profiles.builtInTitle') }}</h2><p>{{ t('profiles.builtInHint') }}</p></div><span>{{ builtInProfiles.length }}</span></header>
      <div class="profile-grid">
        <article v-for="profile in builtInProfiles" :key="profile.id" class="profile-card panel built-in-card">
          <header><div><span class="profile-kind">{{ t('profiles.builtIn') }}</span><h3>{{ profile.name }}</h3></div><span class="readonly-badge">{{ t('profiles.readOnly') }}</span></header>
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
.profiles-page{display:grid;gap:30px}.profiles-page>.page-header{margin-bottom:0}.profile-intro{display:grid;grid-template-columns:46px minmax(0,1fr);align-items:center;gap:14px 18px;padding:20px}.intro-icon{width:46px;height:46px;display:grid;place-items:center;color:var(--accent);background:var(--accent-soft);border-radius:11px}.profile-intro h2{margin:0;font-size:15px}.profile-intro p{margin:6px 0 0;color:var(--muted);font-size:10px;line-height:1.55}.profile-safety{grid-column:2;display:flex;align-items:center;gap:8px!important;margin:0!important;padding-top:11px;color:var(--muted)!important;border-top:1px solid var(--line);font-size:9px!important}.profile-safety .app-icon{flex:none;color:var(--accent)}.profile-error{margin:0;padding:12px 15px}.profile-section{display:grid;gap:12px}.section-heading{display:flex;align-items:flex-start;justify-content:flex-start;gap:10px;padding:0 3px}.section-heading h2{margin:0;font-size:17px}.section-heading p{margin:5px 0 0;color:var(--muted);font-size:10px}.section-heading>span{margin-top:1px;padding:4px 8px;color:var(--muted);background:var(--panel-2);border-radius:6px;font:600 9px "IBM Plex Mono",monospace}.profile-grid{display:grid;grid-template-columns:minmax(0,1fr);gap:12px}.profile-card{min-width:0;display:flex;flex-direction:column;padding:17px}.profile-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}.profile-kind{display:block;margin-bottom:5px;color:var(--accent);font:500 8px "IBM Plex Mono",monospace;text-transform:uppercase;letter-spacing:.06em}.profile-card h3{margin:0;font-size:15px}.profile-card>p{margin:11px 0 13px;color:var(--muted);font-size:10px;line-height:1.55}.profile-actions{display:flex;align-items:center;gap:3px}.profile-actions .icon-button{width:34px;height:34px;border:1px solid var(--line);border-radius:7px}.danger-text{color:var(--danger)}.readonly-badge{padding:5px 7px;color:var(--muted);background:var(--panel-2);border-radius:6px;font-size:8px}.metric-chips{min-height:27px;display:flex;align-items:center;flex-wrap:wrap;gap:5px}.metric-chips code,.metric-chips span{padding:5px 7px;color:var(--text);background:var(--panel-2);border-radius:5px;font-size:8px}.metric-chips span{color:var(--muted)}.profile-card>footer{display:flex;align-items:center;flex-wrap:wrap;gap:7px 14px;margin-top:15px;padding-top:12px;color:var(--muted);border-top:1px solid var(--line);font-size:9px}.empty-profile{min-height:120px;display:grid;place-items:center;align-content:center;gap:7px;padding:25px;color:var(--muted);border-style:dashed;cursor:pointer}.empty-profile:hover{color:var(--accent);border-color:var(--accent)}.empty-profile strong{color:var(--text);font-size:12px}.empty-profile span{font-size:9px}.built-in-card{box-shadow:none}@media(max-width:900px){.profile-intro{grid-template-columns:46px 1fr}.profile-safety{grid-column:2}}@media(max-width:560px){.profile-intro{grid-template-columns:1fr}.profile-safety{grid-column:auto}.profiles-page>.page-header .button{width:100%}}
</style>
