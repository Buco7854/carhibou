<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { api } from '../api/client'
import { auth, logout } from '../api/auth'
import type { BrowserSession, Diagnostics, UserAccount } from '../api/types'
import AppIcon from '../components/AppIcon.vue'
import AppModal from '../components/AppModal.vue'
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
const people = ref<UserAccount[]>([])
const peopleError = ref('')
const creating = ref(false)
const saving = ref(false)
const emptyPerson = () => ({ email: '', display_name: '', password: '', is_admin: false })
const person = ref(emptyPerson())
const isAdmin = computed(() => Boolean(auth.user?.permissions['system.admin']))

async function loadPeople(): Promise<void> {
  if (!isAdmin.value) return
  people.value = await api<UserAccount[]>('/users')
}

async function createPerson(): Promise<void> {
  peopleError.value = ''
  saving.value = true
  try {
    await api<UserAccount>('/users', { method: 'POST', body: JSON.stringify(person.value) })
    creating.value = false
    person.value = emptyPerson()
    await loadPeople()
  } catch (reason) {
    peopleError.value = reason instanceof Error ? reason.message : t('common.error')
  } finally {
    saving.value = false
  }
}

async function updatePerson(account: UserAccount, changes: Partial<UserAccount>): Promise<void> {
  peopleError.value = ''
  try {
    await api<UserAccount>(`/users/${account.id}`, { method: 'PATCH', body: JSON.stringify(changes) })
    await loadPeople()
  } catch (reason) {
    peopleError.value = reason instanceof Error ? reason.message : t('common.error')
  }
}

async function removePerson(account: UserAccount): Promise<void> {
  if (!window.confirm(t('settings.deleteUserConfirm', { name: account.display_name }))) return
  peopleError.value = ''
  try {
    await api<void>(`/users/${account.id}`, { method: 'DELETE' })
    await loadPeople()
  } catch (reason) {
    peopleError.value = reason instanceof Error ? reason.message : t('common.error')
  }
}

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
  await loadPeople()
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

    <section v-if="isAdmin" class="settings-block">
      <div class="settings-label"><h2>{{ t('settings.users') }}</h2><p>{{ t('settings.usersHint') }}</p></div>
      <div class="settings-body">
        <p v-if="peopleError" class="error" role="alert">{{ peopleError }}</p>
        <ul class="people-list">
          <li v-for="account in people" :key="account.id">
            <div class="person">
              <strong>{{ account.display_name }}<span v-if="account.id === auth.user?.id"> · {{ t('settings.you') }}</span></strong>
              <small>{{ account.email }}</small>
            </div>
            <span v-if="account.is_admin" class="person-tag">{{ t('settings.administrator') }}</span>
            <span :class="['status', { online: account.is_active }]">{{ account.is_active ? t('settings.activeAccount') : t('settings.inactiveAccount') }}</span>
            <div class="person-actions">
              <button class="link-button" type="button" @click="updatePerson(account, { is_admin: !account.is_admin })">{{ account.is_admin ? t('settings.revokeAdmin') : t('settings.makeAdmin') }}</button>
              <button class="link-button" type="button" @click="updatePerson(account, { is_active: !account.is_active })">{{ account.is_active ? t('settings.suspend') : t('settings.restore') }}</button>
              <button class="link-button danger" type="button" @click="removePerson(account)">{{ t('common.delete') }}</button>
            </div>
          </li>
        </ul>
        <button class="button secondary" type="button" @click="creating = true"><AppIcon name="plus" :size="15" />{{ t('settings.addUser') }}</button>
      </div>
    </section>

    <AppModal :open="creating" :title="t('settings.addUser')" @close="creating = false">
      <form class="person-form" @submit.prevent="createPerson">
        <label class="field"><span>{{ t('auth.displayName') }}</span><input v-model="person.display_name" class="input" required autofocus /></label>
        <label class="field"><span>{{ t('auth.email') }}</span><input v-model="person.email" class="input" type="email" required /></label>
        <label class="field"><span>{{ t('auth.password') }}</span><input v-model="person.password" class="input" type="password" minlength="12" required /></label>
        <label class="check"><input v-model="person.is_admin" type="checkbox" /><span>{{ t('settings.administrator') }}</span></label>
        <p v-if="peopleError" class="error" role="alert">{{ peopleError }}</p>
        <div class="form-actions"><button class="button" :disabled="saving">{{ t('settings.createUser') }}</button><button class="button ghost" type="button" @click="creating = false">{{ t('common.cancel') }}</button></div>
      </form>
    </AppModal>

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

.people-list{list-style:none;margin:0;padding:0;display:grid}
.people-list li{display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:8px 12px;padding:10px 0;border-bottom:1px solid var(--line)}
.people-list li:first-child{padding-top:0}
.person{min-width:0}
.person strong{display:block;overflow:hidden;font-size:13px;font-weight:500;text-overflow:ellipsis;white-space:nowrap}
.person strong span{color:var(--muted);font-weight:400}
.person small{display:block;margin-top:2px;overflow:hidden;color:var(--muted);font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.person-tag{padding:2px 7px;color:var(--accent);background:var(--accent-soft);border-radius:4px;font-size:11px}
.person-actions{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:14px}
.settings-body>.button{justify-self:start}
.person-form{display:grid;gap:14px}
.person-form .form-actions{justify-content:flex-end;margin-top:2px}
.check{display:flex;align-items:center;gap:8px;font-size:13px;cursor:pointer}
.check input{width:14px;height:14px;accent-color:var(--accent)}
.diagnostics-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:14px;margin:0}
.diagnostics-grid dt{color:var(--muted);font-size:12px}
.diagnostics-grid dd{margin:3px 0 0;font-size:15px;font-weight:500}

@media(max-width:760px){
  .settings-block{grid-template-columns:1fr;gap:14px}
  .settings-pair{grid-template-columns:1fr}
}
</style>
