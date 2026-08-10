import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Play, Plus, RefreshCw, Workflow } from 'lucide-react'
import { authFetch } from '../../utils/api'
import { useAuth } from '../../contexts/AuthContext'
import { PageHeader, EmptyState } from '../ui'

export function RiskBadge({ risk }) {
  const tone =
    risk === 'high'
      ? 'text-rose-300 border-rose-500/40 bg-rose-500/10'
      : risk === 'low'
        ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
        : 'text-amber-300 border-amber-500/40 bg-amber-500/10'
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs capitalize ${tone}`}>
      {risk || 'medium'}
    </span>
  )
}

function TriggeredByBadge({ value }) {
  const label = value || 'manual'
  const tone = String(label).startsWith('event:')
    ? 'bg-sky-500/15 text-sky-300'
    : label === 'schedule'
      ? 'bg-violet-500/15 text-violet-300'
      : 'bg-slate-700/60 text-slate-300'
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs ${tone}`}>{label}</span>
  )
}

export default function WorkflowListPage() {
  const navigate = useNavigate()
  const { role } = useAuth()
  const isAdmin = role === 'Admin'
  const [rows, setRows] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [wfRes, runRes] = await Promise.all([
        authFetch('/api/workflows'),
        authFetch('/api/workflows/runs'),
      ])
      if (!wfRes.ok) throw new Error(`Failed to load workflows (${wfRes.status})`)
      const data = await wfRes.json()
      setRows(Array.isArray(data) ? data : [])
      if (runRes.ok) {
        const runData = await runRes.json()
        setRuns(Array.isArray(runData) ? runData : [])
      }
    } catch (err) {
      setError(err?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

  async function toggleEnabled(row) {
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: row.name,
          description: row.description || '',
          steps: row.steps || [],
          trigger_type: row.trigger_type || 'manual',
          trigger_config: row.trigger_config || {},
          enabled: !row.enabled,
          risk: row.risk || 'medium',
          max_runs_per_hour: row.max_runs_per_hour ?? 12,
          max_concurrent_runs: row.max_concurrent_runs ?? 1,
          on_concurrent_limit: row.on_concurrent_limit || 'drop',
          workspace_id: row.workspace_id || null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Update failed (${res.status})`)
      }
      await load()
    } catch (err) {
      setError(err?.message || 'Update failed')
    } finally {
      setBusyId('')
    }
  }

  async function runWorkflow(row, dryRun = false) {
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun, context: {} }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Run failed (${res.status})`)
      }
      navigate(`/workflows/runs/${encodeURIComponent(body.id)}`)
    } catch (err) {
      setError(err?.message || 'Run failed')
    } finally {
      setBusyId('')
    }
  }

  async function approveLive(row) {
    if (!isAdmin) return
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}/approve-live`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`Approve failed (${res.status})`)
      await load()
    } catch (err) {
      setError(err?.message || 'Approve failed')
    } finally {
      setBusyId('')
    }
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Workflows"
        subtitle="Chain agents with schedule and event triggers, plus human approval gates."
        actions={
          <div className="flex items-center gap-2">
            {isAdmin ? (
              <button
                type="button"
                onClick={() => navigate('/workflows/builder/new')}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500"
              >
                <Plus size={14} /> New workflow
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
            >
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400">
          <Loader2 className="animate-spin" size={18} /> Loading workflows…
        </div>
      ) : !rows.length ? (
        <EmptyState
          icon={Workflow}
          title="No workflows yet"
          hint="Create a workflow to chain agents with schedule or event triggers."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Trigger</th>
                <th className="px-4 py-3 font-medium">Next run</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Enabled</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-slate-800/80 text-slate-200">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{row.name}</div>
                    <div className="text-xs text-slate-500">{row.description || '—'}</div>
                    {!row.first_live_run_approved_at ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">
                          Dry-run only — approve live runs to enable
                        </span>
                        {isAdmin ? (
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void approveLive(row)}
                            className="rounded border border-amber-500/50 px-2 py-0.5 text-xs text-amber-100 hover:bg-amber-500/20"
                          >
                            Approve live runs
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 capitalize">{row.trigger_type || 'manual'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {row.trigger_type === 'schedule' && row.next_run
                      ? new Date(row.next_run).toLocaleString()
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge risk={row.risk} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={busyId === row.id || !isAdmin}
                      onClick={() => void toggleEnabled(row)}
                      className={`rounded-full px-3 py-1 text-xs ${
                        row.enabled
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-slate-700/60 text-slate-400'
                      }`}
                    >
                      {row.enabled ? 'On' : 'Off'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busyId === row.id || !row.enabled}
                        onClick={() => void runWorkflow(row, false)}
                        className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
                      >
                        <Play size={12} /> Run
                      </button>
                      {isAdmin ? (
                        <button
                          type="button"
                          onClick={() => navigate(`/workflows/builder/${encodeURIComponent(row.id)}`)}
                          className="text-xs text-slate-400 hover:text-slate-200"
                        >
                          Edit
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-3">
        <h3 className="text-sm font-medium text-white">Recent runs</h3>
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Triggered by</th>
                <th className="px-4 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 20).map((run) => (
                <tr key={run.id} className="border-t border-slate-800/80 text-slate-200">
                  <td className="px-4 py-3">
                    <Link
                      to={`/workflows/runs/${encodeURIComponent(run.id)}`}
                      className="text-indigo-300 hover:text-indigo-200"
                    >
                      {run.id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize">{run.status}</td>
                  <td className="px-4 py-3">
                    <TriggeredByBadge value={run.triggered_by} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
              {!runs.length ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                    No runs yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
