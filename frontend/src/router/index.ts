import { createRouter, createWebHistory } from 'vue-router'
import { auth, loadUser } from '../api/auth'
import LoginView from '../views/LoginView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true } },
    { path: '/', name: 'dashboard', component: () => import('../views/DashboardView.vue') },
    { path: '/vehicles', name: 'vehicles', component: () => import('../views/VehiclesView.vue') },
    { path: '/vehicles/:id/history', name: 'history', component: () => import('../views/HistoryView.vue') },
    { path: '/dashboards', name: 'dashboards', component: () => import('../views/DashboardsView.vue') },
    { path: '/hooks', name: 'hooks', component: () => import('../views/HooksView.vue') },
    { path: '/devices', name: 'devices', component: () => import('../views/DevicesView.vue') },
    { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
  ],
})

router.beforeEach(async (to) => {
  if (!auth.ready) await loadUser()
  if (!to.meta.public && !auth.user) return { name: 'login', query: { next: to.fullPath } }
  if (to.name === 'login' && auth.user) return { name: 'dashboard' }
  return true
})

export default router
