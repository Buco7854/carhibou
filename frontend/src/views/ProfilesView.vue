<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api, errorMessage } from '../api/client'
import type { ProfileType, VehicleProfile } from '../api/types'
import { canCreateProfiles } from '../access'
import AppIcon from '../components/AppIcon.vue'
import MappingProfileEditor from '../components/MappingProfileEditor.vue'
import VehicleProfileEditor from '../components/VehicleProfileEditor.vue'

const { t } = useI18n()
const profiles = ref<VehicleProfile[]>([])
const usage = ref<Record<string, number>>({})
const editorType = ref<ProfileType>('can')
const editorOpen = ref(false)
const cloning = ref(false)
const selectedProfile = ref<VehicleProfile | null>(null)
const error = ref('')
const customProfiles = computed(() => profiles.value.filter((profile) => !profile.built_in))
const builtInProfiles = computed(() => profiles.value.filter((profile) => profile.built_in))

async function load(): Promise<void> {
  error.value = ''
  try {
    await fetchProfiles()
  } catch (reason) {
    error.value = errorMessage(reason, t('common.error'))
  }
}

async function fetchProfiles(): Promise<void> {
  const [loadedProfiles, agents, connectors] = await Promise.all([
    api<VehicleProfile[]>('/vehicle-profiles'),
    api<Array<{ vehicle_profile: string | null }>>('/agents').catch(() => []),
    api<Array<{ mapping_profile: string }>>('/connectors').catch(() => []),
  ])
  profiles.value = loadedProfiles
  const counts: Record<string, number> = {}
  for (const agent of agents) if (agent.vehicle_profile) counts[agent.vehicle_profile] = (counts[agent.vehicle_profile] ?? 0) + 1
  for (const connector of connectors) if (connector.mapping_profile) counts[connector.mapping_profile] = (counts[connector.mapping_profile] ?? 0) + 1
  usage.value = counts
}

function createProfile(type: ProfileType): void {
  selectedProfile.value = null
  cloning.value = false
  editorType.value = type
  editorOpen.value = true
}

function editProfile(profile: VehicleProfile): void {
  selectedProfile.value = profile
  cloning.value = false
  editorType.value = profile.type
  editorOpen.value = true
}

function cloneProfile(profile: VehicleProfile): void {
  selectedProfile.value = profile
  cloning.value = true
  editorType.value = profile.type
  editorOpen.value = true
}

function assignedCount(profile: VehicleProfile): number {
  return usage.value[profile.id] ?? 0
}

function entryCount(profile: VehicleProfile): number {
  return profile.type === 'mapping' ? (profile.definition.rules ?? []).length : (profile.definition.signals ?? []).length
}

function chips(profile: VehicleProfile): string[] {
  return profile.type === 'mapping'
    ? (profile.definition.rules ?? []).map((rule) => rule.match)
    : (profile.definition.signals ?? []).map((signal) => signal.name)
}

async function remove(profile: VehicleProfile): Promise<void> {
  if (!window.confirm(t('profiles.deleteConfirm', { name: profile.name }))) return
  error.value = ''
  try {
    await api(`/vehicle-profiles/${profile.id}`, { method: 'DELETE' })
    await load()
  } catch (reason) {
    error.value = errorMessage(reason, t('common.error'))
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
        <button v-if="canCreateProfiles" class="button secondary" type="button" @click="createProfile('mapping')"><AppIcon name="plus" :size="15" />{{ t('profiles.newMapping') }}</button>
        <button v-if="canCreateProfiles" class="button" type="button" @click="createProfile('can')"><AppIcon name="plus" :size="15" />{{ t('profiles.newCan') }}</button>
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
            <div class="profile-title"><h3>{{ profile.name }}</h3><span class="type-badge">{{ t(`profiles.type.${profile.type}`) }}</span></div>
            <!-- The server says who may touch a profile; everyone else reads it. -->
            <div v-if="profile.editable" class="profile-actions">
              <button class="icon-button" type="button" :aria-label="t('profiles.edit')" @click="editProfile(profile)"><AppIcon name="edit" :size="15" /></button>
              <button class="icon-button danger-text" type="button" :aria-label="t('common.delete')" @click="remove(profile)"><AppIcon name="trash" :size="15" /></button>
            </div>
            <span v-else class="readonly-badge">{{ t('profiles.readOnly') }}</span>
          </header>
          <p>{{ profile.description || t('profiles.noDescription') }}</p>
          <div class="metric-chips"><code v-for="item in chips(profile).slice(0,6)" :key="item">{{ item }}</code><span v-if="entryCount(profile)>6">+{{ entryCount(profile)-6 }}</span></div>
          <footer><span>{{ profile.type==='mapping' ? t('profiles.ruleCount',{count:entryCount(profile)}) : t('profiles.signalCount',{count:entryCount(profile)}) }}</span><span>{{ t('profiles.assignedCount', { count:assignedCount(profile) }) }}</span><span>v{{ profile.definition.version }}</span></footer>
        </article>
        <button v-if="!customProfiles.length && canCreateProfiles" class="empty-profile panel" type="button" @click="createProfile('can')">
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
            <div class="profile-title"><h3>{{ profile.name }}</h3><span class="type-badge">{{ t(`profiles.type.${profile.type}`) }}</span></div>
            <div class="profile-actions">
              <button v-if="canCreateProfiles" class="icon-button" type="button" :aria-label="t('profiles.clone')" :title="t('profiles.clone')" @click="cloneProfile(profile)"><AppIcon name="copy" :size="15" /></button>
              <span class="readonly-badge">{{ t('profiles.readOnly') }}</span>
            </div>
          </header>
          <p>{{ profile.description || t('profiles.noDescription') }}</p>
          <div class="metric-chips"><code v-for="item in chips(profile).slice(0,6)" :key="item">{{ item }}</code><span v-if="entryCount(profile)>6">+{{ entryCount(profile)-6 }}</span></div>
          <footer><span>{{ profile.type==='mapping' ? t('profiles.ruleCount',{count:entryCount(profile)}) : t('profiles.signalCount',{count:entryCount(profile)}) }}</span><span>{{ t('profiles.assignedCount', { count:assignedCount(profile) }) }}</span><span>v{{ profile.definition.version }}</span></footer>
        </article>
      </div>
    </section>

    <VehicleProfileEditor :open="editorOpen && editorType==='can'" :profile="selectedProfile" :clone="cloning" @close="editorOpen=false" @saved="saved" />
    <MappingProfileEditor :open="editorOpen && editorType==='mapping'" :profile="selectedProfile" :clone="cloning" @close="editorOpen=false" @saved="saved" />
  </div>
</template>

<style scoped>
.profiles-page{max-width:1100px;margin-left:0;display:grid;gap:26px}
.profiles-page>.page-header{margin-bottom:0}
.profile-section{display:grid}
.profile-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:12px}
.profile-card{min-width:0;display:flex;flex-direction:column;padding:16px}
.profile-card>header{display:flex;align-items:flex-start;justify-content:space-between;gap:12px}
.profile-title{min-width:0;display:flex;align-items:center;flex-wrap:wrap;gap:8px}
.profile-card h3{margin:0;font-size:var(--font-section);font-weight:600;letter-spacing:-.01em}
.type-badge{flex:none;padding:2px 6px;color:var(--accent);background:var(--accent-soft);border-radius:var(--radius-sm);font-size:var(--font-micro)}
.profile-card>p{margin:8px 0 12px;color:var(--muted);font-size:var(--font-caption);line-height:1.5}
.profile-actions{flex:none;display:flex;align-items:center;gap:6px;margin:-4px -4px 0 0}
.danger-text{color:var(--danger)}
.danger-text:hover{color:var(--danger);background:var(--danger-soft)}
.readonly-badge{flex:none;padding:2px 6px;color:var(--muted);background:var(--panel-2);border-radius:var(--radius-sm);font-size:var(--font-micro)}
.metric-chips{display:flex;align-items:center;flex-wrap:wrap;gap:4px}
.metric-chips code{padding:2px 6px;color:var(--text);background:var(--panel-2);border-radius:var(--radius-sm);font-family:var(--mono);font-size:var(--font-micro)}
.metric-chips span{color:var(--muted);font-size:var(--font-micro)}
.profile-card>footer{display:flex;align-items:center;flex-wrap:wrap;gap:4px 14px;margin-top:auto;padding-top:12px;color:var(--muted);font-size:var(--font-caption)}
.profile-card>footer>span+span::before{content:"·";margin-right:14px}
.empty-profile{min-height:96px;display:grid;place-items:center;align-content:center;gap:4px;padding:24px;color:var(--muted);border-style:dashed;cursor:pointer;transition:border-color .12s}
.empty-profile:hover{border-color:var(--muted-2)}
.empty-profile strong{color:var(--text);font-size:var(--font-body);font-weight:500}
.empty-profile span{font-size:var(--font-caption)}
@media(max-width:560px){.profile-grid{grid-template-columns:1fr}}
</style>
