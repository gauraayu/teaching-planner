import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api } from '@/services/api'
import type { Role, SessionInfo } from '@/types/domain'
import { sessionStore } from './sessionStore'

type AuthState = {
  session: SessionInfo | null
  status: 'loading' | 'signed-in' | 'signed-out'
  user: SessionInfo['user'] | null
  role: Role | null
  isAuthenticated: boolean
  /** Email, username or employee ID + password. The role comes back from the server; it is never chosen here. */
  login: (identifier: string, password: string) => Promise<SessionInfo>
  changePassword: (currentPassword: string, newPassword: string) => Promise<void>
  logout: () => void
  /** Permission check - UI visibility only; the backend enforces the same rules. */
  can: (permission: string) => boolean
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthState | null>(null)

export const HOME_BY_ROLE: Record<Role, string> = {
  ADMIN: '/admin/dashboard',
  PROFESSOR: '/professor/dashboard',
  CL_CH: '/verification/dashboard',
  OM: '/om/dashboard',
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null)
  // Start as 'loading' on server and client alike; the session is read from storage after mount.
  const [status, setStatus] = useState<AuthState['status']>('loading')

  const refresh = useCallback(async () => {
    if (!sessionStore.get()) {
      setSession(null)
      setStatus('signed-out')
      return
    }
    try {
      const { data } = await api.get<SessionInfo>('/me')
      setSession(data)
      setStatus('signed-in')
    } catch {
      sessionStore.clear()
      setSession(null)
      setStatus('signed-out')
    }
  }, [])

  useEffect(() => {
    void refresh()
    return sessionStore.subscribe((s) => {
      if (!s) {
        setSession(null)
        setStatus('signed-out')
      }
    })
  }, [refresh])

  const login = useCallback(async (identifier: string, password: string) => {
    const { data } = await api.post<SessionInfo & { access_token: string; expires_at: number }>('/auth/login', { identifier, password })
    sessionStore.set({ accessToken: data.access_token, expiresAt: data.expires_at, userId: data.user.id, role: data.role, displayName: data.user.full_name })
    setSession(data)
    setStatus('signed-in')
    return data
  }, [])

  const changePassword = useCallback(async (currentPassword: string, newPassword: string) => {
    // Changing the password ends every older session, so the server hands back a fresh token for this one.
    const { data } = await api.post<SessionInfo & { access_token: string; expires_at: number }>('/auth/change-password', { current_password: currentPassword, new_password: newPassword })
    sessionStore.set({ accessToken: data.access_token, expiresAt: data.expires_at, userId: data.user.id, role: data.role, displayName: data.user.full_name })
    setSession(data)
  }, [])

  const logout = useCallback(() => {
    sessionStore.clear()
  }, [])

  const value = useMemo<AuthState>(
    () => ({ session, status, user: session?.user ?? null, role: session?.role ?? null, isAuthenticated: !!session, login, changePassword, logout, refresh, can: (p) => !!session?.permissions.includes(p) }),
    [session, status, login, changePassword, logout, refresh],
  )
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
