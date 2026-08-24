<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { auth, logout } from './api/auth'
import { APP_NAME } from './branding'

const router = useRouter()
const { t } = useI18n()
const initials = computed(() => auth.user?.display_name.slice(0, 2).toUpperCase() ?? '')

async function signOut() {
  await logout()
  await router.push({ name: 'login' })
}
</script>

<template>
  <RouterView v-if="!auth.user" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/" aria-label="VehiNode dashboard">
        <span class="brand-mark">V</span>
        <span>{{ APP_NAME }}</span>
      </RouterLink>
      <nav class="main-nav" aria-label="Main navigation">
        <RouterLink to="/" exact-active-class="active"><span>⌁</span> {{ t('nav.dashboard') }}</RouterLink>
        <RouterLink to="/vehicles"><span>◈</span> {{ t('nav.vehicles') }}</RouterLink>
        <RouterLink to="/dashboards"><span>▦</span> {{ t('nav.dashboards') }}</RouterLink>
        <RouterLink to="/hooks"><span>⌘</span> {{ t('nav.hooks') }}</RouterLink>
        <RouterLink to="/devices"><span>◉</span> {{ t('nav.devices') }}</RouterLink>
        <RouterLink to="/settings"><span>⚙</span> {{ t('nav.settings') }}</RouterLink>
      </nav>
      <div class="account">
        <div class="avatar">{{ initials }}</div>
        <div><strong>{{ auth.user.display_name }}</strong><small>{{ auth.user.email }}</small></div>
        <button class="icon-button" :title="t('nav.signOut')" @click="signOut">↗</button>
      </div>
    </aside>
    <main class="main-content"><RouterView /></main>
  </div>
</template>
