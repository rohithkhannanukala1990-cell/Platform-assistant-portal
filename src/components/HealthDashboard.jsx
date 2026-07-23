import { useCallback, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Database,
  Wifi,
  Shield,
  Zap,
  Server,
  AlertTriangle,
  CheckCircle,
  XCircle,
  RefreshCw,
  Mail,
  Activity,
  Clock,
  Plug,
  Lightbulb,
  ChevronRight,
} from 'lucide-react'
import { usePortalContext } from '../contexts/PortalContext'
import useHealthDashboard, { canMutateHealth } from '../hooks/useHealthDashboard'
import { useAuth } from '../contexts/AuthContext'

function healthRowStatus(apiStatus) {
  if (apiStatus === 'critical') return 'down'
  if (apiStatus === 'warning') return 'degraded'
  return 'healthy'
}

function AutoHealButton({ service, workspaceId, authFetch }) {
  const [state, setState] = useState('idle')

  const handleHeal = async () => {
    setState('loading')
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          task: `restart failing pods for ${service.name}`,
          context: { workspace_id: workspaceId },
        }),
      })
      if (!res.ok) throw new Error('Heal failed')
      const data = await res.json()
      setState(
        data.status === 'success' || data.status === 'pending_approval' ? 'success' : 'failed'
      )
      setTimeout(() => setState('idle'), 4000)
    } catch {
      setState('failed')
      setTimeout(() => setState('idle'), 4000)
    }
  }

  const config = {
    idle: { label: 'Auto-Heal', cls: 'bg-orange-600 hover:bg-orange-500' },
    loading: { label: 'Healing…', cls: 'bg-gray-600 cursor-wait' },
    success: { label: '✓ Queued', cls: 'bg-green-700 cursor-default' },
    failed: { label: '✗ Failed', cls: 'bg-red-700 cursor-default' },
  }[state]

  return (
    <button
      type="button"
      onClick={() => void handleHeal()}
      disabled={state !== 'idle'}
      className={`text-white text-xs px-3 py-1.5 rounded-lg disabled:opacity-60 ${config.cls}`}
    >
      {config.label}
    </button>
  )
}

function formatRelative(iso) {
  if (!iso) return '—'
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return '—'
  const mins = Math.floor((Date.now() - t) / 60000)
  if (mins < 1) return 'just now'
  if (mins === 1) return '1 minute ago'
  if (mins < 60) return `${mins} minutes ago`
  const hrs = Math.floor(mins / 60)
  if (hrs === 1) return '1 hour ago'
  if (hrs < 24) return `${hrs} hours ago`
  const days = Math.floor(hrs / 24)
  return days === 1 ? '1 day ago' : `${days} days ago`
}

function statusBadgeClasses(status) {
  if (status === 'critical') return 'bg-red-500/20 text-red-300 border border-red-500/30'
  if (status === 'warning') return 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30'
  if (status === 'info') return 'bg-blue-500/20 text-blue-300 border border-blue-500/30'
  return 'bg-green-500/20 text-green-300 border border-green-500/30'
}

function statusBadgeLabel(status) {
  if (status === 'critical') return 'Critical'
  if (status === 'warning') return 'Warning'
  if (status === 'info') return 'Info'
  return 'Healthy'
}

function cardBorder(status) {
  if (status === 'critical') return 'border-red-500/30'
  if (status === 'warning') return 'border-yellow-500/30'
  return 'border-green-500/30'
}

function severityBadge(sev) {
  const s = (sev || 'info').toLowerCase()
  if (s === 'critical' || s === 'high') return 'bg-red-500/20 text-red-400 border border-red-500/25'
  if (s === 'warning' || s === 'medium') return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/25'
  if (s === 'low') return 'bg-slate-500/20 text-slate-300 border border-slate-500/25'
  return 'bg-blue-500/20 text-blue-400 border border-blue-500/25'
}

function ProbeCard({
  title,
  icon: Icon,
  iconClass,
  status,
  latencyMs,
  primary,
  message,
  onDrill,
  drillLabel,
  healService,
  workspaceId,
  authFetch,
  canMutate,
}) {
  const st = status || 'healthy'
  return (
    <div className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(st)} border-gray-700`}>
      <div className="flex items-start justify-between gap-3">
        <Icon className={`w-8 h-8 shrink-0 ${iconClass || 'text-slate-300'}`} />
        <div className="flex flex-col items-end gap-2">
          <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(st)}`}>
            {statusBadgeLabel(st)}
          </span>
          {canMutate &&
            healService &&
            (healthRowStatus(st) === 'degraded' || healthRowStatus(st) === 'down') && (
              <AutoHealButton
                service={healService}
                workspaceId={workspaceId}
                authFetch={authFetch}
              />
            )}
        </div>
      </div>
      <h2 className="mt-4 text-lg font-semibold text-white">{title}</h2>
      <p className="mt-1 text-2xl font-mono text-slate-200">{primary}</p>
      {latencyMs != null && (
        <p className="mt-1 text-xs text-slate-500 font-mono">Latency: {latencyMs} ms</p>
      )}
      <p className="mt-2 text-sm text-slate-400">{message || '—'}</p>
      {onDrill && (
        <button
          type="button"
          onClick={onDrill}
          className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-cyan-300 hover:text-cyan-200"
        >
          {drillLabel || 'View details'}
          <ChevronRight className="w-3.5 h-3.5" />
        </button>
      )}
    </div>
  )
}

function SkeletonGrid() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
      {Array.from({ length: 6 }).map((_, i) => (
        <div
          key={i}
          className="bg-gray-800 rounded-xl p-6 border border-gray-700 animate-pulse h-40"
        />
      ))}
    </div>
  )
}

function SlowQueriesPanel({ performance }) {
  const available = performance?.available !== false
  const rows = Array.isArray(performance?.slow_queries) ? performance.slow_queries : []
  const message = performance?.message || ''

  if (!available) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-6 text-sm text-slate-400">
        <p className="font-medium text-slate-200 mb-1">Slow query probe unavailable</p>
        <p>{message || 'pg_stat_statements is not available (common on non-Postgres / SQLite demos).'}</p>
      </div>
    )
  }

  if (!rows.length) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-6 text-sm text-slate-400 flex items-center gap-3">
        <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
        <span>{message || 'No slow queries above the 500ms mean threshold.'}</span>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-700 bg-gray-800/50">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="text-slate-500 border-b border-gray-700">
            <th className="p-4 font-medium">Query</th>
            <th className="p-4 font-medium whitespace-nowrap">Mean time</th>
            <th className="p-4 font-medium whitespace-nowrap">Calls</th>
            <th className="p-4 font-medium whitespace-nowrap">Total time</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={idx} className="border-b border-gray-700/80 align-top">
              <td className="p-4 text-slate-200 font-mono text-xs max-w-xl whitespace-pre-wrap break-all">
                {row.query || '—'}
              </td>
              <td className="p-4 text-amber-300 font-mono whitespace-nowrap">
                {row.mean_exec_time != null ? `${Number(row.mean_exec_time).toFixed(1)} ms` : '—'}
              </td>
              <td className="p-4 text-slate-300 font-mono">{row.calls ?? '—'}</td>
              <td className="p-4 text-slate-400 font-mono whitespace-nowrap">
                {row.total_exec_time != null ? `${Number(row.total_exec_time).toFixed(1)} ms` : '—'}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function DependenciesPanel({ dependencies }) {
  const available = dependencies?.available !== false
  const rows = Array.isArray(dependencies?.vulnerabilities) ? dependencies.vulnerabilities : []
  const message = dependencies?.message || ''

  if (!available && !rows.length) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-6 text-sm text-slate-400">
        <p className="font-medium text-slate-200 mb-1">Dependency audit unavailable</p>
        <p>{message || 'pip-audit did not return results for this environment.'}</p>
      </div>
    )
  }

  if (!rows.length) {
    return (
      <div className="rounded-xl border border-gray-700 bg-gray-800/60 p-6 text-sm text-slate-400 flex items-center gap-3">
        <CheckCircle className="w-5 h-5 text-green-500 shrink-0" />
        <span>{message || 'No known vulnerabilities reported by pip-audit.'}</span>
      </div>
    )
  }

  return (
    <div className="overflow-x-auto rounded-xl border border-gray-700 bg-gray-800/50">
      <table className="w-full text-sm text-left">
        <thead>
          <tr className="text-slate-500 border-b border-gray-700">
            <th className="p-4 font-medium">Package</th>
            <th className="p-4 font-medium">Version</th>
            <th className="p-4 font-medium">Vulnerability</th>
            <th className="p-4 font-medium">Severity</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, idx) => (
            <tr key={`${row.package}-${row.vulnerability_id}-${idx}`} className="border-b border-gray-700/80">
              <td className="p-4 text-white font-medium">{row.package || '—'}</td>
              <td className="p-4 text-slate-300 font-mono text-xs">{row.version || '—'}</td>
              <td className="p-4">
                <div className="text-slate-200 font-mono text-xs">{row.vulnerability_id || '—'}</div>
                {row.description ? (
                  <p className="mt-1 text-xs text-slate-500 line-clamp-2">{row.description}</p>
                ) : null}
              </td>
              <td className="p-4">
                <span
                  className={`inline-flex rounded-full px-3 py-1 text-xs font-medium capitalize ${severityBadge(row.severity)}`}
                >
                  {row.severity || 'unknown'}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function RecommendationsPanel({ recommendations }) {
  const rows = Array.isArray(recommendations) ? recommendations : []
  if (!rows.length) return null
  return (
    <section className="mb-10">
      <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
        <Lightbulb className="w-5 h-5 text-amber-300" />
        Tuning recommendations
      </h2>
      <ul className="space-y-3">
        {rows.map((rec) => (
          <li
            key={rec.id || rec.title}
            className="rounded-xl border border-gray-700 bg-gray-800/70 p-4"
          >
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${severityBadge(rec.severity)}`}>
                {rec.severity || 'info'}
              </span>
              <span className="text-xs uppercase tracking-wide text-slate-500">{rec.category}</span>
            </div>
            <p className="text-sm font-medium text-white">{rec.title}</p>
            {rec.detail ? <p className="mt-1 text-sm text-slate-400">{rec.detail}</p> : null}
            {rec.action ? (
              <p className="mt-2 text-xs text-cyan-300/90">Suggested: {rec.action}</p>
            ) : null}
            {rec.evidence ? (
              <p className="mt-2 text-xs font-mono text-slate-500 break-all">{rec.evidence}</p>
            ) : null}
          </li>
        ))}
      </ul>
    </section>
  )
}

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'slow-queries', label: 'Slow queries' },
  { id: 'dependencies', label: 'Dependencies' },
]

export default function HealthDashboard() {
  const { authFetch } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const workspaceId = activeWorkspace?.id ?? ''
  const workspaceName = activeWorkspace?.name || 'Default workspace'
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const tab = TABS.some((t) => t.id === searchParams.get('tab'))
    ? searchParams.get('tab')
    : 'overview'

  const {
    role,
    canView,
    canMutate,
    healthData,
    summary,
    alerts,
    setAlerts,
    isLoading,
    fetchError,
    lastChecked,
    autoRefreshTimer,
    fetchHealth,
    refresh,
  } = useHealthDashboard()

  const [isHealing, setIsHealing] = useState(false)
  const [toast, setToast] = useState(null)
  const [fadeOutIds, setFadeOutIds] = useState(() => new Set())

  const showToast = useCallback((message) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const setTab = (id) => {
    const next = new URLSearchParams(searchParams)
    if (id === 'overview') next.delete('tab')
    else next.set('tab', id)
    setSearchParams(next, { replace: true })
  }

  async function runHeal() {
    if (!canMutateHealth(role)) return
    setIsHealing(true)
    try {
      const res = await authFetch('/api/health/autoheal/all', { method: 'POST' })
      const data = res.ok ? await res.json().catch(() => ({})) : {}
      const n = typeof data.count === 'number' ? data.count : 0
      showToast(`Healed ${n} issue${n === 1 ? '' : 's'}`)
      await fetchHealth()
    } catch {
      showToast('Heal request failed')
    } finally {
      setIsHealing(false)
    }
  }

  async function emailTeam() {
    if (!canMutateHealth(role)) return
    try {
      const res = await authFetch('/api/health/alerts/email', { method: 'POST' })
      if (res.ok) showToast('Alerts emailed to team')
      else showToast('Email request failed')
    } catch {
      showToast('Email request failed')
    }
  }

  async function resolveAlert(id) {
    if (!canMutateHealth(role)) return
    try {
      const res = await authFetch(`/api/health/alerts/${encodeURIComponent(id)}/resolve`, {
        method: 'POST',
      })
      if (!res.ok) return
      setFadeOutIds((prev) => new Set(prev).add(id))
      window.setTimeout(() => {
        setAlerts((a) => a.filter((x) => x.id !== id))
        setFadeOutIds((prev) => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
      }, 320)
    } catch {
      /* ignore */
    }
  }

  async function ignoreAlert(id) {
    if (!canMutateHealth(role)) return
    try {
      const res = await authFetch(`/api/health/alerts/${encodeURIComponent(id)}/ignore`, {
        method: 'POST',
      })
      if (!res.ok) return
      setFadeOutIds((prev) => new Set(prev).add(id))
      window.setTimeout(() => {
        setAlerts((a) => a.filter((x) => x.id !== id))
        setFadeOutIds((prev) => {
          const next = new Set(prev)
          next.delete(id)
          return next
        })
      }, 320)
    } catch {
      /* ignore */
    }
  }

  const overallStatus = summary?.status || healthData?.tools?.status || 'healthy'
  const db = healthData?.database || {}
  const redis = healthData?.redis || {}
  const ws = healthData?.websockets || {}
  const tools = healthData?.tools || {}
  const deps = healthData?.dependencies || {}
  const perf = healthData?.performance || {}
  const connectors = healthData?.connectors || tools.connectors || {}
  const recommendations = healthData?.recommendations || []

  const toolsStatus =
    tools.status ||
    ((tools.degraded_count || 0) > 0 || (tools.expiring_count || 0) > 0 ? 'warning' : 'healthy')
  const secStatus =
    deps.status || ((deps.vulnerability_count || 0) > 0 ? 'warning' : 'healthy')
  const perfStatus =
    perf.status || ((perf.slow_query_count || 0) > 0 ? 'warning' : 'healthy')

  const expiring = Array.isArray(tools.expiring) ? tools.expiring : []

  const connectorCards = useMemo(() => {
    return Object.entries(connectors || {}).map(([name, row]) => ({
      name,
      ...(row && typeof row === 'object' ? row : { status: 'healthy', message: '—' }),
    }))
  }, [connectors])

  if (!canView) {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center space-y-4">
        <Shield className="w-12 h-12 mx-auto text-amber-500/70" />
        <h1 className="text-xl font-semibold text-white">System Health</h1>
        <p className="text-slate-400 text-sm">
          This dashboard is restricted to{' '}
          <span className="text-purple-400 font-medium">Admin</span> and{' '}
          <span className="text-purple-400 font-medium">Operator</span> users.
        </p>
      </div>
    )
  }

  return (
    <div className="max-w-7xl mx-auto pb-16 px-4 sm:px-6 lg:px-8">
      {toast && (
        <div className="fixed top-20 right-6 z-50 px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      <header className="py-8 border-b border-gray-700 mb-6">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">System Health</h1>
            <p className="mt-2 text-sm text-slate-400 flex flex-wrap items-center gap-x-3 gap-y-1">
              <Clock className="w-4 h-4 inline shrink-0 text-slate-500" aria-hidden />
              <span>
                Workspace: <span className="text-slate-200">{workspaceName}</span>
              </span>
              <span aria-hidden>·</span>
              <span>
                Last checked: {lastChecked || '—'} | Auto-refresh in {autoRefreshTimer}s
              </span>
            </p>
            {!isLoading && healthData && (
              <div className="mt-3 inline-flex items-center gap-2">
                <span className="text-xs text-slate-500 uppercase tracking-wide">Overall</span>
                <span
                  className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(overallStatus)}`}
                >
                  {statusBadgeLabel(overallStatus)}
                </span>
              </div>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => void refresh()}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 border border-gray-600
                text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh Now
            </button>
            {canMutate && (
              <>
                <button
                  type="button"
                  onClick={runHeal}
                  disabled={isHealing || isLoading}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-900/40 border border-emerald-700/50
                    text-sm font-medium text-emerald-200 hover:bg-emerald-900/60 disabled:opacity-50 transition-colors"
                >
                  {isHealing ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Healing...
                    </>
                  ) : (
                    <>
                      <RefreshCw className="w-4 h-4" />
                      Heal Low-Risk Issues
                    </>
                  )}
                </button>
                <button
                  type="button"
                  onClick={emailTeam}
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 border border-gray-600
                    text-sm font-medium text-white hover:bg-gray-700 transition-colors"
                >
                  <Mail className="w-4 h-4" />
                  Email Team
                </button>
              </>
            )}
          </div>
        </div>

        <nav className="mt-6 flex flex-wrap gap-2" aria-label="Health views">
          {TABS.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                tab === t.id
                  ? 'bg-slate-700 border-slate-500 text-white'
                  : 'bg-transparent border-gray-700 text-slate-400 hover:text-slate-200'
              }`}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      {fetchError && !isLoading && (
        <div className="mb-8 flex flex-col sm:flex-row items-start sm:items-center gap-4 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30 text-yellow-200">
          <AlertTriangle className="w-6 h-6 shrink-0" />
          <div className="flex-1">
            <p className="font-medium">Health data unavailable</p>
            <p className="text-sm text-yellow-200/80 mt-1">Check API connectivity or session role.</p>
          </div>
          <button
            type="button"
            onClick={() => void refresh()}
            className="px-3 py-1.5 rounded-lg bg-yellow-500/20 border border-yellow-500/40 text-sm font-medium hover:bg-yellow-500/30"
          >
            Retry
          </button>
        </div>
      )}

      {isLoading ? (
        <SkeletonGrid />
      ) : !fetchError && healthData ? (
        <>
          {tab === 'slow-queries' && (
            <section className="mb-10">
              <h2 className="text-lg font-semibold text-white mb-4">Slow queries</h2>
              <p className="text-sm text-slate-400 mb-4">
                From pg_stat_statements (mean &gt; {perf.threshold_ms ?? 500}ms). Read-only.
              </p>
              <SlowQueriesPanel performance={perf} />
            </section>
          )}

          {tab === 'dependencies' && (
            <section className="mb-10">
              <h2 className="text-lg font-semibold text-white mb-4">Dependency vulnerabilities</h2>
              <p className="text-sm text-slate-400 mb-4">
                pip-audit findings for backend requirements. Read-only.
              </p>
              <DependenciesPanel dependencies={deps} />
            </section>
          )}

          {tab === 'overview' && (
            <>
              {/* TODO(S3-P3.2): Render overall health status and per-probe cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-10">
                <ProbeCard
                  title="Database"
                  icon={Database}
                  status={db.status}
                  latencyMs={db.latency_ms}
                  primary={db.latency_ms != null ? `${db.latency_ms} ms` : '—'}
                  message={db.message}
                  healService={{ name: 'Database' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
                <ProbeCard
                  title="Redis Cache"
                  icon={Zap}
                  iconClass="text-amber-400"
                  status={redis.status}
                  latencyMs={redis.latency_ms}
                  primary={redis.latency_ms != null ? `${redis.latency_ms} ms` : '—'}
                  message={redis.message}
                  healService={{ name: 'Redis Cache' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
                <ProbeCard
                  title="WebSockets"
                  icon={Wifi}
                  iconClass="text-cyan-400"
                  status={ws.status}
                  primary={`${ws.active_connections ?? 0} active`}
                  message={`${ws.dropped_count ?? 0} dropped — ${ws.message || ''}`}
                  healService={{ name: 'WebSockets' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
                <ProbeCard
                  title="Tool Connections"
                  icon={Server}
                  iconClass="text-violet-400"
                  status={toolsStatus}
                  primary={`${tools.configured_count ?? tools.total ?? 0} configured`}
                  message={
                    tools.message ||
                    `${tools.degraded_count ?? 0} degraded · ${tools.tool_account_count ?? 0} accounts`
                  }
                  healService={{ name: 'Tool Connections' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
                <ProbeCard
                  title="Dependencies"
                  icon={Shield}
                  iconClass="text-green-400"
                  status={secStatus}
                  primary={`${deps.vulnerability_count ?? 0} vulns`}
                  message={deps.message}
                  onDrill={() => setTab('dependencies')}
                  drillLabel="View vulnerabilities"
                  healService={{ name: 'Security' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
                <ProbeCard
                  title="Performance"
                  icon={Activity}
                  iconClass="text-rose-400"
                  status={perfStatus}
                  primary={`${perf.slow_query_count ?? 0} slow queries`}
                  message={perf.message || `Threshold: ${perf.threshold_ms ?? 500}ms`}
                  onDrill={() => setTab('slow-queries')}
                  drillLabel="View slow queries"
                  healService={{ name: 'Performance' }}
                  workspaceId={workspaceId}
                  authFetch={authFetch}
                  canMutate={canMutate}
                />
              </div>

              {connectorCards.length > 0 && (
                <section className="mb-10">
                  <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
                    <Plug className="w-5 h-5 text-violet-300" />
                    Connectors
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
                    {connectorCards.map((c) => (
                      <div
                        key={c.name}
                        className={`rounded-lg border bg-gray-800/80 p-4 ${cardBorder(c.status)} border-gray-700`}
                      >
                        <div className="flex items-center justify-between gap-2">
                          <p className="text-sm font-semibold text-white capitalize">{c.name}</p>
                          <span
                            className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${statusBadgeClasses(c.status)}`}
                          >
                            {statusBadgeLabel(c.status)}
                          </span>
                        </div>
                        {c.latency_ms != null && (
                          <p className="mt-2 text-xs font-mono text-slate-400">{c.latency_ms} ms</p>
                        )}
                        <p className="mt-1 text-xs text-slate-500">{c.message || '—'}</p>
                      </div>
                    ))}
                  </div>
                </section>
              )}

              <RecommendationsPanel recommendations={recommendations} />

              {expiring.length > 0 && (
                <section className="mb-10 rounded-xl border border-amber-500/30 bg-amber-500/5 p-6">
                  <h2 className="text-lg font-semibold text-amber-200 mb-4 flex items-center gap-2">
                    <AlertTriangle className="w-5 h-5" />
                    Credentials Expiring Soon
                  </h2>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm text-left">
                      <thead>
                        <tr className="text-slate-500 border-b border-gray-700">
                          <th className="pb-2 pr-4 font-medium">Account Name</th>
                          <th className="pb-2 pr-4 font-medium">Tool</th>
                          <th className="pb-2 pr-4 font-medium">Expires In</th>
                          <th className="pb-2 font-medium">Action</th>
                        </tr>
                      </thead>
                      <tbody>
                        {expiring.map((row) => {
                          const days = row.expires_in_days
                          const urgent = typeof days === 'number' && days < 3
                          return (
                            <tr
                              key={row.account_id ?? row.account_name}
                              className="border-b border-gray-700/80"
                            >
                              <td className="py-3 pr-4 text-white font-medium">
                                {row.account_name || '—'}
                              </td>
                              <td className="py-3 pr-4 text-slate-300">{row.tool || '—'}</td>
                              <td
                                className={`py-3 pr-4 font-mono ${urgent ? 'text-red-400 font-semibold' : 'text-slate-300'}`}
                              >
                                {typeof days === 'number' ? `${days} days` : '—'}
                              </td>
                              <td className="py-3">
                                <button
                                  type="button"
                                  onClick={() =>
                                    navigate('/integrations', {
                                      state: {
                                        rotateAccountId: row.account_id,
                                        rotateAccountName: row.account_name,
                                        rotateTool: row.tool,
                                      },
                                    })
                                  }
                                  className="px-3 py-1.5 rounded-lg bg-amber-600/30 border border-amber-500/40 text-amber-100 text-xs font-medium hover:bg-amber-600/50"
                                >
                                  Rotate Now
                                </button>
                              </td>
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}

              <section>
                <h2 className="text-lg font-semibold text-white mb-4">
                  Active Alerts ({alerts.length})
                </h2>
                {alerts.length === 0 ? (
                  <div className="flex items-center gap-3 p-6 rounded-xl bg-gray-800/80 border border-gray-700 text-slate-400">
                    <CheckCircle className="w-6 h-6 text-green-500 shrink-0" />
                    <span>No active alerts — system healthy</span>
                  </div>
                ) : (
                  <div className="overflow-x-auto rounded-xl border border-gray-700 bg-gray-800/50">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="text-left text-slate-500 border-b border-gray-700">
                          <th className="p-4 font-medium">Message</th>
                          <th className="p-4 font-medium">Severity</th>
                          <th className="p-4 font-medium">Time Since</th>
                          {canMutate && <th className="p-4 font-medium">Actions</th>}
                        </tr>
                      </thead>
                      <tbody>
                        {alerts.map((alert) => {
                          const msg =
                            (alert.message || '').length > 60
                              ? `${(alert.message || '').slice(0, 60)}…`
                              : alert.message || ''
                          const fading = fadeOutIds.has(alert.id)
                          return (
                            <tr
                              key={alert.id}
                              className={`border-b border-gray-700/80 transition-opacity duration-300 ${fading ? 'opacity-0' : 'opacity-100'}`}
                            >
                              <td className="p-4 text-slate-200 max-w-md">{msg}</td>
                              <td className="p-4">
                                <span
                                  className={`inline-flex rounded-full px-3 py-1 text-xs font-medium capitalize ${severityBadge(alert.severity)}`}
                                >
                                  {alert.severity || 'info'}
                                </span>
                              </td>
                              <td className="p-4 text-slate-400 whitespace-nowrap">
                                {formatRelative(alert.created_at)}
                              </td>
                              {canMutate && (
                                <td className="p-4 whitespace-nowrap">
                                  <button
                                    type="button"
                                    onClick={() => resolveAlert(alert.id)}
                                    className="mr-2 px-2 py-1 rounded-lg text-xs font-medium bg-green-500/15 text-green-300 border border-green-500/30 hover:bg-green-500/25"
                                  >
                                    Resolve
                                  </button>
                                  <button
                                    type="button"
                                    onClick={() => ignoreAlert(alert.id)}
                                    className="px-2 py-1 rounded-lg text-xs font-medium bg-slate-600/40 text-slate-200 border border-slate-500/40 hover:bg-slate-600/60"
                                  >
                                    Ignore
                                  </button>
                                </td>
                              )}
                            </tr>
                          )
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>
            </>
          )}
        </>
      ) : !fetchError ? (
        <div className="text-center py-16 text-slate-500">
          <XCircle className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p>No health payload loaded.</p>
        </div>
      ) : null}

      <p className="mt-10 text-center text-xs text-slate-600">
        Related:{' '}
        <Link to="/scorecards" className="text-slate-400 hover:text-slate-200 underline-offset-2 hover:underline">
          Scorecards
        </Link>
      </p>
    </div>
  )
}
