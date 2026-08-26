<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { auth, logout } from './api/auth'
import { APP_NAME } from './branding'
import AppIcon from './components/AppIcon.vue'
import AppSelect from './components/AppSelect.vue'
import BrandMark from './components/BrandMark.vue'
import { persistLocale } from './i18n'
import { resolvedTheme, setTheme } from './theme'

const router = useRouter()
const { locale, t } = useI18n()
const isAdmin = computed(() => Boolean(auth.user?.permissions['system.admin']))
const initials = computed(() => auth.user?.display_name.slice(0, 2).toUpperCase() ?? '')

function changeLocale(value: string | number | null): void {
  if (value !== 'en' && value !== 'fr') return
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
      <RouterLink class="brand" to="/" aria-label="VehiNode">
        <BrandMark :size="24" />
        <strong>{{ APP_NAME }}</strong>
      </RouterLink>

      <nav class="main-nav" :aria-label="t('nav.sections')">
        <RouterLink to="/" exact-active-class="active" :title="t('nav.dashboards')"><AppIcon name="grid" :size="17" /><span class="nav-label">{{ t('nav.dashboards') }}</span></RouterLink>
        <RouterLink to="/vehicles" :title="t('nav.vehicles')"><AppIcon name="vehicle" :size="17" /><span class="nav-label">{{ t('nav.vehicles') }}</span></RouterLink>
        <RouterLink to="/profiles" :title="t('nav.profiles')"><AppIcon name="profile" :size="17" /><span class="nav-label">{{ t('nav.profiles') }}</span></RouterLink>
        <RouterLink to="/hooks" :title="t('nav.hooks')"><AppIcon name="hooks" :size="17" /><span class="nav-label">{{ t('nav.hooks') }}</span></RouterLink>
        <RouterLink to="/devices" :title="t('nav.devices')"><AppIcon name="devices" :size="17" /><span class="nav-label">{{ t('nav.devices') }}</span></RouterLink>
        <span class="nav-divider" />
        <RouterLink to="/settings" :title="t('nav.settings')"><AppIcon name="settings" :size="17" /><span class="nav-label">{{ t('nav.settings') }}</span></RouterLink>
        <RouterLink v-if="isAdmin" to="/admin" :title="t('admin.title')"><AppIcon name="profile" :size="17" /><span class="nav-label">{{ t('admin.title') }}</span></RouterLink>
      </nav>

      <div class="sidebar-foot">
        <div class="account">
          <span class="avatar">{{ initials }}</span>
          <span class="account-id"><strong>{{ auth.user.display_name }}</strong><small>{{ auth.user.email }}</small></span>
        </div>
        <div class="sidebar-tools">
          <AppSelect compact :model-value="locale" :aria-label="t('settings.language')" @update:model-value="changeLocale"><option value="en">EN</option><option value="fr">FR</option></AppSelect>
          <button class="tool-button" type="button" :title="t('settings.theme')" @click="toggleTheme"><AppIcon name="theme" :size="17" /></button>
          <button class="tool-button" type="button" :title="t('nav.signOut')" @click="signOut"><AppIcon name="signout" :size="17" /></button>
        </div>
      </div>
    </aside>

    <section class="workspace">
      <main class="main-content"><RouterView /></main>
    </section>
  </div>
</template>
