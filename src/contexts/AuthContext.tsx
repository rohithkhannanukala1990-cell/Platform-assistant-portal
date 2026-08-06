import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { getPortalContextHeaders } from '../utils/portalContextHeaders'
import { API_BASE } from '../config/apiBase'
import { getGlobalToast } from '../components/ToastNotification'
import { safeLoginError } from '../utils/parseApiError'
import type { AuthUser, LoginResult } from '../types/api'

type JwtPayload = { exp?: number; [key: string]: unknown }

function parseJWT(token: string): JwtPayload | null {
  try {
    if (!token || typeof token !== 'string') return null
    const parts = token.split('.')
    if (parts.length !== 3) return null

    const base64Url = parts[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const json = atob(padded)
    return JSON.parse(json) as JwtPayload
  } catch {
    return null
  }
}

function isTokenExpired(token: string): boolean {
  const payload = parseJWT(token)
  const exp = payload?.exp
  if (!exp || typeof exp !== 'number') return true
  return exp <= Date.now() / 1000
}

function loadStoredToken(): string | null {
  try {
    const token = localStorage.getItem('aiops_access_token')
    if (!token || isTokenExpired(token)) {
      localStorage.removeItem('aiops_access_token')
      return null
    }
    return token
  } catch {
    return null
  }
}

export interface AuthFetchOptions extends RequestInit {
  silentToast?: boolean
}

export interface AuthContextValue {
  user: AuthUser | null
  role: string | null
  token: string | null
  isAuthenticated: boolean
  loading: boolean
  error: string | null
  login: (username: string, password: string, totpCode?: string) => Promise<LoginResult>
  logout: () => Promise<void>
  authFetch: (url: string, options?: AuthFetchOptions) => Promise<Response>
  setSessionFromToken: (accessToken: string) => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [token, setToken] = useState<string | null>(() => loadStoredToken())
  const [user, setUser] = useState<AuthUser | null>(null)
  const [role, setAuthRole] = useState<string | null>(null)
  const [loading, setLoading] = useState(() => !!loadStoredToken())
  const [error, setError] = useState<string | null>(null)

  const logout = useCallback(async () => {
    const current = token
    try {
      if (current) {
        await fetch(`${API_BASE}/api/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${current}` },
        }).catch(() => {})
      }
    } catch {
      /* ignore */
    }
    try {
      localStorage.removeItem('aiops_access_token')
    } catch {
      /* ignore */
    }
    setToken(null)
    setUser(null)
    setAuthRole(null)
  }, [token])

  const setSessionFromToken = useCallback((accessToken: string) => {
    if (!accessToken) return
    try {
      localStorage.setItem('aiops_access_token', accessToken)
    } catch {
      /* ignore */
    }
    setToken(accessToken)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function hydrate() {
      if (!token) {
        setLoading(false)
        return
      }

      setLoading(true)
      setError(null)

      try {
        const res = await fetch(`${API_BASE}/auth/me`, {
          headers: { Authorization: `Bearer ${token}` },
        })

        if (!res.ok) throw new Error('Unauthorized')

        const data = (await res.json()) as AuthUser
        if (cancelled) return

        setUser(data)
        setAuthRole(data.role ?? null)
      } catch {
        if (cancelled) return
        void logout()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void hydrate()
    return () => {
      cancelled = true
    }
  }, [token, logout])

  const login = useCallback(async (username: string, password: string, totpCode?: string) => {
    setError(null)

    try {
      const res = await fetch(`${API_BASE}/auth/login`, {
        method: 'POST',
        body: (() => {
          const form = new FormData()
          form.append('username', username)
          form.append('password', password)
          if (totpCode) form.append('totp_code', totpCode)
          return form
        })(),
      })

      const data = (await res.json().catch(() => ({}))) as {
        access_token?: string
        username?: string
        role?: string
        detail?: unknown
      }
      if (!res.ok) {
        const detail = data?.detail
        const code =
          typeof detail === 'object' && detail && 'code' in (detail as object)
            ? String((detail as { code?: string }).code)
            : null
        let message =
          typeof detail === 'string'
            ? detail
            : typeof detail === 'object' && detail && 'message' in (detail as object)
              ? String((detail as { message?: string }).message)
              : Array.isArray(detail)
                ? detail.map((d) => (typeof d === 'object' && d && 'msg' in d ? String((d as { msg?: string }).msg) : String(d))).join(', ')
                : 'Login failed'

        message = safeLoginError(message, {
          isProd: import.meta.env.PROD || import.meta.env.MODE === 'production',
        })

        if (code === 'mfa_enrollment_required') {
          setError(message)
          return { success: false, error: message, mfaEnrollmentRequired: true }
        }
        if (res.status === 401 && (message === 'MFA code required' || /mfa code required/i.test(message))) {
          return {
            success: false,
            error: 'MFA required — enter your authenticator code below',
            mfaRequired: true,
          }
        }
        setError(message)
        return { success: false, error: message }
      }

      try {
        if (data.access_token) localStorage.setItem('aiops_access_token', data.access_token)
      } catch {
        /* ignore */
      }

      if (data.access_token) setToken(data.access_token)
      setUser({ username: data.username, role: data.role })
      setAuthRole(data.role ?? null)

      return { success: true, role: data.role ?? null }
    } catch (e) {
      const message = e instanceof Error ? e.message : 'Login failed'
      setError(message)
      return { success: false, error: message }
    }
  }, [])

  const authFetch = useCallback(
    async (url: string, options: AuthFetchOptions = {}) => {
      const { silentToast, ...fetchOptions } = options
      const fullUrl = /^https?:\/\//i.test(url) ? url : `${API_BASE}${url}`
      const headers = new Headers(fetchOptions.headers || {})
      if (token) headers.set('Authorization', `Bearer ${token}`)
      const portalHeaders = getPortalContextHeaders()
      Object.entries(portalHeaders).forEach(([k, v]) => {
        if (v != null && v !== '') headers.set(k, String(v))
      })

      const method = (fetchOptions.method || 'GET').toUpperCase()
      const isAgentsRun =
        method === 'POST' &&
        /\/api\/agents\/run\/?$/.test(new URL(fullUrl, window.location.origin).pathname)

      const res = await fetch(fullUrl, { ...fetchOptions, headers })

      if (res.status === 401) {
        getGlobalToast()?.error?.('Session expired. Please log in again.')
        void logout()
        throw new Error('Session expired')
      }

      if (isAgentsRun && !silentToast) {
        const api = getGlobalToast()
        if (api) {
          try {
            const data = (await res.clone().json()) as {
              status?: string
              requires_approval?: boolean
              detail?: unknown
            }
            if (res.ok) {
              const pending =
                data?.status === 'pending_approval' || data?.requires_approval === true
              api.success(
                pending
                  ? 'Agent run submitted — awaiting approval'
                  : 'Agent run completed successfully'
              )
            } else {
              const detail =
                typeof data?.detail === 'string'
                  ? data.detail
                  : Array.isArray(data?.detail)
                    ? data.detail
                        .map((d) =>
                          typeof d === 'object' && d && 'msg' in d
                            ? String((d as { msg?: string }).msg)
                            : String(d)
                        )
                        .join(', ')
                    : 'Agent run failed'
              api.error(detail || 'Agent run failed')
            }
          } catch {
            if (!res.ok) api.error('Agent run failed')
          }
        }
      }

      return res
    },
    [token, logout]
  )

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      role,
      token,
      isAuthenticated: !!(token && role) && !loading,
      loading,
      error,
      login,
      logout,
      authFetch,
      setSessionFromToken,
    }),
    [user, role, token, loading, error, login, logout, authFetch, setSessionFromToken]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
