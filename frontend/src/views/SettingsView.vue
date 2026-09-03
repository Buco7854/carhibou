<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { formatInstant } from '../vehicleDisplay'
import { useRouter } from 'vue-router'
import { api, errorMessage } from '../api/client'
import { auth, logout } from '../api/auth'
import type { BrowserSession } from '../api/types'
import AppSelect from '../components/AppSelect.vue'
import { persistLocale } from '../i18n'
import { mapThemeMode, setMapTheme, setTheme, themeMode } from '../theme'

const { locale, t } = useI18n()
const router = useRouter()
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

function changeMapTheme(value: string | number | null): void {
  if (value === 'light' || value === 'dark' || value === 'auto') setMapTheme(value)
}

async function changePassword(): Promise<void> {
  accountError.value = ''
  try {
    await api('/auth/password', { method:'POST', body:JSON.stringify({ current_password:currentPassword.value, new_password:newPassword.value }) })
    currentPassword.value = ''; newPassword.value = ''; accountMessage.value = t('settings.passwordChanged')
    sessions.value = await api<BrowserSession[]>('/auth/sessions')
  } catch (reason) { accountError.value = errorMessage(reason, t('common.error')) }
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
          <div class="field"><label for="map-theme">{{ t('settings.mapTheme') }}</label><AppSelect id="map-theme" :model-value="mapThemeMode" @update:model-value="changeMapTheme"><option value="auto">{{ t('settings.mapThemeAuto') }}</option><option value="light">{{ t('settings.light') }}</option><option value="dark">{{ t('settings.dark') }}</option></AppSelect><small class="field-hint">{{ t('settings.mapThemeHint') }}</small></div>
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
            <div><strong>{{ session.current ? t('settings.currentSession') : (session.user_agent || t('settings.unknownClient')) }}</strong><small>{{ session.ip_address || '—' }} · {{ formatInstant(session.last_seen_at) }}</small></div>
            <button v-if="!session.current" class="link-button" @click="revokeSession(session.id)">{{ t('settings.revokeSession') }}</button>
          </li>
        </ul>
      </div>
    </section>

  </div>
</template>

<style scoped>

.account-facts{display:grid;gap:7px;margin:0}
.account-facts>div{display:flex;align-items:baseline;gap:12px}
.account-facts dt{min-width:110px;color:var(--muted);font-size:var(--font-caption)}
.account-facts dd{margin:0;font-size:var(--font-body);font-weight:500}

.password-form{display:grid;gap:12px}
.password-actions{display:flex;align-items:center;gap:16px}

.session-list{list-style:none;margin:0;padding:0;display:grid}
.session-list li{display:flex;align-items:center;justify-content:space-between;gap:14px;padding:10px 0;border-bottom:1px solid var(--line)}
.session-list li:first-child{padding-top:0}
.session-list li:last-child{border-bottom:0;padding-bottom:0}
.session-list strong{display:block;font-size:var(--font-body);font-weight:500}
.session-list small{display:block;margin-top:2px;color:var(--muted);font-size:var(--font-caption)}

.people-list{list-style:none;margin:0;padding:0;display:grid}
.people-list li{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 12px;padding:10px 0;border-bottom:1px solid var(--line)}
.people-list li:first-child{padding-top:0}
.person{min-width:0}
.person strong{display:block;overflow:hidden;font-size:var(--font-body);font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.person strong span{color:var(--muted);font-weight:400}
.person small{display:block;margin-top:2px;overflow:hidden;color:var(--muted);font-size:var(--font-caption);text-overflow:ellipsis;white-space:nowrap}
.person-tag{padding:2px 7px;color:var(--accent);background:var(--accent-soft);border-radius:var(--radius-sm);font-size:var(--font-micro)}
.person-actions{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:14px}
.person-form{display:grid;gap:14px}
.person-form .form-actions{justify-content:flex-end;margin-top:2px}
.check{display:flex;align-items:center;gap:8px;font-size:var(--font-body);cursor:pointer}
.check input{width:14px;height:14px;accent-color:var(--accent)}
.diagnostics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:14px;margin:0}
.diagnostics-grid dt{color:var(--muted);font-size:var(--font-caption)}
.diagnostics-grid dd{margin:3px 0 0;font-size:var(--font-section);font-weight:500}

</style>
