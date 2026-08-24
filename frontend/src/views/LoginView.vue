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
      <div class="brand large"><BrandMark :size="42" /><span>{{ APP_NAME }}</span></div>
      <div>
        <span class="eyebrow">{{ t('auth.eyebrow') }}</span>
        <h1>{{ t('auth.headline') }}<br><em>{{ t('auth.headlineAccent') }}</em></h1>
        <p>{{ t('app.description') }}. {{ t('auth.privacy') }}</p>
      </div>
      <div class="signal-grid" aria-hidden="true"><i v-for="index in 36" :key="index" /></div>
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
.login-page { min-height:100vh; display:grid; grid-template-columns:minmax(380px,1.2fr) minmax(360px,.8fr); }
.login-story { position:relative; overflow:hidden; padding:50px clamp(35px,6vw,90px); display:flex; flex-direction:column; justify-content:space-between; color:#f7f5f2; background:radial-gradient(circle at 90% 12%,rgba(255,100,40,.18),transparent 24rem),linear-gradient(145deg,#171715,#090909); border-right:1px solid var(--line); }
.brand.large { padding:0; color:#fff; font-size:24px; }
.login-story h1 { font-size:clamp(38px,5.4vw,74px); line-height:1.04; letter-spacing:-.06em; margin:14px 0 20px; max-width:850px; }.login-story h1 em { color:var(--accent); font-style:normal; }.login-story p { max-width:590px; color:#aaa9a4; font-size:17px; line-height:1.7; }
.signal-grid { position:absolute; right:-80px; bottom:-80px; width:440px; height:440px; display:grid; grid-template-columns:repeat(6,1fr); opacity:.24; transform:rotate(-12deg); }.signal-grid i { border:1px solid #d85a28; border-radius:50%; margin:10px; animation:pulse 3s infinite alternate; }.signal-grid i:nth-child(3n) { animation-delay:1s; }
.login-form-wrap { display:grid; place-items:center; padding:40px; }.login-form { width:min(100%,420px); display:grid; gap:18px; }.login-form h2 { font-size:30px; margin:0; letter-spacing:-.04em; }.login-form p { margin:-9px 0 10px; }.login-button { margin-top:5px; padding:13px; }.mode-switch { border:0;background:none;color:var(--muted);cursor:pointer;font-size:12px; }.mode-switch:hover { color:var(--accent); }
@keyframes pulse { to { transform:scale(.65); opacity:.25; } }
@media(max-width:800px){.login-page{display:block}.login-story{min-height:280px;padding:28px 24px}.login-story h1{font-size:38px}.login-story p{display:none}.login-form-wrap{padding:35px 22px}.brand.large{display:flex}.signal-grid{width:240px;height:240px}}
</style>
