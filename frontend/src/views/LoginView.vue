<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { authMethods, login, register, registrationIsOpen } from '../api/auth'
import { APP_NAME } from '../branding'
import AppIcon from '../components/AppIcon.vue'
import AppSelect from '../components/AppSelect.vue'
import BrandMark from '../components/BrandMark.vue'
import { persistLocale } from '../i18n'
import { resolvedTheme, setTheme } from '../theme'

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const displayName = ref('')
const registrationOpen = ref(false)
const oidc = ref<{ enabled: boolean; name: string }>({ enabled: false, name: '' })
const error = ref('')
const busy = ref(false)
const router = useRouter()
const route = useRoute()
const { locale, t } = useI18n()

onMounted(async () => {
  // authMethods already degrades to password-only when the endpoint is unreachable.
  const methods = authMethods()
  try {
    registrationOpen.value = await registrationIsOpen()
    if (registrationOpen.value) mode.value = 'register'
  } catch {
    // A configured account can still sign in if the optional setup check is unavailable.
  }
  oidc.value = (await methods).oidc
})

function ssoLogin(): void {
  // A full-page redirect: the OIDC flow ends by setting the same session cookie
  // password login sets, so the app is simply re-entered signed in.
  window.location.href = '/api/v1/auth/oidc/login'
}

function changeLocale(value: string | number | null): void {
  if (value !== 'en' && value !== 'fr') return
  locale.value = value
  persistLocale(value)
}

function toggleTheme(): void {
  setTheme(resolvedTheme.value === 'dark' ? 'light' : 'dark')
}

async function submit() {
  error.value = ''; busy.value = true
  try {
    if (mode.value === 'login') await login(email.value, password.value)
    else await register(email.value, password.value, displayName.value)
    await router.push(String(route.query.next ?? '/'))
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : 'Authentication failed'
  } finally { busy.value = false }
}
</script>

<template>
  <main class="login-page">
    <div class="login-utilities">
      <AppSelect compact :model-value="locale" :aria-label="t('settings.language')" @update:model-value="changeLocale"><option value="en">EN</option><option value="fr">FR</option></AppSelect>
      <button class="tool-button" type="button" :title="t('settings.theme')" @click="toggleTheme"><AppIcon name="theme" :size="17" /></button>
    </div>

    <section class="login-card">
      <div class="login-brand">
        <BrandMark :size="36" />
        <div><strong>{{ APP_NAME }}</strong><small>{{ t('auth.workspaceTitle') }}</small></div>
      </div>

      <form class="login-form" @submit.prevent="submit">
        <h1>{{ mode === 'login' ? t('auth.signInTitle') : t('auth.registerTitle') }}</h1>
        <p class="login-hint">{{ mode === 'login' ? t('auth.signInHint') : t('auth.registerHint') }}</p>
        <button v-if="oidc.enabled" class="button secondary sso-button" type="button" @click="ssoLogin">{{ t('auth.continueWith', { name: oidc.name }) }}</button>
        <div v-if="mode === 'register'" class="field"><label for="name">{{ t('auth.displayName') }}</label><input id="name" v-model="displayName" class="input" required /></div>
        <div class="field"><label for="email">{{ t('auth.email') }}</label><input id="email" v-model="email" class="input" type="email" autocomplete="email" required /></div>
        <div class="field"><label for="password">{{ t('auth.password') }}</label><input id="password" v-model="password" class="input" type="password" :minlength="mode === 'register' ? 12 : 1" :autocomplete="mode === 'register' ? 'new-password' : 'current-password'" required /></div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="button login-button" :disabled="busy">{{ busy ? t('auth.connecting') : mode === 'login' ? t('auth.signIn') : t('auth.create') }}</button>
        <button v-if="registrationOpen" class="link-button mode-switch" type="button" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? t('auth.switchRegister') : t('auth.switchLogin') }}</button>
      </form>
    </section>

    <p class="login-foot">{{ t('auth.openSource') }}</p>
  </main>
</template>

<style scoped>
.login-page{position:relative;width:100%;min-height:100vh;display:grid;grid-template-rows:1fr auto;justify-items:center;padding:64px 20px 20px;background:var(--workspace)}
.login-utilities{position:absolute;top:16px;right:18px;display:flex;align-items:center;gap:4px}

.login-card{width:min(100%,380px);align-self:center;display:grid;gap:28px}

/* The mark stands alone above the card, the way a sign-in door carries the
   nameplate: centred, quiet, no copy beyond the product's own name. */
.login-brand{display:grid;justify-items:center;gap:12px;text-align:center}
.login-brand strong,.login-brand small{display:block}
.login-brand strong{font-size:var(--font-card-title);font-weight:600;letter-spacing:-.01em}
.login-brand small{margin-top:2px;color:var(--muted);font-size:var(--font-caption)}

.login-form{display:grid;gap:14px;padding:24px;background:var(--panel);border:1px solid var(--line);border-radius:var(--radius-lg);box-shadow:var(--shadow-soft)}
.login-form h1{margin:0;font-size:var(--font-subtitle);font-weight:600;letter-spacing:-.01em}
.login-hint{margin:-9px 0 3px;color:var(--muted);font-size:var(--font-body)}
.login-button{width:100%;height:36px;margin-top:4px}
.sso-button{width:100%;height:36px}
.mode-switch{justify-self:center;color:var(--muted);font-size:var(--font-caption);transition:color .12s}
.mode-switch:hover{color:var(--accent)}

.login-foot{margin:32px 0 0;color:var(--muted);font-size:var(--font-caption);text-align:center}

@media(max-width:520px){.login-page{padding-top:56px}}
</style>
