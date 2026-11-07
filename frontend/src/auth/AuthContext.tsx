import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { api, tokens } from '../lib/api'
import type { User } from '../lib/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
  isRecruiter: boolean
  isAdmin: boolean
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient()
  const me = useQuery({
    queryKey: ['me'],
    queryFn: () => api<User>('/auth/me/'),
    enabled: Boolean(tokens.access),
    retry: false,
    staleTime: 5 * 60_000,
  })

  useEffect(() => {
    const handler = () => client.clear()
    window.addEventListener('hr:logout', handler)
    return () => window.removeEventListener('hr:logout', handler)
  }, [client])

  const login = useCallback(
    async (username: string, password: string) => {
      const data = await api<{ access: string; refresh: string }>('/auth/token/', { body: { username, password } })
      tokens.set(data.access, data.refresh)
      await client.invalidateQueries({ queryKey: ['me'] })
      await me.refetch()
    },
    [client, me],
  )

  const logout = useCallback(async () => {
    const refresh = tokens.refresh
    try {
      if (refresh) await api('/auth/logout/', { body: { refresh } })
    } catch {
      // Token may already be invalid; local logout still proceeds.
    }
    tokens.clear()
    client.clear()
    window.location.assign('/login')
  }, [client])

  const value = useMemo<AuthState>(() => {
    const user = tokens.access ? (me.data ?? null) : null
    const isAdmin = user?.role === 'ADMIN' || Boolean(user?.is_superuser)
    return {
      user,
      loading: Boolean(tokens.access) && me.isLoading,
      login,
      logout,
      isAdmin,
      isRecruiter: isAdmin || user?.role === 'RECRUITER',
    }
  }, [me.data, me.isLoading, login, logout])

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
