import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { api, ApiError, subscribeUnauthorized } from '../api/client'
import { ROLES, type Role, type User } from '../api/types'

interface Ctx {
  user: User | null; ready: boolean
  login: (email: string, password: string, remember: boolean) => Promise<void>
  logout: () => Promise<void>
  can: (min: Role) => boolean
  refresh: () => Promise<void>
}
const AuthCtx = createContext<Ctx | null>(null)

export function can(role: Role | undefined, min: Role) {
  if (!role) return false
  return ROLES.indexOf(role) >= ROLES.indexOf(min)
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [ready, setReady] = useState(false)

  const refresh = useCallback(async () => {
    try { setUser(await api.get<User>('/auth/me', { silent401: true })) }
    catch (e) { if (e instanceof ApiError && e.status === 401) setUser(null); else throw e }
  }, [])

  useEffect(() => { refresh().catch(() => {}).finally(() => setReady(true)) }, [refresh])
  useEffect(() => subscribeUnauthorized(() => setUser(null)), [])

  const value = useMemo<Ctx>(() => ({
    user, ready, refresh,
    login: async (email, password, remember) => { setUser(await api.post<User>('/auth/login', { email, password, remember })) },
    logout: async () => { try { await api.post('/auth/logout') } finally { setUser(null) } },
    can: (min) => can(user?.role, min),
  }), [user, ready, refresh])
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export function useAuth() {
  const c = useContext(AuthCtx)
  if (!c) throw new Error('useAuth fora do AuthProvider')
  return c
}
