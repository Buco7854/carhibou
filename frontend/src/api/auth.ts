import { reactive } from 'vue'
import type { User } from './types'
import { APIError, api } from './client'

export const auth = reactive<{ user: User | null; ready: boolean }>({ user: null, ready: false })

export async function loadUser(): Promise<User | null> {
  try {
    auth.user = await api<User>('/auth/me')
  } catch (error) {
    if (!(error instanceof APIError) || error.status !== 401) throw error
    auth.user = null
  } finally {
    auth.ready = true
  }
  return auth.user
}

export async function login(email: string, password: string): Promise<void> {
  const response = await api<{ user: User; csrf_token: string }>('/auth/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
  })
  auth.user = response.user
}

export async function register(email: string, password: string, displayName: string): Promise<void> {
  const response = await api<{ user: User; csrf_token: string }>('/auth/register', {
    method: 'POST',
    body: JSON.stringify({ email, password, display_name: displayName }),
  })
  auth.user = response.user
}

export async function logout(): Promise<void> {
  await api('/auth/logout', { method: 'POST' })
  auth.user = null
}
