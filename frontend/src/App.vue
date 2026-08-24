<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import { auth, logout } from './api/auth'
import { APP_NAME } from './branding'
import AppIcon from './components/AppIcon.vue'
import BrandMark from './components/BrandMark.vue'
import { persistLocale, type SupportedLocale } from './i18n'
import { resolvedTheme, setTheme } from './theme'

const router = useRouter()
const route = useRoute()
const { locale, t } = useI18n()
const initials = computed(() => auth.user?.display_name.slice(0, 2).toUpperCase() ?? '')
const section = computed(() => {
  const name = String(route.name ?? 'dashboard')
  if (name === 'history') return { index: '02.1', label: t('history.title') }
  const mapped = ['dashboard', 'vehicles', 'dashboards', 'hooks', 'devices', 'settings'].includes(name) ? name : 'dashboard'
  const indexes: Record<string, string> = { dashboard: '01', vehicles: '02', dashboards: '03', hooks: '04', devices: '05', settings: '06' }
  return { index: indexes[mapped] ?? '01', label: t(`nav.${mapped}`) }
})

function changeLocale(event: Event): void {
  const value = (event.target as HTMLSelectElement).value as SupportedLocale
  locale.value = value
  persistLocale(value)
}

function toggleTheme(): void {
  setTheme(resolvedTheme.value === 'dark' ? 'light' : 'dark')
}

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
        <BrandMark />
        <span class="brand-copy"><strong>{{ APP_NAME }}</strong><small>{{ t('nav.telemetryNode') }}</small></span>
      </RouterLink>
      <div class="nav-group-label">{{ t('nav.workspace') }}</div>
      <nav class="main-nav" :aria-label="t('nav.workspace')">
        <RouterLink to="/" exact-active-class="active" :title="t('nav.dashboard')"><AppIcon name="dashboard" /><span class="nav-label">{{ t('nav.dashboard') }}</span></RouterLink>
        <RouterLink to="/vehicles" :title="t('nav.vehicles')"><AppIcon name="vehicle" /><span class="nav-label">{{ t('nav.vehicles') }}</span></RouterLink>
        <RouterLink to="/dashboards" :title="t('nav.dashboards')"><AppIcon name="grid" /><span class="nav-label">{{ t('nav.dashboards') }}</span></RouterLink>
        <RouterLink to="/hooks" :title="t('nav.hooks')"><AppIcon name="hooks" /><span class="nav-label">{{ t('nav.hooks') }}</span></RouterLink>
        <RouterLink to="/devices" :title="t('nav.devices')"><AppIcon name="devices" /><span class="nav-label">{{ t('nav.devices') }}</span></RouterLink>
      </nav>
      <div class="nav-group-label system-label">{{ t('nav.system') }}</div>
      <nav class="main-nav" :aria-label="t('nav.system')">
        <RouterLink to="/settings" :title="t('nav.settings')"><AppIcon name="settings" /><span class="nav-label">{{ t('nav.settings') }}</span></RouterLink>
      </nav>
      <div class="sidebar-pulse"><span class="pulse-dot" /><div><strong>{{ t('nav.platformReady') }}</strong><small>{{ t('nav.platformReadyHint') }}</small></div></div>
      <div class="account">
        <div class="avatar">{{ initials }}</div>
        <div><strong>{{ auth.user.display_name }}</strong><small>{{ auth.user.email }}</small></div>
        <button class="icon-button" :title="t('nav.signOut')" @click="signOut"><AppIcon name="signout" :size="17" /></button>
      </div>
    </aside>
    <section class="workspace">
      <header class="topbar">
        <div class="section-title"><span class="section-index">{{ section.index }}</span><div><small>{{ t('nav.controlCenter') }}</small><strong>{{ section.label }}</strong></div></div>
        <div class="topbar-bus"><i />{{ t('nav.secureConnection') }}</div>
        <div class="topbar-actions">
          <select class="topbar-select" :value="locale" :aria-label="t('settings.language')" @change="changeLocale"><option value="en">EN</option><option value="fr">FR</option></select>
          <button class="topbar-button" :title="t('settings.theme')" @click="toggleTheme"><AppIcon name="theme" :size="18" /></button>
          <button class="topbar-avatar" :title="auth.user.email" @click="router.push('/settings')">{{ initials }}</button>
        </div>
      </header>
      <main class="main-content"><RouterView /></main>
    </section>
  </div>
</template>
