import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

/**
 * SSO handoff page — IdP redirects here with #token=...
 */
export default function AuthCallback() {
  const navigate = useNavigate()
  const { setSessionFromToken } = useAuth()
  const [error, setError] = useState(null)

  useEffect(() => {
    const hash = window.location.hash || ''
    const params = new URLSearchParams(hash.replace(/^#/, ''))
    const token = params.get('token')
    if (!token) {
      setError('Missing SSO token. Sign in again.')
      return
    }
    try {
      if (typeof setSessionFromToken === 'function') {
        setSessionFromToken(token)
      } else {
        localStorage.setItem('aiops_access_token', token)
      }
      navigate('/dashboard', { replace: true })
    } catch (e) {
      setError(e?.message || 'Failed to complete SSO login')
    }
  }, [navigate, setSessionFromToken])

  if (error) {
    return (
      <div className="min-h-screen flex flex-col items-center justify-center gap-3 bg-surface px-4">
        <p className="text-sm text-red-400">{error}</p>
        <a href="/login" className="text-xs text-accent hover:underline">
          Back to login
        </a>
      </div>
    )
  }

  return (
    <div className="min-h-screen flex items-center justify-center gap-2 bg-surface text-slate-400 text-sm">
      <Loader2 className="w-4 h-4 animate-spin" /> Completing sign-in…
    </div>
  )
}
