import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Rocket,
  CheckCircle2,
  XCircle,
  RefreshCw,
  GitBranch,
  GitCommit,
  User,
  Loader2,
  ExternalLink,
  AlertCircle,
  Ban,
} from 'lucide-react'
import RelatedAgentsBar from './RelatedAgentsBar'
import { useAuth } from '../contexts/AuthContext'
import type { DeploymentRow, GithubRepo, GithubWorkflowRun } from '../types/api'
import {
  argoAppToDeployment,
  githubRunToDeployment,
  isDeployishRun,
} from '../utils/deploymentsMap'

const STATUS_CFG = {
  success: {
    label: 'Success',
    cls: 'text-green-400 bg-green-500/10 border-green-500/25',
    icon: CheckCircle2,
  },
  failed: {
    label: 'Failed',
    cls: 'text-red-400 bg-red-500/10 border-red-500/25',
    icon: XCircle,
  },
  running: {
    label: 'Running',
    cls: 'text-blue-400 bg-blue-500/10 border-blue-500/25',
    icon: RefreshCw,
  },
  cancelled: {
    label: 'Cancelled',
    cls: 'text-slate-400 bg-slate-500/10 border-slate-500/25',
    icon: Ban,
  },
  unknown: {
    label: 'Unknown',
    cls: 'text-amber-400 bg-amber-500/10 border-amber-500/25',
    icon: AlertCircle,
  },
} as const

const ENV_FILTERS = ['All', 'production', 'staging', 'dev', 'test', 'unknown'] as const

function repoFullName(repo: GithubRepo): string {
  if (repo.full_name) return repo.full_name
  const owner = typeof repo.owner === 'string' ? repo.owner : repo.owner?.login
  if (owner && repo.name) return `${owner}/${repo.name}`
  return ''
}

export default function DeploymentsView() {
  const { authFetch } = useAuth()
  const [rows, setRows] = useState<DeploymentRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [notConnected, setNotConnected] = useState(false)
  const [envFilter, setEnvFilter] = useState<(typeof ENV_FILTERS)[number]>('All')
  const [deployOnly, setDeployOnly] = useState(true)
  const [argoCount, setArgoCount] = useState(0)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    const collected: DeploymentRow[] = []
    let argo = 0

    try {
      const reposRes = await authFetch('/api/github/repos?per_page=30')
      if (reposRes.status === 400) {
        setNotConnected(true)
      } else if (!reposRes.ok) {
        throw new Error(await reposRes.text())
      } else {
        const repos = (await reposRes.json()) as GithubRepo[]
        const list = Array.isArray(repos) ? repos.slice(0, 8) : []
        for (const repo of list) {
          const full = repoFullName(repo)
          if (!full.includes('/')) continue
          const [owner, name] = full.split('/')
          const runsRes = await authFetch(
            `/api/github/repos/${owner}/${name}/actions/runs?per_page=15`
          )
          if (runsRes.status === 400) {
            setNotConnected(true)
            break
          }
          if (!runsRes.ok) continue
          const runs = (await runsRes.json()) as GithubWorkflowRun[]
          if (!Array.isArray(runs)) continue
          for (const run of runs) {
            collected.push(githubRunToDeployment(run, full))
          }
        }
      }

      try {
        const argoRes = await authFetch('/api/argocd/applications?limit=50')
        if (argoRes.ok) {
          const apps = await argoRes.json()
          if (Array.isArray(apps)) {
            argo = apps.length
            for (const app of apps) {
              collected.push(argoAppToDeployment(app))
            }
          }
        }
      } catch {
        /* Argo optional */
      }

      setArgoCount(argo)
      setRows(collected)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load deployments')
      setRows([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = useMemo(() => {
    let list = rows
    if (envFilter !== 'All') {
      list = list.filter((d) => d.env === envFilter)
    }
    if (deployOnly) {
      const deployish = list.filter(
        (d) =>
          d.source !== 'github' ||
          isDeployishRun({
            id: d.id,
            name: d.message,
            display_title: d.message,
            path: d.message,
          })
      )
      const githubDeployish = deployish.filter((d) => d.source === 'github')
      if (githubDeployish.length > 0 || list.every((d) => d.source !== 'github')) {
        list = deployish
      }
    }
    return list
  }, [rows, envFilter, deployOnly])

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Rocket className="w-5 h-5 text-blue-400" />
            Deployments
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Live workflow runs from GitHub Actions
            {argoCount > 0 ? ` · ${argoCount} Argo CD apps` : ''}
          </p>
        </div>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-card text-slate-400 hover:text-white disabled:opacity-50"
        >
          <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
          Refresh
        </button>
      </div>

      <RelatedAgentsBar surface="deployments" />

      {notConnected && (
        <div className="flex flex-col items-start gap-2 px-4 py-3 rounded-xl border border-amber-500/25 bg-amber-500/5">
          <p className="text-sm text-amber-200 font-semibold">GitHub not connected</p>
          <p className="text-xs text-amber-200/80">
            Connect a GitHub account in Tool Registry to see live Actions runs here.
          </p>
          <Link
            to="/tool-registry"
            className="text-xs font-semibold text-emerald-300 hover:underline"
          >
            Open Tool Registry →
          </Link>
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-1.5">
          <FilterIcon />
          {ENV_FILTERS.map((e) => (
            <button
              key={e}
              type="button"
              onClick={() => setEnvFilter(e)}
              className={`px-2.5 py-1 rounded-lg text-[11px] border transition-colors ${
                envFilter === e
                  ? 'border-blue-500/40 bg-blue-500/15 text-blue-300'
                  : 'border-border text-slate-500 hover:text-white'
              }`}
            >
              {e}
            </button>
          ))}
        </div>
        <label className="flex items-center gap-2 text-xs text-slate-400 ml-auto">
          <input
            type="checkbox"
            checked={deployOnly}
            onChange={(e) => setDeployOnly(e.target.checked)}
          />
          Prefer deploy/release workflows
        </label>
      </div>

      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-500 gap-2 text-sm">
          <Loader2 className="w-4 h-4 animate-spin" />
          Loading live deployments…
        </div>
      ) : filtered.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-16 px-6 text-center border border-dashed border-neutral-700 rounded-xl">
          <Rocket className="w-8 h-8 text-neutral-500 mb-3" />
          <p className="text-sm font-semibold text-neutral-200">No deployment runs yet</p>
          <p className="text-xs text-neutral-500 mt-1 max-w-md">
            {notConnected
              ? 'Connect GitHub to populate this list.'
              : 'No matching workflow runs for the selected filters. Try clearing “Prefer deploy/release workflows”.'}
          </p>
          <Link
            to="/github/actions"
            className="mt-4 text-xs font-semibold text-emerald-300 hover:underline"
          >
            Open GitHub Actions →
          </Link>
        </div>
      ) : (
        <div className="bg-card border border-border rounded-xl overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-border text-left text-[11px] uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Service / repo</th>
                <th className="px-4 py-3">Env</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Commit</th>
                <th className="px-4 py-3">By</th>
                <th className="px-4 py-3">When</th>
                <th className="px-4 py-3" />
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const cfg = STATUS_CFG[d.status] || STATUS_CFG.unknown
                const Icon = cfg.icon
                return (
                  <tr key={d.id} className="border-b border-border last:border-0 hover:bg-card/80">
                    <td className="px-4 py-3">
                      <p className="text-sm text-white font-medium truncate max-w-[220px]">{d.service}</p>
                      <p className="text-[11px] text-slate-500 truncate max-w-[260px]">{d.message}</p>
                    </td>
                    <td className="px-4 py-3">
                      <span className="text-[11px] px-2 py-0.5 rounded border border-border text-slate-300">
                        {d.env}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={`inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded border ${cfg.cls}`}
                      >
                        <Icon className="w-3 h-3" />
                        {cfg.label}
                      </span>
                      <p className="text-[10px] text-slate-600 mt-0.5">{d.source}</p>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      <span className="inline-flex items-center gap-1">
                        <GitCommit className="w-3 h-3" />
                        {d.commit}
                      </span>
                      <p className="text-[10px] text-slate-600 mt-0.5 inline-flex items-center gap-1">
                        <GitBranch className="w-3 h-3" />
                        {d.duration}
                      </p>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-400">
                      <span className="inline-flex items-center gap-1">
                        <User className="w-3 h-3" />
                        {d.triggeredBy}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-xs text-slate-500">{d.time}</td>
                    <td className="px-4 py-3 text-right">
                      {d.htmlUrl ? (
                        <a
                          href={d.htmlUrl}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1 text-xs text-emerald-400 hover:underline"
                        >
                          Open <ExternalLink className="w-3 h-3" />
                        </a>
                      ) : null}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function FilterIcon() {
  return <span className="text-[10px] text-slate-600 uppercase tracking-wider mr-1">Env</span>
}
