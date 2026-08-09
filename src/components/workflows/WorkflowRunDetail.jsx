import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Check, Loader2, RefreshCw, X } from 'lucide-react'
import { authFetch } from '../../utils/api'
import { PageHeader } from '../ui'

function GroundingBadge({ grounding }) {
  const g = (grounding || 'none').toLowerCase()
  const tone =
    g === 'live'
      ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
      : g === 'partial'
        ? 'bg-amber-500/15 text-amber-300 border-amber-500/30'
        : g === 'demo'
          ? 'bg-sky-500/15 text-sky-300 border-sky-500/30'
          : 'bg-slate-700/50 text-slate-300 border-slate-600/40'
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-[11px] uppercase tracking-wide ${tone}`}>
      {g}
    </span>
  )
}

function StatusDot({ status }) {
  const color =
    status === 'completed' || status === 'approved'
      ? 'bg-emerald-400'
      : status === 'pending_approval'
        ? 'bg-amber-400'
        : status === 'failed' || status === 'rejected'
          ? 'bg-rose-400'
          : status === 'running'
            ? 'bg-indigo-400'
            : 'bg-slate-500'
  return <span className={`mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full ${color}`} />
}

export default function WorkflowRunDetail() {
  const { runId } = useParams()
  const [run, setRun] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [rejectReason, setRejectReason] = useState('')

  const load = useCallback(async () => {
    if (!runId) return
    setLoading(true)
    setError('')
    try {
      const res = await authFetch(`/api/workflows/runs/${encodeURIComponent(runId)}`)
      if (!res.ok) throw new Error(res.status === 404 ? 'Run not found' : `Load failed (${res.status})`)
      setRun(await res.json())
    } catch (err) {
      setError(err?.message || 'Failed to load run')
    } finally {
      setLoading(false)
    }
  }, [runId])

  useEffect(() => {
    void load()
  }, [load])

  const steps = useMemo(() => {
    const defSteps = run?.workflow?.steps || []
    const state = run?.steps_state || {}
    if (defSteps.length) {
      return defSteps.map((s) => ({
        id: s.id,
        type: s.type,
        label: s.agent || s.connector || s.prompt || s.id,
        state: state[s.id] || { status: 'pending' },
      }))
    }
    return Object.entries(state).map(([id, st]) => ({
      id,
      type: st.type || 'step',
      label: id,
      state: st,
    }))
  }, [run])

  async function approve(stepId) {
    setBusy(true)
    setError('')
    try {
      const res = await authFetch(`/api/workflows/runs/${encodeURIComponent(runId)}/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || `Approve failed (${res.status})`)
      setRun(body)
    } catch (err) {
      setError(err?.message || 'Approve failed')
    } finally {
      setBusy(false)
    }
  }

  async function reject(stepId) {
    setBusy(true)
    setError('')
    try {
      const res = await authFetch(`/api/workflows/runs/${encodeURIComponent(runId)}/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ step_id: stepId, reason: rejectReason || 'Rejected' }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail || `Reject failed (${res.status})`)
      setRun(body)
    } catch (err) {
      setError(err?.message || 'Reject failed')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 text-slate-400">
        <Loader2 className="animate-spin" size={18} /> Loading run…
      </div>
    )
  }

  if (!run) {
    return (
      <div className="space-y-3 p-6">
        <p className="text-rose-300">{error || 'Run not found'}</p>
        <Link to="/workflows" className="text-sm text-indigo-300 hover:underline">
          Back to workflows
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title={`Run ${run.id.slice(0, 8)}…`}
        subtitle={`Status: ${run.status} · Workflow ${run.workflow_id}`}
        actions={
          <div className="flex items-center gap-3">
            <GroundingBadge grounding={run.grounding} />
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
            >
              <RefreshCw size={14} /> Refresh
            </button>
            <Link to="/workflows" className="text-sm text-slate-400 hover:text-slate-200">
              All workflows
            </Link>
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {run.error ? (
        <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 px-4 py-3 text-sm text-amber-100">
          {run.error}
        </div>
      ) : null}

      <div className="relative space-y-0 border-l border-slate-700/80 ml-3">
        {steps.map((step) => {
          const st = step.state || {}
          const pending = st.status === 'pending_approval'
          return (
            <div key={step.id} className="relative pl-8 pb-8">
              <div className="absolute -left-[5px] top-1">
                <StatusDot status={st.status || 'pending'} />
              </div>
              <div className="rounded-xl border border-slate-800 bg-slate-900/40 p-4">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-medium text-white">{step.id}</span>
                  <span className="text-xs uppercase tracking-wide text-slate-500">{step.type}</span>
                  <span className="text-xs text-slate-400">{st.status || 'pending'}</span>
                  <GroundingBadge grounding={st.grounding || (pending ? 'none' : run.grounding)} />
                </div>
                {st.prompt ? <p className="mt-2 text-sm text-slate-300">{st.prompt}</p> : null}
                {st.output ? (
                  <pre className="mt-3 max-h-48 overflow-auto rounded-lg bg-black/30 p-3 text-xs text-slate-300">
                    {JSON.stringify(st.output, null, 2)}
                  </pre>
                ) : null}
                {pending ? (
                  <div className="mt-4 flex flex-wrap items-center gap-2">
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void approve(step.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-emerald-500 disabled:opacity-40"
                    >
                      <Check size={12} /> Approve
                    </button>
                    <input
                      value={rejectReason}
                      onChange={(e) => setRejectReason(e.target.value)}
                      placeholder="Reject reason"
                      className="rounded-lg border border-slate-700 bg-slate-950 px-3 py-1.5 text-xs text-slate-200"
                    />
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void reject(step.id)}
                      className="inline-flex items-center gap-1 rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-rose-500 disabled:opacity-40"
                    >
                      <X size={12} /> Reject
                    </button>
                  </div>
                ) : null}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
