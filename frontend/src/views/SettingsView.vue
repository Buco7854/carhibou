<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { api } from '../api/client'
import { auth } from '../api/auth'
import type { BrowserSession, Diagnostics } from '../api/types'
import AppSelect from '../components/AppSelect.vue'
import { persistLocale } from '../i18n'
import { setTheme, themeMode } from '../theme'

const { locale, t } = useI18n()
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

onMounted(async () => {
  sessions.value = await api<BrowserSession[]>('/auth/sessions')
  if (auth.user?.permissions['system.admin']) {
    try { diagnostics.value = await api<Diagnostics>('/system/diagnostics') } catch { /* health remains visible through direct endpoint */ }
  }
})
</script>

<template>
  <div class="page max-w-4xl">
    <header class="page-header"><div><span class="eyebrow">{{ t('settings.eyebrow') }}</span><h1>{{ t('settings.title') }}</h1></div></header>
    <div class="grid gap-4 md:grid-cols-2">
      <section class="panel panel-pad">
        <h2 class="mt-0 text-lg font-bold">{{ t('settings.appearance') }}</h2>
        <div class="mt-5 grid gap-5">
          <div class="field"><label for="theme">{{ t('settings.theme') }}</label><AppSelect id="theme" :model-value="themeMode" @update:model-value="changeTheme"><option value="auto">{{ t('settings.auto') }}</option><option value="light">{{ t('settings.light') }}</option><option value="dark">{{ t('settings.dark') }}</option></AppSelect></div>
          <div class="field"><label for="locale">{{ t('settings.language') }}</label><AppSelect id="locale" :model-value="locale" @update:model-value="changeLocale"><option value="en">{{ t('settings.english') }}</option><option value="fr">{{ t('settings.french') }}</option></AppSelect></div>
          <p class="muted m-0 text-xs">{{ t('settings.saved') }}</p>
        </div>
      </section>
      <section class="panel panel-pad">
        <h2 class="mt-0 text-lg font-bold">{{ t('settings.account') }}</h2>
        <dl class="mt-5 grid grid-cols-[auto_1fr] gap-x-4 gap-y-3 text-sm"><dt class="muted">{{ t('auth.displayName') }}</dt><dd class="m-0 font-semibold">{{ auth.user?.display_name }}</dd><dt class="muted">{{ t('auth.email') }}</dt><dd class="m-0 font-semibold">{{ auth.user?.email }}</dd></dl>
        <p class="muted mt-6 text-xs leading-5">{{ t('settings.sessionHint') }}</p>
      </section>
      <section class="panel panel-pad">
        <h2 class="mt-0 text-lg font-bold">{{ t('settings.changePassword') }}</h2>
        <form class="mt-5 grid gap-3" @submit.prevent="changePassword"><label class="field"><span>{{ t('settings.currentPassword') }}</span><input v-model="currentPassword" class="input" type="password" autocomplete="current-password" required /></label><label class="field"><span>{{ t('settings.newPassword') }}</span><input v-model="newPassword" class="input" type="password" minlength="12" autocomplete="new-password" required /></label><p v-if="accountError" class="error m-0">{{ accountError }}</p><p v-if="accountMessage" class="success m-0 text-xs">{{ accountMessage }}</p><button class="button justify-self-start">{{ t('settings.changePassword') }}</button></form>
      </section>
      <section class="panel panel-pad">
        <h2 class="mt-0 text-lg font-bold">{{ t('settings.activeSessions') }}</h2>
        <ul class="session-list"><li v-for="session in sessions" :key="session.id"><div><strong>{{ session.current ? t('settings.currentSession') : (session.user_agent || t('settings.unknownClient')) }}</strong><small>{{ session.ip_address || '—' }} · {{ new Date(session.last_seen_at).toLocaleString() }}</small></div><button v-if="!session.current" class="button secondary text-xs" @click="revokeSession(session.id)">{{ t('settings.revokeSession') }}</button></li></ul>
      </section>
      <section v-if="diagnostics" class="panel panel-pad md:col-span-2">
        <h2 class="mt-0 text-lg font-bold">{{ t('settings.diagnostics') }}</h2>
        <dl class="diagnostics-grid"><div><dt>{{ t('settings.version') }}</dt><dd>{{ diagnostics.version }}</dd></div><div><dt>{{ t('settings.database') }}</dt><dd>{{ diagnostics.database }}</dd></div><div><dt>{{ t('settings.workers') }}</dt><dd>{{ diagnostics.workers.length }}</dd></div><div><dt>{{ t('settings.pendingJobs') }}</dt><dd>{{ diagnostics.pending_jobs }}</dd></div><div><dt>{{ t('settings.failedJobs') }}</dt><dd>{{ diagnostics.failed_jobs }}</dd></div><div><dt>{{ t('settings.hookFailures') }}</dt><dd>{{ diagnostics.hook_failures }}</dd></div><div><dt>{{ t('settings.staleDevices') }}</dt><dd>{{ diagnostics.stale_devices }}</dd></div></dl>
      </section>
    </div>
  </div>
</template>

<style scoped>.diagnostics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:10px}.diagnostics-grid div{padding:12px;background:var(--panel-2);border-radius:9px}.diagnostics-grid dt{color:var(--muted);font-size:9px;text-transform:uppercase}.diagnostics-grid dd{margin:5px 0 0;font:500 17px "IBM Plex Mono",monospace}.session-list{list-style:none;margin:13px 0 0;padding:0;display:grid;gap:7px}.session-list li{display:flex;align-items:center;justify-content:space-between;gap:11px;padding:10px;background:var(--panel-2);border-radius:9px}.session-list strong,.session-list small{display:block;font-size:10px}.session-list small{color:var(--muted);margin-top:4px;font-size:8px}</style>
