<script setup lang="ts">
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { login, register } from '../api/auth'
import { APP_NAME } from '../branding'
import BrandMark from '../components/BrandMark.vue'

const mode = ref<'login' | 'register'>('login')
const email = ref('')
const password = ref('')
const displayName = ref('')
const error = ref('')
const busy = ref(false)
const router = useRouter()
const route = useRoute()
const { t } = useI18n()

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
      <div class="brand large"><BrandMark :size="42" /><span class="brand-copy"><strong>{{ APP_NAME }}</strong><small>{{ t('nav.telemetryNode') }}</small></span></div>
      <div>
        <span class="eyebrow">{{ t('auth.eyebrow') }}</span>
        <h1>{{ t('auth.headline') }}<br><em>{{ t('auth.headlineAccent') }}</em></h1>
        <p>{{ t('app.description') }}. {{ t('auth.privacy') }}</p>
      </div>
      <div class="signal-grid" aria-hidden="true"><i v-for="index in 36" :key="index" :style="{ height: `${10 + ((index * 17) % 64)}%` }" /></div>
    </section>
    <section class="login-form-wrap">
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
.login-page{min-height:100vh;display:grid;grid-template-columns:minmax(420px,1.15fr) minmax(360px,.85fr);background:var(--workspace)}
.login-story{position:relative;overflow:hidden;padding:46px clamp(34px,6vw,86px);display:flex;flex-direction:column;justify-content:space-between;color:#edf4ed;background:#143a36;border-right:1px solid #2c5a54}.login-story::after{content:"";position:absolute;inset:0;background:linear-gradient(118deg,transparent 0 62%,rgba(183,212,59,.055) 62% 63%,transparent 63%);pointer-events:none}
.brand.large{z-index:1;padding:0;color:#edf4ed}.brand.large .brand-copy small{color:#91afa8}
.login-story>div:nth-child(2){position:relative;z-index:1;max-width:780px}.login-story h1{max-width:850px;margin:13px 0 19px;font-family:"Barlow Condensed",sans-serif;font-size:clamp(52px,6.2vw,88px);font-weight:600;letter-spacing:-.025em;line-height:.87;text-transform:uppercase}.login-story h1 em{color:#c6df56;font-style:normal}.login-story p{max-width:570px;color:#a9c0ba;font-size:14px;line-height:1.65}
.signal-grid{position:absolute;right:clamp(20px,5vw,80px);bottom:44px;width:min(470px,52%);height:92px;display:flex;align-items:flex-end;gap:5px;padding:15px 0;border-block:1px solid rgba(198,223,86,.22);opacity:.8}.signal-grid::before{content:"TELEMETRY / LOCAL";position:absolute;top:-17px;left:0;color:#83a39b;font-family:"IBM Plex Mono",monospace;font-size:7px;letter-spacing:.12em}.signal-grid i{flex:1;min-height:3px;background:#58b8b0;animation:sample-pulse 3.8s ease-in-out infinite alternate}.signal-grid i:nth-child(4n){background:#c6df56}.signal-grid i:nth-child(3n){animation-delay:.7s}
.login-form-wrap{display:grid;place-items:center;padding:40px;background:var(--workspace)}.login-form{width:min(100%,400px);display:grid;gap:18px}.login-form h2{margin:0;font-family:"Barlow Condensed",sans-serif;font-size:38px;font-weight:600;line-height:1;text-transform:uppercase}.login-form p{margin:-9px 0 10px}.login-button{margin-top:5px;padding:13px}.mode-switch{border:0;background:none;color:var(--muted);cursor:pointer;font-family:"IBM Plex Mono",monospace;font-size:8px;text-transform:uppercase}.mode-switch:hover{color:var(--petrol)}
@keyframes sample-pulse{to{opacity:.4;transform:scaleY(.72);transform-origin:bottom}}
@media(max-width:800px){.login-page{display:block}.login-story{min-height:310px;padding:26px 23px}.login-story h1{font-size:48px}.login-story p{display:none}.login-form-wrap{padding:34px 22px}.brand.large{display:grid}.signal-grid{right:23px;bottom:24px;width:55%;height:58px}}
</style>
