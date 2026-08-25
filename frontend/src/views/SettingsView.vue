<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth, logout } from '../api/auth'
import type { BrowserSession, Diagnostics } from '../api/types'
import AppSelect from '../components/AppSelect.vue'
import { persistLocale } from '../i18n'
import { setTheme, themeMode } from '../theme'

const { locale, t } = useI18n()
const router = useRouter()
const diagnostics = ref<Diagnostics | null>(null)
const sessions = ref<BrowserSession[]>([])
const currentPassword = ref('')
const newPassword = ref('')
const accountMessage = ref('')
const accountError = ref('')

function changeLocale(value: string | number | null): void {
  if (value !== 'en' && value !== 'fr') return
  locale.value = value
  persistLocale(value)
}

function changeTheme(value: string | number | null): void {
  if (value === 'light' || value === 'dark' || value === 'auto') setTheme(value)
}

async function changePassword(): Promise<void> {
  accountError.value = ''
  try {
    await api('/auth/password', { method:'POST', body:JSON.stringify({ current_password:currentPassword.value, new_password:newPassword.value }) })
    currentPassword.value = ''; newPassword.value = ''; accountMessage.value = t('settings.passwordChanged')
    sessions.value = await api<BrowserSession[]>('/auth/sessions')
  } catch (reason) { accountError.value = reason instanceof Error ? reason.message : t('common.error') }
}

async function revokeSession(id: string): Promise<void> {
  await api(`/auth/sessions/${id}`, { method:'DELETE' })
  sessions.value = sessions.value.filter((session) => session.id !== id)
}

async function signOut(): Promise<void> {
  await logout()
  await router.push({ name: 'login' })
}

onMounted(async () => {
  sessions.value = await api<BrowserSession[]>('/auth/sessions')
  if (auth.user?.permissions['system.admin']) {
    try { diagnostics.value = await api<Diagnostics>('/system/diagnostics') } catch { /* health remains visible through direct endpoint */ }
  }
})
</script>

<template>
  <div class="page settings-page">
    <header class="page-header"><div><h1>{{ t('settings.title') }}</h1></div></header>

    <section class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.appearance') }}</h2><p>{{ t('settings.saved') }}</p></div>
      <div class="settings-body">
        <div class="settings-pair">
          <div class="field"><label for="theme">{{ t('settings.theme') }}</label><AppSelect id="theme" :model-value="themeMode" @update:model-value="changeTheme"><option value="auto">{{ t('settings.auto') }}</option><option value="light">{{ t('settings.light') }}</option><option value="dark">{{ t('settings.dark') }}</option></AppSelect></div>
          <div class="field"><label for="locale">{{ t('settings.language') }}</label><AppSelect id="locale" :model-value="locale" @update:model-value="changeLocale"><option value="en">{{ t('settings.english') }}</option><option value="fr">{{ t('settings.french') }}</option></AppSelect></div>
        </div>
      </div>
    </section>

    <section class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.account') }}</h2><p>{{ t('settings.sessionHint') }}</p></div>
      <div class="settings-body">
        <dl class="account-facts">
          <div><dt>{{ t('auth.displayName') }}</dt><dd>{{ auth.user?.display_name }}</dd></div>
          <div><dt>{{ t('auth.email') }}</dt><dd>{{ auth.user?.email }}</dd></div>
        </dl>
        <form class="password-form" @submit.prevent="changePassword">
          <div class="settings-pair">
            <label class="field"><span>{{ t('settings.currentPassword') }}</span><input v-model="currentPassword" class="input" type="password" autocomplete="current-password" required /></label>
            <label class="field"><span>{{ t('settings.newPassword') }}</span><input v-model="newPassword" class="input" type="password" minlength="12" autocomplete="new-password" required /></label>
          </div>
          <p v-if="accountError" class="error">{{ accountError }}</p>
          <p v-if="accountMessage" class="success">{{ accountMessage }}</p>
          <div class="password-actions">
            <button class="button secondary">{{ t('settings.changePassword') }}</button>
            <button class="link-button danger" type="button" @click="signOut">{{ t('nav.signOut') }}</button>
          </div>
        </form>
      </div>
    </section>

    <section class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.activeSessions') }}</h2></div>
      <div class="settings-body">
        <ul class="session-list">
          <li v-for="session in sessions" :key="session.id">
            <div><strong>{{ session.current ? t('settings.currentSession') : (session.user_agent || t('settings.unknownClient')) }}</strong><small>{{ session.ip_address || '—' }} · {{ new Date(session.last_seen_at).toLocaleString() }}</small></div>
            <button v-if="!session.current" class="link-button" @click="revokeSession(session.id)">{{ t('settings.revokeSession') }}</button>
          </li>
        </ul>
      </div>
    </section>

    <section v-if="diagnostics" class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.diagnostics') }}</h2></div>
      <div class="settings-body">
        <dl class="diagnostics-grid">
          <div><dt>{{ t('settings.version') }}</dt><dd class="mono">{{ diagnostics.version }}</dd></div>
          <div><dt>{{ t('settings.database') }}</dt><dd class="mono">{{ diagnostics.database }}</dd></div>
          <div><dt>{{ t('settings.workers') }}</dt><dd class="mono">{{ diagnostics.workers.length }}</dd></div>
          <div><dt>{{ t('settings.pendingJobs') }}</dt><dd class="mono">{{ diagnostics.pending_jobs }}</dd></div>
          <div><dt>{{ t('settings.failedJobs') }}</dt><dd class="mono">{{ diagnostics.failed_jobs }}</dd></div>
          <div><dt>{{ t('settings.hookFailures') }}</dt><dd class="mono">{{ diagnostics.hook_failures }}</dd></div>
          <div><dt>{{ t('settings.staleDevices') }}</dt><dd class="mono">{{ diagnostics.stale_devices }}</dd></div>
        </dl>
      </div>
    </section>
  </div>
</template>

<style scoped>
.settings-page{max-width:900px;margin-left:0}
.settings-block{display:grid;grid-template-columns:minmax(0,220px) minmax(0,1fr);gap:20px 40px;padding:22px 0;border-top:1px solid var(--line)}
.settings-block:first-of-type{border-top:0;padding-top:0}
.settings-label h2{margin:0;font-size:14px;font-weight:600}
.settings-label p{margin:5px 0 0;color:var(--muted);font-size:12px;line-height:1.5}
.settings-body{display:grid;gap:20px}
.settings-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}

.account-facts{display:grid;gap:7px;margin:0}
.account-facts>div{display:flex;align-items:baseline;gap:12px}
.account-facts dt{min-width:110px;color:var(--muted);font-size:12px}
.account-facts dd{margin:0;font-size:13px;font-weight:500}

.password-form{display:grid;gap:12px}
.password-actions{display:flex;align-items:center;gap:16px}

.session-list{list-style:none;margin:0;padding:0;display:grid}
.session-list li{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)}
.session-list li:first-child{padding-top:0}
.session-list li:last-child{border-bottom:0;padding-bottom:0}
.session-list strong{display:block;font-size:13px;font-weight:500}
.session-list small{display:block;margin-top:2px;color:var(--muted);font-size:12px}

.diagnostics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:14px;margin:0}
.diagnostics-grid dt{color:var(--muted);font-size:12px}
.diagnostics-grid dd{margin:3px 0 0;font-size:15px;font-weight:500}

@media(max-width:760px){
  .settings-block{grid-template-columns:1fr;gap:14px}
  .settings-pair{grid-template-columns:1fr}
}
</style>
