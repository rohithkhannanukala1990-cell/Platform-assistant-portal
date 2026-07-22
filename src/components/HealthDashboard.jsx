import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
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
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'

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
  return 'bg-green-500/20 text-green-300 border border-green-500/30'
}

function statusBadgeLabel(status) {
  if (status === 'critical') return '🔴 Critical'
  if (status === 'warning') return '🟡 Warning'
  return '🟢 Healthy'
}

function cardBorder(status) {
  if (status === 'critical') return 'border-red-500/30'
  if (status === 'warning') return 'border-yellow-500/30'
  return 'border-green-500/30'
}

function severityBadge(sev) {
  const s = (sev || 'info').toLowerCase()
  if (s === 'critical') return 'bg-red-500/20 text-red-400 border border-red-500/25'
  if (s === 'warning') return 'bg-yellow-500/20 text-yellow-400 border border-yellow-500/25'
  return 'bg-blue-500/20 text-blue-400 border border-blue-500/25'
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

export default function HealthDashboard() {
  const { authFetch, role } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const workspaceId = activeWorkspace?.id ?? ''
  const navigate = useNavigate()

  const [healthData, setHealthData] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isHealing, setIsHealing] = useState(false)
  const [lastChecked, setLastChecked] = useState(null)
  const [autoRefreshTimer, setAutoRefreshTimer] = useState(60)
  const [fetchError, setFetchError] = useState(false)
  const [toast, setToast] = useState(null)
  const [fadeOutIds, setFadeOutIds] = useState(() => new Set())

  const showToast = useCallback((message) => {
    setToast(message)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchHealthRef = useRef(async () => {})

  const fetchHealth = useCallback(async () => {
    setFetchError(false)
    try {
      const [fullRes, alertsRes] = await Promise.all([
        authFetch('/api/health/full'),
        authFetch('/api/health/alerts'),
      ])
      if (!fullRes.ok || !alertsRes.ok) {
        setFetchError(true)
        setHealthData(null)
        setAlerts([])
        return
      }
      const full = await fullRes.json()
      const list = await alertsRes.json()
      setHealthData(full)
      setAlerts(Array.isArray(list) ? list : [])
      setLastChecked(new Date().toLocaleString())
      setAutoRefreshTimer(60)
    } catch {
      setFetchError(true)
      setHealthData(null)
      setAlerts([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch])

  fetchHealthRef.current = fetchHealth

  useEffect(() => {
    if (role === 'Admin') fetchHealth()
    else setIsLoading(false)
  }, [fetchHealth, role])

  useEffect(() => {
    if (role !== 'Admin') return undefined
    const onWorkspace = () => {
      void fetchHealthRef.current()
    }
    window.addEventListener('active-workspace-changed', onWorkspace)
    window.addEventListener('context-changed', onWorkspace)
    return () => {
      window.removeEventListener('active-workspace-changed', onWorkspace)
      window.removeEventListener('context-changed', onWorkspace)
    }
  }, [role])

  useEffect(() => {
    if (role !== 'Admin') return undefined
    const id = window.setInterval(() => {
      setAutoRefreshTimer((c) => {
        if (c <= 1) {
          window.queueMicrotask(() => {
            void fetchHealthRef.current()
          })
          return 60
        }
        return c - 1
      })
    }, 1000)
    return () => window.clearInterval(id)
  }, [role])

  async function runHeal() {
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
    try {
      const res = await authFetch('/api/health/alerts/email', { method: 'POST' })
      if (res.ok) showToast('Alerts emailed to team')
      else showToast('Email request failed')
    } catch {
      showToast('Email request failed')
    }
  }

  async function resolveAlert(id) {
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

  if (role !== 'Admin') {
    return (
      <div className="max-w-lg mx-auto mt-20 text-center space-y-4">
        <Shield className="w-12 h-12 mx-auto text-amber-500/70" />
        <h1 className="text-xl font-semibold text-white">System Health</h1>
        <p className="text-slate-400 text-sm">
          This dashboard is restricted to <span className="text-purple-400 font-medium">Admin</span>{' '}
          users only.
        </p>
      </div>
    )
  }

  const db = healthData?.database || {}
  const redis = healthData?.redis || {}
  const ws = healthData?.websockets || {}
  const tools = healthData?.tools || {}
  const deps = healthData?.dependencies || {}
  const perf = healthData?.performance || {}

  const toolsStatus =
    (tools.degraded_count || 0) > 0 || (tools.expiring_count || 0) > 0 ? 'warning' : 'healthy'
  const secStatus = (deps.vulnerability_count || 0) > 0 ? 'warning' : 'healthy'
  const perfStatus = (perf.slow_query_count || 0) > 0 ? 'warning' : 'healthy'

  const expiring = Array.isArray(tools.expiring) ? tools.expiring : []

  const healthServices = [
    { name: 'Database', status: healthRowStatus(db.status) },
    { name: 'Redis Cache', status: healthRowStatus(redis.status) },
    { name: 'WebSockets', status: healthRowStatus(ws.status) },
    { name: 'Tool Connections', status: healthRowStatus(toolsStatus) },
    { name: 'Security', status: healthRowStatus(secStatus) },
    { name: 'Performance', status: healthRowStatus(perfStatus) },
  ]

  return (
    <div className="max-w-7xl mx-auto pb-16 px-4 sm:px-6 lg:px-8">
      {toast && (
        <div className="fixed top-20 right-6 z-50 px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}

      {/* Header */}
      <header className="py-8 border-b border-gray-700 mb-8">
        <div className="flex flex-col lg:flex-row lg:items-end lg:justify-between gap-6">
          <div>
            <h1 className="text-2xl font-bold text-white tracking-tight">System Health</h1>
            <p className="mt-2 text-sm text-slate-400 flex flex-wrap items-center gap-x-3 gap-y-1">
              <Clock className="w-4 h-4 inline shrink-0 text-slate-500" aria-hidden />
              <span>
                Last checked: {lastChecked || '—'} | Auto-refresh in {autoRefreshTimer}s
              </span>
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => {
                setIsLoading(true)
                fetchHealth()
              }}
              disabled={isLoading}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-gray-800 border border-gray-600
                text-sm font-medium text-white hover:bg-gray-700 disabled:opacity-50 transition-colors"
            >
              <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
              Refresh Now
            </button>
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
          </div>
        </div>
      </header>

      {fetchError && !isLoading && (
        <div className="mb-8 flex flex-col sm:flex-row items-start sm:items-center gap-4 p-4 rounded-xl bg-yellow-500/10 border border-yellow-500/30 text-yellow-200">
          <AlertTriangle className="w-6 h-6 shrink-0" />
          <div className="flex-1">
            <p className="font-medium">Health data unavailable</p>
            <p className="text-sm text-yellow-200/80 mt-1">Check API connectivity or admin session.</p>
          </div>
          <button
            type="button"
            onClick={() => {
              setIsLoading(true)
              fetchHealth()
            }}
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
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mb-10">
            {/* Database */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(db.status)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Database className="w-8 h-8 text-slate-300 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(db.status)}`}>
                    {statusBadgeLabel(db.status)}
                  </span>
                  {(healthServices[0].status === 'degraded' ||
                    healthServices[0].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[0]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">Database</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">
                {db.latency_ms != null ? `${db.latency_ms} ms` : '—'}
              </p>
              <p className="mt-2 text-sm text-slate-400">{db.message || '—'}</p>
            </div>

            {/* Redis */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(redis.status)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Zap className="w-8 h-8 text-amber-400 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(redis.status)}`}>
                    {statusBadgeLabel(redis.status)}
                  </span>
                  {(healthServices[1].status === 'degraded' ||
                    healthServices[1].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[1]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">Redis Cache</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">
                {redis.latency_ms != null ? `${redis.latency_ms} ms` : '—'}
              </p>
              <p className="mt-2 text-sm text-slate-400">{redis.message || '—'}</p>
            </div>

            {/* WebSockets */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(ws.status)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Wifi className="w-8 h-8 text-cyan-400 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(ws.status)}`}>
                    {statusBadgeLabel(ws.status)}
                  </span>
                  {(healthServices[2].status === 'degraded' ||
                    healthServices[2].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[2]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">WebSockets</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">
                {(ws.active_connections ?? 0)} active
              </p>
              <p className="mt-2 text-sm text-slate-400">
                {(ws.dropped_count ?? 0)} dropped — {ws.message || ''}
              </p>
            </div>

            {/* Tools */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(toolsStatus)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Server className="w-8 h-8 text-violet-400 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(toolsStatus)}`}>
                    {statusBadgeLabel(toolsStatus)}
                  </span>
                  {(healthServices[3].status === 'degraded' ||
                    healthServices[3].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[3]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">Tool Connections</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">{(tools.total ?? 0)} accounts</p>
              <p className="mt-2 text-sm text-slate-400">
                {(tools.degraded_count ?? 0)} degraded, {(tools.expiring_count ?? 0)} expiring
              </p>
            </div>

            {/* Security / dependencies */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(secStatus)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Shield className="w-8 h-8 text-green-400 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(secStatus)}`}>
                    {statusBadgeLabel(secStatus)}
                  </span>
                  {(healthServices[4].status === 'degraded' ||
                    healthServices[4].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[4]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">Security</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">
                {(deps.vulnerability_count ?? 0)} vulns
              </p>
              <p className="mt-2 text-sm text-slate-400">{deps.message || '—'}</p>
            </div>

            {/* Performance */}
            <div
              className={`bg-gray-800 rounded-xl p-6 border ${cardBorder(perfStatus)} border-gray-700`}
            >
              <div className="flex items-start justify-between gap-3">
                <Activity className="w-8 h-8 text-rose-400 shrink-0" />
                <div className="flex flex-col items-end gap-2">
                  <span className={`rounded-full px-3 py-1 text-sm font-medium ${statusBadgeClasses(perfStatus)}`}>
                    {statusBadgeLabel(perfStatus)}
                  </span>
                  {(healthServices[5].status === 'degraded' ||
                    healthServices[5].status === 'down') && (
                    <AutoHealButton
                      service={healthServices[5]}
                      workspaceId={workspaceId}
                      authFetch={authFetch}
                    />
                  )}
                </div>
              </div>
              <h2 className="mt-4 text-lg font-semibold text-white">Performance</h2>
              <p className="mt-1 text-2xl font-mono text-slate-200">
                {(perf.slow_query_count ?? 0)} slow queries
              </p>
              <p className="mt-2 text-sm text-slate-400">Threshold: 500ms</p>
            </div>
          </div>

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
                        <tr key={row.account_id ?? row.account_name} className="border-b border-gray-700/80">
                          <td className="py-3 pr-4 text-white font-medium">{row.account_name || '—'}</td>
                          <td className="py-3 pr-4 text-slate-300">{row.tool || '—'}</td>
                          <td className={`py-3 pr-4 font-mono ${urgent ? 'text-red-400 font-semibold' : 'text-slate-300'}`}>
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

          {/* Alerts */}
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
                      <th className="p-4 font-medium">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((alert) => {
                      const msg = (alert.message || '').length > 60
                        ? `${(alert.message || '').slice(0, 60)}…`
                        : (alert.message || '')
                      const fading = fadeOutIds.has(alert.id)
                      return (
                        <tr
                          key={alert.id}
                          className={`border-b border-gray-700/80 transition-opacity duration-300 ${fading ? 'opacity-0' : 'opacity-100'}`}
                        >
                          <td className="p-4 text-slate-200 max-w-md">{msg}</td>
                          <td className="p-4">
                            <span className={`inline-flex rounded-full px-3 py-1 text-xs font-medium capitalize ${severityBadge(alert.severity)}`}>
                              {alert.severity || 'info'}
                            </span>
                          </td>
                          <td className="p-4 text-slate-400 whitespace-nowrap">
                            {formatRelative(alert.created_at)}
                          </td>
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
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        </>
      ) : !fetchError ? (
        <div className="text-center py-16 text-slate-500">
          <XCircle className="w-10 h-10 mx-auto mb-3 opacity-50" />
          <p>No health payload loaded.</p>
        </div>
      ) : null}
    </div>
  )
}
