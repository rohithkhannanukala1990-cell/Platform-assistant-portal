import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Activity,
  RefreshCw,
  Loader2,
  AlertCircle,
  ExternalLink,
  Bot,
  Wrench,
  AlertTriangle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'
import RelatedAgentsBar from './RelatedAgentsBar'

function EmptyConnected({ title, subtitle }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center border border-dashed border-neutral-700 rounded-xl bg-neutral-900/40">
      <Wrench className="w-8 h-8 text-neutral-500 mb-3" />
      <p className="text-sm font-semibold text-neutral-200">{title}</p>
      <p className="text-xs text-neutral-500 mt-1 max-w-sm">{subtitle}</p>
      <Link
        to="/tool-registry"
        className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 hover:bg-emerald-600/30"
      >
        Connect GitHub in Tool Registry
      </Link>
    </div>
  )
}

export default function GitHubActionsView() {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const [repos, setRepos] = useState([])
  const [repo, setRepo] = useState('')
  const [runs, setRuns] = useState([])
  const [selected, setSelected] = useState(null)
  const [jobs, setJobs] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)
  const [agentResult, setAgentResult] = useState(null)
  const [incidentId, setIncidentId] = useState(null)

  const loadRepos = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    try {
      const res = await authFetch('/api/github/repos?per_page=50')
      if (res.status === 400) {
        setNotConnected(true)
        setRepos([])
        return
      }
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRepos(Array.isArray(data) ? data : [])
      if (Array.isArray(data) && data.length && !repo) {
        setRepo(data[0].full_name || '')
      }
    } catch (e) {
      setError(e.message || 'Failed to load repos')
    } finally {
      setLoading(false)
    }
  }, [authFetch, repo])

  const loadRuns = useCallback(async () => {
    if (!repo || !repo.includes('/')) return
    setBusy(true)
    setError(null)
    setSelected(null)
    setJobs([])
    setAgentResult(null)
    setIncidentId(null)
    try {
      const [owner, name] = repo.split('/')
      const res = await authFetch(
        `/api/github/repos/${owner}/${name}/actions/runs?status=failure&per_page=30`
      )
      if (res.status === 400) {
        setNotConnected(true)
        return
      }
      if (!res.ok) throw new Error(await res.text())
      setRuns(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load workflow runs')
      setRuns([])
    } finally {
      setBusy(false)
    }
  }, [authFetch, repo])

  useEffect(() => {
    void loadRepos()
  }, [loadRepos])

  useEffect(() => {
    if (repo) void loadRuns()
  }, [repo, loadRuns])

  async function openRun(run) {
    if (!repo) return
    const [owner, name] = repo.split('/')
    setSelected(run)
    setJobs([])
    setAgentResult(null)
    setIncidentId(null)
    try {
      const [detailRes, jobsRes] = await Promise.all([
        authFetch(`/api/github/repos/${owner}/${name}/actions/runs/${run.id}`),
        authFetch(`/api/github/repos/${owner}/${name}/actions/runs/${run.id}/jobs`),
      ])
      if (detailRes.ok) setSelected(await detailRes.json())
      if (jobsRes.ok) setJobs(await jobsRes.json())
    } catch {
      /* keep list row */
    }
  }

  async function runTriageAgent() {
    if (!selected || !repo) return
    const [owner, name] = repo.split('/')
    setBusy(true)
    setAgentResult(null)
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: `triage pipeline fail run ${selected.id} in ${repo}`,
          override_agents: ['pipeline_monitor_agent'],
          params: {
            owner,
            repo: name,
            run_id: selected.id,
          },
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Agent run failed')
      setAgentResult(data)
      showToast?.(data.summary || 'Triage complete', 'success')
    } catch (e) {
      showToast?.(e.message || 'Triage failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  async function createIncident() {
    if (!selected || !repo) return
    setBusy(true)
    try {
      const logText = [
        `GitHub Actions failure on ${repo}`,
        `run_id=${selected.id}`,
        `name=${selected.name || selected.display_title}`,
        `conclusion=${selected.conclusion}`,
        `url=${selected.html_url || ''}`,
        `jobs=${JSON.stringify(jobs.slice(0, 20))}`,
      ].join('\n')
      const res = await authFetch('/api/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs: logText }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Incident create failed')
      setIncidentId(data.id)
      showToast?.(`Incident #${data.id} created`, 'success')
    } catch (e) {
      showToast?.(e.message || 'Failed to create incident', 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-neutral-400 gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading GitHub Actions…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-6">
        <EmptyConnected
          title="GitHub not connected"
          subtitle="Connect a PAT in Tool Registry to list failed Actions runs. Demo data is not invented here when disconnected."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <Activity className="w-5 h-5 text-rose-400" />
          <h1 className="text-lg font-bold text-white">GitHub Actions</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadRuns()}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-neutral-700 text-neutral-300 hover:bg-neutral-800"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

      <RelatedAgentsBar surface="github_actions" />

      {error && (
        <div className="flex items-center gap-2 text-xs text-rose-400">
          <AlertCircle className="w-3.5 h-3.5" /> {error}
        </div>
      )}

      <div className="flex items-center gap-2">
        <label className="text-xs text-neutral-400">Repository</label>
        <select
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-neutral-200"
        >
          {repos.map((r) => (
            <option key={r.full_name} value={r.full_name}>
              {r.full_name}
            </option>
          ))}
        </select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 overflow-hidden">
          <div className="px-3 py-2 border-b border-neutral-800 text-xs font-semibold text-neutral-400 uppercase">
            Failed runs {busy ? '…' : `(${runs.length})`}
          </div>
          <ul className="max-h-[28rem] overflow-y-auto divide-y divide-neutral-800">
            {runs.length === 0 && (
              <li className="px-3 py-8 text-center text-xs text-neutral-500">No failed workflow runs.</li>
            )}
            {runs.map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  onClick={() => void openRun(run)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-neutral-800/60 ${
                    selected?.id === run.id ? 'bg-neutral-800/80' : ''
                  }`}
                >
                  <p className="text-sm text-neutral-100 font-medium flex items-center gap-1.5">
                    <AlertTriangle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    {run.display_title || run.name}
                  </p>
                  <p className="text-[11px] text-neutral-500 mt-0.5">
                    #{run.id} · {run.head_branch} · {run.conclusion}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 flex flex-col gap-3 min-h-[16rem]">
          {!selected ? (
            <p className="text-xs text-neutral-500 m-auto">Select a failed run.</p>
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    {selected.display_title || selected.name}
                  </h2>
                  <p className="text-[11px] text-neutral-500 mt-1">
                    run {selected.id} · {selected.head_branch} · {selected.conclusion}
                  </p>
                </div>
                {selected.html_url && (
                  <a
                    href={selected.html_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-neutral-400 hover:text-white"
                  >
                    <ExternalLink className="w-4 h-4" />
                  </a>
                )}
              </div>
              <div>
                <p className="text-[11px] font-semibold text-neutral-500 uppercase mb-1">
                  Jobs ({jobs.length})
                </p>
                <ul className="text-[11px] text-neutral-400 max-h-40 overflow-y-auto space-y-0.5">
                  {jobs.map((j) => (
                    <li key={j.id} className="flex justify-between gap-2">
                      <span className="truncate">{j.name}</span>
                      <span className={j.conclusion === 'failure' ? 'text-rose-400' : 'text-neutral-500'}>
                        {j.conclusion || j.status}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
              <div className="flex gap-2 mt-auto">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void runTriageAgent()}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-rose-600/20 border border-rose-500/40 text-rose-200 text-xs font-bold hover:bg-rose-600/30 disabled:opacity-40"
                >
                  {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5" />}
                  Triage with agent
                </button>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void createIncident()}
                  className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg border border-neutral-600 text-neutral-200 text-xs font-bold hover:bg-neutral-800 disabled:opacity-40"
                >
                  Create incident
                </button>
              </div>
              {incidentId && (
                <Link to="/incidents" className="text-xs text-emerald-400 hover:underline">
                  Open incident #{incidentId}
                </Link>
              )}
              {agentResult && (
                <div className="rounded-lg border border-neutral-700 bg-neutral-950/60 p-3 text-xs text-neutral-300">
                  <p className="font-semibold text-neutral-100 mb-1">{agentResult.status}</p>
                  <p>{agentResult.summary}</p>
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
