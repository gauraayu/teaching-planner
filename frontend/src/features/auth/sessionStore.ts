/**
 * Session persistence abstraction.
 *
 * Stores the session token issued by POST /api/auth/login. The rest of the app reads
 * the session through `useAuth()`; the role is always re-read from the server (/api/me),
 * so editing this storage cannot grant another role.
 */
import type { Role } from '@/types/domain'

export type StoredSession = {
  accessToken: string
  expiresAt: number
  userId: string
  role: Role
  displayName: string
}

const KEY = 'atp.session.v1'
type Listener = (s: StoredSession | null) => void
const listeners = new Set<Listener>()

function read(): StoredSession | null {
  try {
    const raw = localStorage.getItem(KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as StoredSession
    if (!s.accessToken || s.expiresAt * 1000 < Date.now()) return null
    return s
  } catch {
    return null
  }
}

export const sessionStore = {
  get: read,
  set(s: StoredSession) {
    try {
      localStorage.setItem(KEY, JSON.stringify(s))
    } catch {
      /* storage unavailable (private mode): session lives in memory for this tab */
    }
    listeners.forEach((l) => l(s))
  },
  clear() {
    try {
      localStorage.removeItem(KEY)
    } catch {
      /* ignore */
    }
    listeners.forEach((l) => l(null))
  },
  /** Called by the API client on 401 so every screen returns to sign-in. */
  expire() {
    if (read()) this.clear()
  },
  subscribe(l: Listener) {
    listeners.add(l)
    return () => {
      listeners.delete(l)
    }
  },
}
