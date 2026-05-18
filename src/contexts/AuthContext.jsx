import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { getPortalContextHeaders } from '../utils/portalContextHeaders'
import { API_BASE } from '../config/apiBase'
import { getGlobalToast } from '../components/ToastNotification'

// ── PRIVATE HELPERS (not exported) ────────────────────────────────────────────
function parseJWT(token) {
  try {
    if (!token || typeof token !== 'string') return null
    const parts = token.split('.')
    if (parts.length !== 3) return null

    // Base64url decode the middle segment (payload)
    const base64Url = parts[1]
    const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/')
    const padded = base64.padEnd(base64.length + ((4 - (base64.length % 4)) % 4), '=')
    const json = atob(padded)
    return JSON.parse(json)
  } catch {
    return null
  }
}

function isTokenExpired(token) {
  const payload = parseJWT(token)
  const exp = payload?.exp
  if (!exp || typeof exp !== 'number') return true
  return exp <= Date.now() / 1000
}

function loadStoredToken() {
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

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [token, setToken] = useState(() => loadStoredToken())
  const [user, setUser] = useState(null)
  const [role, setAuthRole] = useState(null) // ALWAYS from server, NEVER computed client-side
  const [loading, setLoading] = useState(() => !!loadStoredToken())
  const [error, setError] = useState(null)

  const logout = useCallback(() => {
    try {
      localStorage.removeItem('aiops_access_token')
    } catch {
      // ignore storage failures
    }
    setToken(null)
    setUser(null)
    setAuthRole(null)
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

        const data = await res.json()
        if (cancelled) return

        setUser(data)
        setAuthRole(data.role ?? null)
      } catch {
        if (cancelled) return
        logout()
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    hydrate()
    return () => {
      cancelled = true
    }
  }, [token, logout])

  const login = useCallback(async (username, password, totpCode) => {
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

      const data = await res.json().catch(() => ({}))
      if (!res.ok) {
        if (res.status === 401 && !totpCode) {
          return { success: false, error: 'MFA required — enter your authenticator code below', mfaRequired: true }
        }
        const message = data?.detail || 'Login failed'
        setError(message)
        return { success: false, error: message }
      }

      try {
        localStorage.setItem('aiops_access_token', data.access_token)
      } catch {
        // ignore storage failures; token state still holds it for session
      }

      setToken(data.access_token)
      setUser({ username: data.username, role: data.role })
      setAuthRole(data.role)

      return { success: true, role: data.role }
    } catch (e) {
      const message = e?.message || 'Login failed'
      setError(message)
      return { success: false, error: message }
    }
  }, [])

  const authFetch = useCallback(
    async (url, options = {}) => {
      const fullUrl = /^https?:\/\//i.test(url) ? url : `${API_BASE}${url}`
      const headers = new Headers(options.headers || {})
      if (token) headers.set('Authorization', `Bearer ${token}`)
      const portalHeaders = getPortalContextHeaders()
      Object.entries(portalHeaders).forEach(([k, v]) => {
        if (v != null && v !== '') headers.set(k, String(v))
      })

      const method = (options.method || 'GET').toUpperCase()
      const isAgentsRun =
        method === 'POST' &&
        /\/api\/agents\/run\/?$/.test(new URL(fullUrl, window.location.origin).pathname)

      const res = await fetch(fullUrl, { ...options, headers })

      if (res.status === 401) {
        getGlobalToast()?.error?.('Session expired. Please log in again.')
        logout()
        throw new Error('Session expired')
      }

      if (isAgentsRun) {
        const api = getGlobalToast()
        if (api) {
          try {
            const data = await res.clone().json()
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
                    ? data.detail.map((d) => d.msg || d).join(', ')
                    : 'Agent run failed'
              api.error(detail)
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

  const value = useMemo(
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
    }),
    [user, role, token, loading, error, login, logout, authFetch]
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}

