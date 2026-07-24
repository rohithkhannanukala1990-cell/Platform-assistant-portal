import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  GitPullRequest,
  RefreshCw,
  Loader2,
  AlertCircle,
  ExternalLink,
  Bot,
  Wrench,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

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

export default function GitHubPRsView() {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const [repos, setRepos] = useState([])
  const [repo, setRepo] = useState('')
  const [prs, setPrs] = useState([])
  const [selected, setSelected] = useState(null)
  const [files, setFiles] = useState([])
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)
  const [agentResult, setAgentResult] = useState(null)

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

  const loadPrs = useCallback(async () => {
    if (!repo || !repo.includes('/')) return
    setBusy(true)
    setError(null)
    setSelected(null)
    setFiles([])
    setAgentResult(null)
    try {
      const [owner, name] = repo.split('/')
      const res = await authFetch(`/api/github/repos/${owner}/${name}/pulls?state=open`)
      if (res.status === 400) {
        setNotConnected(true)
        return
      }
      if (!res.ok) throw new Error(await res.text())
      setPrs(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load PRs')
      setPrs([])
    } finally {
      setBusy(false)
    }
  }, [authFetch, repo])

  useEffect(() => {
    void loadRepos()
  }, [loadRepos])

  useEffect(() => {
    if (repo) void loadPrs()
  }, [repo, loadPrs])

  async function openPr(pr) {
    if (!repo) return
    const [owner, name] = repo.split('/')
    setSelected(pr)
    setFiles([])
    setAgentResult(null)
    try {
      const [detailRes, filesRes] = await Promise.all([
        authFetch(`/api/github/repos/${owner}/${name}/pulls/${pr.number}`),
        authFetch(`/api/github/repos/${owner}/${name}/pulls/${pr.number}/files`),
      ])
      if (detailRes.ok) setSelected(await detailRes.json())
      if (filesRes.ok) setFiles(await filesRes.json())
    } catch {
      /* keep list row */
    }
  }

  async function runCodeReview() {
    if (!selected || !repo) return
    const [owner, name] = repo.split('/')
    setBusy(true)
    setAgentResult(null)
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: `code review PR #${selected.number} in ${repo}`,
          override_agents: ['code_review_agent'],
          params: {
            owner,
            repo: name,
            pr_number: selected.number,
          },
        }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Agent run failed')
      setAgentResult(data)
      showToast?.(data.summary || 'Code review complete', 'success')
    } catch (e) {
      showToast?.(e.message || 'Code review failed', 'error')
    } finally {
      setBusy(false)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20 text-neutral-400 gap-2">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading GitHub…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-6">
        <EmptyConnected
          title="GitHub not connected"
          subtitle="Connect a PAT in Tool Registry to list pull requests. No invented PR data is shown when disconnected."
        />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-6 max-w-6xl mx-auto">
      <div className="flex items-center justify-between gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <GitPullRequest className="w-5 h-5 text-violet-400" />
          <h1 className="text-lg font-bold text-white">GitHub Pull Requests</h1>
        </div>
        <button
          type="button"
          onClick={() => void loadRepos()}
          className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs rounded-lg border border-neutral-700 text-neutral-300 hover:bg-neutral-800"
        >
          <RefreshCw className="w-3.5 h-3.5" /> Refresh
        </button>
      </div>

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
            Open PRs {busy ? '…' : `(${prs.length})`}
          </div>
          <ul className="max-h-[28rem] overflow-y-auto divide-y divide-neutral-800">
            {prs.length === 0 && (
              <li className="px-3 py-8 text-center text-xs text-neutral-500">No open pull requests.</li>
            )}
            {prs.map((pr) => (
              <li key={pr.number}>
                <button
                  type="button"
                  onClick={() => void openPr(pr)}
                  className={`w-full text-left px-3 py-2.5 hover:bg-neutral-800/60 ${
                    selected?.number === pr.number ? 'bg-neutral-800/80' : ''
                  }`}
                >
                  <p className="text-sm text-neutral-100 font-medium">
                    #{pr.number} {pr.title}
                  </p>
                  <p className="text-[11px] text-neutral-500 mt-0.5">
                    {pr.user} · {pr.updated_at ? new Date(pr.updated_at).toLocaleString() : ''}
                  </p>
                </button>
              </li>
            ))}
          </ul>
        </div>

        <div className="rounded-xl border border-neutral-800 bg-neutral-900/50 p-4 flex flex-col gap-3 min-h-[16rem]">
          {!selected ? (
            <p className="text-xs text-neutral-500 m-auto">Select a pull request.</p>
          ) : (
            <>
              <div className="flex items-start justify-between gap-2">
                <div>
                  <h2 className="text-sm font-semibold text-white">
                    #{selected.number} {selected.title}
                  </h2>
                  <p className="text-[11px] text-neutral-500 mt-1">
                    {selected.head} → {selected.base} · {selected.user}
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
              {selected.body && (
                <p className="text-xs text-neutral-400 whitespace-pre-wrap line-clamp-6">{selected.body}</p>
              )}
              <div>
                <p className="text-[11px] font-semibold text-neutral-500 uppercase mb-1">
                  Files ({files.length})
                </p>
                <ul className="text-[11px] text-neutral-400 max-h-40 overflow-y-auto space-y-0.5">
                  {files.map((f) => (
                    <li key={f.filename} className="font-mono truncate">
                      {f.filename}{' '}
                      <span className="text-emerald-500">+{f.additions}</span>{' '}
                      <span className="text-rose-400">-{f.deletions}</span>
                    </li>
                  ))}
                </ul>
              </div>
              <button
                type="button"
                disabled={busy}
                onClick={() => void runCodeReview()}
                className="mt-auto flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-violet-600/20 border border-violet-500/40 text-violet-200 text-xs font-bold hover:bg-violet-600/30 disabled:opacity-40"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Bot className="w-3.5 h-3.5" />}
                Run code review agent
              </button>
              {agentResult && (
                <div className="rounded-lg border border-neutral-700 bg-neutral-950/60 p-3 text-xs text-neutral-300">
                  <p className="font-semibold text-neutral-100 mb-1">{agentResult.status}</p>
                  <p>{agentResult.summary}</p>
                  {Array.isArray(agentResult.details?.findings) && agentResult.details.findings.length > 0 && (
                    <ul className="mt-2 list-disc pl-4 space-y-1 text-neutral-400">
                      {agentResult.details.findings.slice(0, 8).map((f, i) => (
                        <li key={i}>{String(f)}</li>
                      ))}
                    </ul>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  )
}
