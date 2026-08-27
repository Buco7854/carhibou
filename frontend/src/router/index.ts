import { createRouter, createWebHistory } from 'vue-router'
import { auth, loadUser } from '../api/auth'
import { isAdmin } from '../access'
import LoginView from '../views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'dashboards', component: () => import('../views/DashboardsView.vue') },
    { path: '/vehicles', name: 'vehicles', component: () => import('../views/VehiclesView.vue') },
    { path: '/profiles', name: 'profiles', component: () => import('../views/ProfilesView.vue') },
    { path: '/vehicles/:id/history', name: 'history', component: () => import('../views/HistoryView.vue') },
    { path: '/dashboards', redirect: '/' },
    // Hooks execute privileged Python in the worker, so they are instance
    // administration, not something a per-vehicle grant can extend to.
    { path: '/hooks', name: 'hooks', component: () => import('../views/HooksView.vue'), meta: { admin: true } },
    { path: '/data-sources', name: 'data-sources', component: () => import('../views/DataSourcesView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
    { path: '/admin', name: 'admin', component: () => import('../views/AdminView.vue'), meta: { admin: true } },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.ready) await loadUser()
  if (!to.meta.public && !auth.user) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && auth.user) return { name: 'dashboards' }
  // Administration is a different job from preferences, so it is a different page
  // and one an ordinary account has no route into.
  if (to.meta.admin && !isAdmin.value) return { name: 'settings' }
  return true
})

export default router
