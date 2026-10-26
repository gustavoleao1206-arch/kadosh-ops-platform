import { createContext, useCallback, useContext, useEffect, useMemo, type ReactNode } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router'
import { api, ApiError, MUST_CHANGE_PASSWORD_EVENT, UNAUTHORIZED_EVENT } from '../api/client'
import type { User } from '../api/types'

interface AuthContextValue {
  user: User | null
  loading: boolean
  login: (email: string, senha: string) => Promise<User>
  logout: () => Promise<void>
  refresh: () => Promise<void>
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const qc = useQueryClient()
  const navigate = useNavigate()

  const me = useQuery<User | null>({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api<User>('/auth/me')
      } catch (e) {
        if (e instanceof ApiError && e.status === 401) return null
        throw e
      }
    },
    staleTime: 60_000,
    retry: false,
  })

  useEffect(() => {
    const onUnauthorized = () => {
      qc.setQueryData(['me'], null)
      qc.removeQueries({ predicate: (q) => q.queryKey[0] !== 'me' })
      const here = window.location.pathname + window.location.search
      if (!here.startsWith('/login')) navigate('/login', { replace: true, state: { from: here } })
    }
    const onMustChange = () => navigate('/trocar-senha', { replace: true })
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    window.addEventListener(MUST_CHANGE_PASSWORD_EVENT, onMustChange)
    return () => {
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
      window.removeEventListener(MUST_CHANGE_PASSWORD_EVENT, onMustChange)
    }
  }, [navigate, qc])

  const login = useCallback(
    async (email: string, senha: string) => {
      const res = await api<{ user: User }>('/auth/login', { method: 'POST', body: { email, senha, client: 'web' } })
      qc.setQueryData(['me'], res.user)
      return res.user
    },
    [qc],
  )

  const logout = useCallback(async () => {
    try {
      await api('/auth/logout', { method: 'POST' })
    } finally {
      qc.clear()
      navigate('/login', { replace: true })
    }
  }, [navigate, qc])

  const refresh = useCallback(async () => {
    await qc.invalidateQueries({ queryKey: ['me'] })
  }, [qc])

  const value = useMemo<AuthContextValue>(
    () => ({ user: me.data ?? null, loading: me.isLoading, login, logout, refresh }),
    [me.data, me.isLoading, login, logout, refresh],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth fora do AuthProvider')
  return ctx
}
