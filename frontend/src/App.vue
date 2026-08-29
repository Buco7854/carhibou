<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'
import { isAdmin } from './access'
import { auth, logout } from './api/auth'
import { APP_NAME } from './branding'
import AppIcon from './components/AppIcon.vue'
import AppSelect from './components/AppSelect.vue'
import BrandMark from './components/BrandMark.vue'
import { persistLocale } from './i18n'
import { resolvedTheme, setTheme } from './theme'

const router = useRouter()
const { locale, t } = useI18n()
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

interface NavEntry { to: string; icon: string; label: string; short?: string; exact?: boolean }

/**
 * The navigation, once, for both shapes of it.
 *
 * The rail lists everything. The phone's bar has room for five touch targets and
 * no more, so four entries are marked primary and the rest live behind More,
 * which also carries the account and the tools the rail keeps in its foot. The
 * primary four never depend on the account's role: an administrator has two
 * extra destinations, and letting them into the bar is what made it wrap.
 */
const primaryNav = computed<NavEntry[]>(() => [
  { to: '/', icon: 'grid', label: t('nav.dashboards'), short: t('nav.short.dashboards'), exact: true },
  { to: '/vehicles', icon: 'vehicle', label: t('nav.vehicles'), short: t('nav.short.vehicles') },
  { to: '/data-sources', icon: 'agent', label: t('nav.dataSources'), short: t('nav.short.dataSources') },
  { to: '/profiles', icon: 'profile', label: t('nav.profiles'), short: t('nav.short.profiles') },
])

const secondaryNav = computed<NavEntry[]>(() => [
  ...(isAdmin.value ? [{ to: '/hooks', icon: 'hooks', label: t('nav.hooks') }] : []),
  { to: '/settings', icon: 'settings', label: t('nav.settings') },
  ...(isAdmin.value ? [{ to: '/admin', icon: 'shield', label: t('admin.title') }] : []),
])

const moreOpen = ref(false)
function closeMore(): void { moreOpen.value = false }
// Navigating is the end of the sheet's job, however the route was reached.
watch(() => router.currentRoute.value.fullPath, closeMore)
</script>

<template>
  <RouterView v-if="!auth.user" />
  <div v-else class="app-shell">
    <aside class="sidebar">
      <RouterLink class="brand" to="/" aria-label="Carhibou">
        <BrandMark :size="40" />
        <strong>{{ APP_NAME }}</strong>
      </RouterLink>

      <nav class="main-nav" :aria-label="t('nav.sections')">
        <RouterLink v-for="item in primaryNav" :key="item.to" :to="item.to" :exact-active-class="item.exact ? 'active' : ''" :title="item.label">
          <AppIcon :name="item.icon" :size="17" />
          <span class="nav-label">{{ item.label }}</span>
          <span class="nav-label-short">{{ item.short }}</span>
        </RouterLink>
        <span class="nav-divider" />
        <RouterLink v-for="item in secondaryNav" :key="item.to" class="nav-secondary" :to="item.to" :title="item.label">
          <AppIcon :name="item.icon" :size="17" />
          <span class="nav-label">{{ item.label }}</span>
        </RouterLink>
        <!-- The bar's fifth target. It exists only where the bar does. -->
        <button class="nav-more" type="button" :aria-expanded="moreOpen" aria-controls="nav-sheet" @click="moreOpen = !moreOpen">
          <AppIcon name="more" :size="17" />
          <span class="nav-label-short">{{ t('nav.more') }}</span>
        </button>
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

    <!-- Everything the bar has no room for, plus the account and tools the rail
         keeps in its foot and the phone had no way to reach at all. -->
    <Teleport to="body">
      <div v-if="moreOpen" class="nav-sheet-backdrop" @pointerdown.self="closeMore" />
      <section
        v-if="moreOpen"
        id="nav-sheet"
        class="nav-sheet"
        role="dialog"
        :aria-label="t('nav.more')"
        @keydown.esc="closeMore"
      >
        <RouterLink v-for="item in secondaryNav" :key="item.to" :to="item.to" class="nav-sheet-link">
          <AppIcon :name="item.icon" :size="17" />{{ item.label }}
        </RouterLink>
        <div class="nav-sheet-account">
          <span class="avatar">{{ initials }}</span>
          <span class="account-id"><strong>{{ auth.user.display_name }}</strong><small>{{ auth.user.email }}</small></span>
        </div>
        <div class="nav-sheet-tools">
          <AppSelect compact :model-value="locale" :aria-label="t('settings.language')" @update:model-value="changeLocale"><option value="en">EN</option><option value="fr">FR</option></AppSelect>
          <button class="button secondary" type="button" @click="toggleTheme"><AppIcon name="theme" :size="16" />{{ t('settings.theme') }}</button>
          <button class="button secondary" type="button" @click="signOut"><AppIcon name="signout" :size="16" />{{ t('nav.signOut') }}</button>
        </div>
      </section>
    </Teleport>
  </div>
</template>
