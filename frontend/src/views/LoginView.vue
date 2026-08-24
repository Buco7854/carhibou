<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../api/auth'
import { APP_NAME } from '../branding'
import AppIcon from '../components/AppIcon.vue'
import BrandMark from '../components/BrandMark.vue'
import { persistLocale, type SupportedLocale } from '../i18n'
import { resolvedTheme, setTheme } from '../theme'

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const busy = ref(false)
const router = useRouter()
const route = useRoute()
const { locale, t } = useI18n()

function changeLocale(event: Event): void {
  const value = (event.target as HTMLSelectElement).value as SupportedLocale
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
    <section class="login-story">
      <div class="brand large"><BrandMark :size="42" /><span class="brand-copy"><strong>{{ APP_NAME }}</strong><small>{{ t('app.description') }}</small></span></div>
      <div class="story-copy">
        <span class="eyebrow">{{ t('auth.eyebrow') }}</span>
        <h1>{{ t('auth.headline') }} <em>{{ t('auth.headlineAccent') }}</em></h1>
        <p>{{ t('auth.privacy') }}</p>
      </div>
      <ol class="data-path">
        <li><span>01</span><div><strong>{{ t('auth.pathVehicle') }}</strong><small>{{ t('auth.pathVehicleHint') }}</small></div></li>
        <li><span>02</span><div><strong>{{ t('auth.pathNode') }}</strong><small>{{ t('auth.pathNodeHint') }}</small></div></li>
        <li><span>03</span><div><strong>{{ t('auth.pathHooks') }}</strong><small>{{ t('auth.pathHooksHint') }}</small></div></li>
      </ol>
    </section>
    <section class="login-form-wrap">
      <div class="login-utilities"><select class="topbar-select" :value="locale" :aria-label="t('settings.language')" @change="changeLocale"><option value="en">EN</option><option value="fr">FR</option></select><button class="topbar-button" :title="t('settings.theme')" @click="toggleTheme"><AppIcon name="theme" :size="18" /></button></div>
      <form class="login-form" @submit.prevent="submit">
        <span class="eyebrow">{{ mode === 'login' ? t('auth.welcome') : t('auth.firstIgnition') }}</span>
        <h2>{{ mode === 'login' ? t('auth.signInTitle') : t('auth.registerTitle') }}</h2>
        <p class="muted">{{ mode === 'login' ? t('auth.signInHint') : t('auth.registerHint') }}</p>
        <div v-if="mode === 'register'" class="field"><label for="name">{{ t('auth.displayName') }}</label><input id="name" v-model="displayName" class="input" required /></div>
        <div class="field"><label for="email">{{ t('auth.email') }}</label><input id="email" v-model="email" class="input" type="email" autocomplete="email" required /></div>
        <div class="field"><label for="password">{{ t('auth.password') }}</label><input id="password" v-model="password" class="input" type="password" :minlength="mode === 'register' ? 12 : 1" autocomplete="current-password" required /></div>
        <p v-if="error" class="error" role="alert">{{ error }}</p>
        <button class="button login-button" :disabled="busy">{{ busy ? t('auth.connecting') : mode === 'login' ? t('auth.signIn') : t('auth.create') }}</button>
        <button class="mode-switch" type="button" @click="mode = mode === 'login' ? 'register' : 'login'">{{ mode === 'login' ? t('auth.switchRegister') : t('auth.switchLogin') }}</button>
      </form>
    </section>
  </main>
</template>

<style scoped>
.login-page{width:min(100%,1320px);min-height:calc(100vh - clamp(40px,6vw,92px));margin:0 auto;display:grid;grid-template-columns:minmax(280px,360px) minmax(360px,1fr);overflow:hidden;background:var(--workspace);border:1px solid rgba(255,255,255,.38);border-radius:22px;box-shadow:0 32px 80px rgba(31,39,51,.3)}
.login-story{padding:31px 29px;display:flex;flex-direction:column;background:var(--sidebar);border-right:1px solid var(--line)}.brand.large{padding:0;color:var(--text)}.brand.large .brand-copy small{max-width:180px}.story-copy{margin:auto 0 45px}.login-story h1{max-width:290px;margin:11px 0 14px;font-size:clamp(31px,3.5vw,46px);font-weight:500;letter-spacing:-.055em;line-height:1.08}.login-story h1 em{color:var(--accent);font-style:normal}.login-story p{max-width:270px;color:var(--muted);font-size:12px;line-height:1.6}
.data-path{position:relative;margin:0;padding:0;list-style:none}.data-path::before{content:"";position:absolute;top:16px;bottom:16px;left:14px;width:2px;background:var(--accent)}.data-path li{position:relative;display:grid;grid-template-columns:30px 1fr;align-items:center;gap:11px;min-height:56px}.data-path li>span{z-index:1;width:30px;height:30px;display:grid;place-items:center;color:var(--accent);background:var(--sidebar);border:1px solid var(--accent);border-radius:50%;font-family:"IBM Plex Mono",monospace;font-size:8px}.data-path strong,.data-path small{display:block}.data-path strong{font-size:11px}.data-path small{margin-top:2px;color:var(--muted);font-size:9px}
.login-form-wrap{position:relative;display:grid;place-items:center;padding:60px 38px 38px;background:var(--workspace)}.login-utilities{position:absolute;top:22px;right:24px;display:flex;gap:8px}.login-form{width:min(100%,390px);display:grid;gap:17px}.login-form h2{margin:0;font-size:30px;font-weight:600;letter-spacing:-.04em}.login-form p{margin:-8px 0 9px}.login-button{margin-top:5px;padding:12px}.mode-switch{border:0;background:none;color:var(--muted);cursor:pointer;font-size:10px}.mode-switch:hover{color:var(--accent)}
@media(max-width:760px){.login-page{min-height:100vh;display:block;border:0;border-radius:0}.login-story{min-height:240px;padding:24px 22px}.story-copy{margin:40px 0 0}.login-story h1{max-width:500px;font-size:34px}.login-story p{display:none}.data-path{display:none}.login-form-wrap{min-height:520px;padding:76px 22px 34px}.brand.large{display:flex}}
</style>
