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
.login-page{width:min(100%,1450px);min-height:calc(100vh - clamp(36px,8vw,128px));margin:0 auto;display:grid;grid-template-columns:minmax(390px,1.15fr) minmax(360px,.85fr);overflow:hidden;background:var(--workspace);border:5px solid color-mix(in srgb,white 80%,transparent);border-radius:30px;box-shadow:0 36px 90px rgba(32,39,52,.26)}
.login-story{position:relative;overflow:hidden;padding:45px clamp(34px,6vw,82px);display:flex;flex-direction:column;justify-content:space-between;color:#f7f5f2;background:radial-gradient(circle at 88% 16%,rgba(255,104,45,.18),transparent 23rem),linear-gradient(145deg,#181817,#090909);border-right:1px solid #2b2b29}.login-story::after{content:"";position:absolute;inset:0;background:linear-gradient(120deg,transparent 0 67%,rgba(255,104,45,.04) 67% 68%,transparent 68%);pointer-events:none}
.brand.large{z-index:1;padding:0;color:#fff}.brand.large .brand-copy small{color:#aaa9a4}
.login-story>div:nth-child(2){position:relative;z-index:1;max-width:760px}.login-story h1{max-width:820px;margin:13px 0 19px;font-size:clamp(42px,5.5vw,74px);font-weight:500;letter-spacing:-.055em;line-height:1.03}.login-story h1 em{color:var(--accent);font-style:normal}.login-story p{max-width:570px;color:#aaa9a4;font-size:14px;line-height:1.65}
.signal-grid{position:absolute;right:clamp(20px,5vw,76px);bottom:42px;width:min(450px,52%);height:88px;display:flex;align-items:flex-end;gap:5px;padding:14px 0;border-block:1px solid rgba(255,104,45,.23);opacity:.78}.signal-grid::before{content:"VEHICLE TELEMETRY";position:absolute;top:-17px;left:0;color:#777672;font-size:7px;letter-spacing:.1em}.signal-grid i{flex:1;min-height:3px;background:#ff682d;animation:sample-pulse 3.8s ease-in-out infinite alternate}.signal-grid i:nth-child(4n){background:#ff9a62}.signal-grid i:nth-child(3n){animation-delay:.7s}
.login-form-wrap{display:grid;place-items:center;padding:38px;background:var(--workspace)}.login-form{width:min(100%,390px);display:grid;gap:17px}.login-form h2{margin:0;font-size:29px;font-weight:600;letter-spacing:-.035em}.login-form p{margin:-8px 0 9px}.login-button{margin-top:5px;padding:12px}.mode-switch{border:0;background:none;color:var(--muted);cursor:pointer;font-size:10px}.mode-switch:hover{color:var(--accent)}
@keyframes sample-pulse{to{opacity:.4;transform:scaleY(.72);transform-origin:bottom}}
@media(max-width:800px){.login-page{min-height:100vh;display:block;border:0;border-radius:0}.login-story{min-height:300px;padding:26px 23px}.login-story h1{font-size:39px}.login-story p{display:none}.login-form-wrap{padding:34px 22px}.brand.large{display:grid}.signal-grid{right:23px;bottom:24px;width:55%;height:58px}}
</style>
