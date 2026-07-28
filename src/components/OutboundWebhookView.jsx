import { Link } from 'react-router-dom'
import { Loader2, RefreshCw, Webhook, Wrench } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

export default function OutboundWebhookView() {
  const { authFetch } = useAuth()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    try {
      const res = await authFetch('/api/outbound-webhook/status')
      if (res.status === 400) {
        setNotConnected(true)
        setStatus(null)
        return
      }
      if (!res.ok) throw new Error(await res.text())
      setStatus(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load outbound webhook status')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !status && !notConnected) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading outbound webhook…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-4 md:p-6 max-w-5xl mx-auto">
        <h1 className="text-lg font-semibold text-white mb-4">Outbound Webhook</h1>
        <div className="flex flex-col items-center justify-center py-16 px-6 text-center border border-dashed border-border rounded-xl bg-card/40">
          <Wrench className="w-8 h-8 text-slate-500 mb-3" />
          <p className="text-sm font-semibold text-slate-200">Outbound Webhook not connected</p>
          <p className="text-xs text-slate-500 mt-1 max-w-sm">
            Store the customer URL as the account instance URL in Tool Registry. Used for incident created / approval needed events.
          </p>
          <Link
            to="/tool-registry"
            className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25"
          >
            Connect Outbound Webhook in Tool Registry
          </Link>
        </div>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            <Webhook className="w-5 h-5 text-accent" /> Outbound Webhook
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">
            First-class connector · deliver portal events to a customer URL
          </p>
        </div>
        <button
          type="button"
          onClick={() => load()}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-400 hover:text-white"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>
      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}
      <div className="rounded-xl border border-border bg-card/40 p-4 text-sm text-slate-300 space-y-1">
        <p>
          Status:{' '}
          <span className={status?.ok ? 'text-emerald-400' : 'text-amber-400'}>
            {status?.ok ? 'configured' : 'check failed'}
          </span>
        </p>
        {status?.url_host && (
          <p className="text-xs text-slate-500 font-mono">Host: {status.url_host}</p>
        )}
        <p className="text-xs text-slate-500">
          Writes use <code className="text-slate-400">POST /api/outbound-webhook/deliver</code> (Admin or HITL).
        </p>
      </div>
    </div>
  )
}
