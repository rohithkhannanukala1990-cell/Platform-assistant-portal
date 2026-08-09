import { useCallback, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Play, RefreshCw, Workflow } from 'lucide-react'
import { authFetch } from '../../utils/api'
import { PageHeader, EmptyState } from '../ui'

function RiskBadge({ risk }) {
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

export default function WorkflowListPage() {
  const navigate = useNavigate()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const res = await authFetch('/api/workflows')
      if (!res.ok) throw new Error(`Failed to load workflows (${res.status})`)
      const data = await res.json()
      setRows(Array.isArray(data) ? data : [])
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

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Workflows"
        subtitle="Chain agents with human approval gates between steps."
        actions={
          <button
            type="button"
            onClick={() => void load()}
            className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
          >
            <RefreshCw size={14} /> Refresh
          </button>
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
          hint="Create a workflow via the API to chain agents with HITL gates."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Steps</th>
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
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge risk={row.risk} />
                  </td>
                  <td className="px-4 py-3">{(row.steps || []).length}</td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={busyId === row.id}
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
                      <Link
                        to={`/workflows?focus=${encodeURIComponent(row.id)}`}
                        className="text-xs text-slate-400 hover:text-slate-200"
                      >
                        ID
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
