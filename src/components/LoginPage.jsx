import { useEffect, useState } from 'react'
import { Bot, Loader2, ShieldCheck, Eye, EyeOff } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'
import { safeLoginError } from '../utils/parseApiError'

export default function LoginPage() {
  const auth = useAuth()

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [totpCode, setTotpCode] = useState('')
  const [mfaRequired, setMfaRequired] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [localError, setLocalError] = useState(null)
  const [submitting, setSubmitting] = useState(false)
  const [sso, setSso] = useState({ saml: false, google: false, any: false })

  const isDev = import.meta.env.DEV
  const loading = submitting

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`${API_BASE}/api/auth/sso/status`)
        if (!res.ok) return
        const data = await res.json()
        if (!cancelled) setSso(data)
      } catch {
        /* SSO status optional */
      }
    })()
    return () => {
      cancelled = true
    }
  }, [])

  async function onSubmit(e) {
    e.preventDefault()
    setLocalError(null)

    if (!username.trim() || !password) {
      setLocalError('Username and password are required.')
      return
    }

    setSubmitting(true)
    try {
      const result = await auth.login(username.trim(), password, totpCode)
      if (!result?.success) {
        if (result?.mfaRequired) setMfaRequired(true)
        setLocalError(result?.error || 'Login failed')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const errText = safeLoginError(localError || auth.error, {
    isProd: import.meta.env.PROD || import.meta.env.MODE === 'production',
  })
  const displayError = (localError || auth.error) ? errText : null

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md rounded-2xl border border-border bg-sidebar shadow-2xl p-7">
        <div className="flex items-center gap-4 mb-6">
          <div className="w-11 h-11 rounded-xl bg-accent/15 border border-accent/30 flex items-center justify-center shrink-0">
            <Bot className="w-5 h-5 text-accent" strokeWidth={2.5} />
          </div>
          <div className="min-w-0">
            <h1 className="text-lg font-bold text-white tracking-tight">Platform Engineering</h1>
            <p className="text-sm text-slate-400">AIOps Assistant Portal</p>
          </div>
        </div>

        {displayError && (
          <div className="flex items-start gap-3 p-3.5 rounded-xl border border-red-500/30 bg-red-500/10 text-red-400 mb-5">
            <ShieldCheck className="w-4 h-4 shrink-0 mt-0.5" />
            <div className="text-sm leading-relaxed">
              {displayError}
            </div>
          </div>
        )}

        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-400">Username</label>
            <input
              type="text"
              autoComplete="username"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={loading}
              className="w-full rounded-xl border border-border bg-card px-4 py-3 text-sm text-slate-200 placeholder-slate-600 outline-none
                focus:border-accent/50 focus:ring-2 focus:ring-accent/20 disabled:opacity-60 disabled:cursor-not-allowed"
              placeholder="admin"
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="text-xs font-semibold text-slate-400">Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={loading}
                className="w-full rounded-xl border border-border bg-card px-4 py-3 pr-11 text-sm text-slate-200 placeholder-slate-600 outline-none
                  focus:border-accent/50 focus:ring-2 focus:ring-accent/20 disabled:opacity-60 disabled:cursor-not-allowed"
                placeholder="••••••••"
              />
              <button
                type="button"
                onClick={() => setShowPassword((v) => !v)}
                disabled={loading}
                className="absolute inset-y-0 right-0 px-3 flex items-center justify-center text-slate-500 hover:text-slate-200 transition-colors
                  disabled:opacity-60 disabled:cursor-not-allowed"
                title={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          {mfaRequired && (
            <div className="mt-3">
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="6-digit authenticator code"
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value)}
                className="w-full px-4 py-2 bg-card border border-yellow-500
                           rounded-lg text-white text-center tracking-widest
                           text-xl focus:outline-none focus:border-yellow-400"
              />
              <p className="text-yellow-400 text-xs mt-1 text-center">
                Open your authenticator app and enter the code
              </p>
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="mt-1 flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold bg-accent text-black
              hover:bg-green-400 active:scale-95 disabled:opacity-50 disabled:cursor-not-allowed disabled:scale-100 transition-all duration-150 glow-green"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Signing in…
              </>
            ) : (
              'Sign In'
            )}
          </button>

          {isDev && (
            <p className="text-xs text-slate-600 text-center mt-1">Default: admin / Admin123!</p>
          )}
        </form>

        {sso.any ? (
          <div className="mt-4 border-t border-slate-700 pt-4 space-y-2">
            <p className="text-xs text-slate-500 text-center mb-3">Or continue with</p>
            {sso.saml && (
              <a
                href={`${API_BASE}/api/auth/sso/saml/login`}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors"
              >
                SSO / SAML Login
              </a>
            )}
            {sso.google && (
              <a
                href={`${API_BASE}/api/auth/oauth/google`}
                className="flex items-center justify-center gap-2 w-full py-2.5 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 transition-colors"
              >
                Continue with Google
              </a>
            )}
          </div>
        ) : (
          <p className="mt-4 text-[11px] text-slate-600 text-center border-t border-slate-800 pt-4">
            SSO not configured
          </p>
        )}
      </div>
    </div>
  )
}
