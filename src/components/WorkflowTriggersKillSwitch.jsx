import { useCallback, useEffect, useState } from 'react'
import { AlertTriangle, Zap } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function WorkflowTriggersKillSwitch() {
  const { authFetch, role } = useAuth()
  const isAdmin = role === 'Admin'
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/workflows/triggers/status')
      if (!res.ok) throw new Error(`status ${res.status}`)
      setStatus(await res.json())
      setError('')
    } catch {
      setError('Could not load workflow trigger status')
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  async function toggle() {
    if (!isAdmin || !status) return
    setBusy(true)
    try {
      const res = await authFetch('/api/workflows/triggers/kill-switch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: !status.triggers_enabled }),
      })
      if (!res.ok) throw new Error('toggle failed')
      setStatus(await res.json())
    } catch {
      setError('Failed to update kill switch')
    } finally {
      setBusy(false)
    }
  }

  const enabled = status?.triggers_enabled !== false

  return (
    <div className="rounded-xl border border-amber-500/40 bg-amber-500/5 p-4 space-y-3">
      <div className="flex items-center gap-2">
        <Zap className="w-4 h-4 text-amber-300" />
        <h3 className="text-sm font-semibold text-white">Workflow automatic triggers</h3>
      </div>
      <p className="text-xs text-slate-300 leading-relaxed">
        Global kill switch for schedule and event-driven workflows. Turning this off stops all
        automatic workflow execution. Manual Run from the Workflows page still works.
      </p>
      {!enabled ? (
        <div className="flex items-start gap-2 rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-2 text-xs text-rose-200">
          <AlertTriangle className="w-3.5 h-3.5 mt-0.5 shrink-0" />
          Automatic triggers are OFF. Schedules and events will not start workflows.
        </div>
      ) : null}
      {error ? <p className="text-xs text-rose-400">{error}</p> : null}
      <div className="flex items-center justify-between gap-3">
        <div className="text-xs text-slate-400">
          State:{' '}
          <span className={enabled ? 'text-emerald-300' : 'text-rose-300'}>
            {enabled ? 'ENABLED' : 'DISABLED'}
          </span>
          {typeof status?.scheduled_job_count === 'number' ? (
            <span className="ml-2">· {status.scheduled_job_count} scheduled jobs</span>
          ) : null}
        </div>
        {isAdmin ? (
          <button
            type="button"
            disabled={busy || !status}
            onClick={() => void toggle()}
            className={`rounded-lg px-3 py-1.5 text-xs font-medium ${
              enabled
                ? 'bg-rose-600 text-white hover:bg-rose-500'
                : 'bg-emerald-600 text-white hover:bg-emerald-500'
            } disabled:opacity-40`}
          >
            {busy ? 'Updating…' : enabled ? 'Turn OFF automatic triggers' : 'Turn ON automatic triggers'}
          </button>
        ) : (
          <span className="text-xs text-slate-500">Admin only</span>
        )}
      </div>
    </div>
  )
}
