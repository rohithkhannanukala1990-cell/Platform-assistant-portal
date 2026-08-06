import { useEffect, useState, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import {
  Plug, Copy, CheckCheck, RefreshCw, Activity,
  GitBranch, Database, Cloud, Bell, Clock,
  AlertTriangle, CheckCircle2, Loader2, ShieldAlert,
  Zap, Terminal,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'

const GATEWAY_PATH = '/api/webhooks/inbound'
const ACTIVITY_PATH = '/api/webhooks/activity'
const GATEWAY_URL = `${API_BASE}${GATEWAY_PATH}`
const ACTIVITY_URL = ACTIVITY_PATH

// ── Webhook source catalogue ──────────────────────────────────────────────────
const INTEGRATIONS = [
  {
    id: 'github',
    label: 'GitHub',
    icon: GitBranch,
    color: 'text-slate-300',
    bg: 'bg-slate-500/10 border-slate-500/25',
    role: 'Developer',
    roleColor: 'text-blue-400',
    events: ['push', 'pull_request', 'workflow_run', 'deployment'],
    example: { source: 'github', event_type: 'push', payload: { action: 'push', message: 'feat: deploy auth-service v2.5', head_commit: { message: 'feat: deploy auth-service v2.5 — bumped memory limit' } } },
  },
  {
    id: 'airflow',
    label: 'Apache Airflow',
    icon: Zap,
    color: 'text-green-400',
    bg: 'bg-green-500/10 border-green-500/25',
    role: 'DataEngineer',
    roleColor: 'text-cyan-400',
    events: ['dag_failure', 'task_failure', 'sla_miss'],
    example: { source: 'airflow', event_type: 'dag_failure', payload: { dag_id: 'sales_reconciliation_etl', message: 'DAG sales_reconciliation_etl failed at task transform_sales. OOM error: 16GB exceeded.' } },
  },
  {
    id: 'snowflake',
    label: 'Snowflake',
    icon: Database,
    color: 'text-cyan-400',
    bg: 'bg-cyan-500/10 border-cyan-500/25',
    role: 'DataEngineer',
    roleColor: 'text-cyan-400',
    events: ['query_failure', 'warehouse_suspended', 'storage_alert'],
    example: { source: 'snowflake', event_type: 'warehouse_suspended', payload: { event: 'warehouse_suspended', message: 'COMPUTE_WH warehouse auto-suspended after 60min idle. 3 active queries were killed.' } },
  },
  {
    id: 'datadog',
    label: 'Datadog',
    icon: Activity,
    color: 'text-purple-400',
    bg: 'bg-purple-500/10 border-purple-500/25',
    role: 'NetworkEngineer',
    roleColor: 'text-amber-400',
    events: ['alert', 'no-data', 'recovered', 'renotify'],
    example: { source: 'datadog', event_type: 'alert', payload: { alert_type: 'alert', body: 'CPU utilization on prod-api-3 exceeded 95% for 5 consecutive minutes. Auto-scaling triggered but lag increasing.' } },
  },
  {
    id: 'aws',
    label: 'AWS CloudWatch',
    icon: Cloud,
    color: 'text-orange-400',
    bg: 'bg-orange-500/10 border-orange-500/25',
    role: 'NetworkEngineer',
    roleColor: 'text-amber-400',
    events: ['AlarmStateChange', 'EC2_Instance_State-change', 'ECS_Task_State_Change'],
    example: { source: 'aws', event_type: 'AlarmStateChange', payload: { Type: 'Notification', Message: 'ALARM: prod-rds-cpu-high. RDS CPU at 94%. Threshold: 80%. State: ALARM.' } },
  },
  {
    id: 'pagerduty',
    label: 'PagerDuty',
    icon: Bell,
    color: 'text-green-400',
    bg: 'bg-green-500/10 border-green-500/25',
    role: 'NetworkEngineer',
    roleColor: 'text-amber-400',
    events: ['incident.trigger', 'incident.acknowledge', 'incident.resolve'],
    example: { source: 'pagerduty', event_type: 'incident.trigger', payload: { event: 'incident.trigger', message: 'High error rate on payment-service: 12% of requests returning 500. SLO breach imminent.' } },
  },
  {
    id: 'rds',
    label: 'AWS RDS',
    icon: Database,
    color: 'text-rose-400',
    bg: 'bg-rose-500/10 border-rose-500/25',
    role: 'DatabaseDeveloper',
    roleColor: 'text-rose-400',
    events: ['failover', 'low-storage', 'maintenance', 'backup-failure'],
    example: { source: 'rds', event_type: 'low-storage', payload: { event: 'low-storage', message: 'prod-postgres-primary: free storage below 10% (4.8 GB remaining of 500 GB). Automatic storage scaling triggered.' } },
  },
  {
    id: 'mongodb',
    label: 'MongoDB Atlas',
    icon: Database,
    color: 'text-green-400',
    bg: 'bg-green-500/10 border-green-500/25',
    role: 'DatabaseDeveloper',
    roleColor: 'text-rose-400',
    events: ['replication-lag', 'oplog-window', 'index-build-failure', 'disk-alert'],
    example: { source: 'mongodb', event_type: 'replication-lag', payload: { event: 'replication-lag', message: 'MongoDB Atlas: replication lag on secondary node exceeded 60s. Primary cluster: prod-atlas-m30. Risk of data loss on failover.' } },
  },
  {
    id: 'postgresql',
    label: 'PostgreSQL',
    icon: Database,
    color: 'text-blue-400',
    bg: 'bg-blue-500/10 border-blue-500/25',
    role: 'DatabaseDeveloper',
    roleColor: 'text-rose-400',
    events: ['connection-limit', 'deadlock', 'vacuum-failure', 'slow-query'],
    example: { source: 'postgresql', event_type: 'connection-limit', payload: { event: 'connection-limit', message: 'prod-postgres-primary: connection pool at 95% capacity (190/200). New connections are being queued. Review pg_stat_activity.' } },
  },
]

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_CFG = {
  accepted:  { cls: 'bg-blue-500/10 border-blue-500/25 text-blue-400',    icon: Clock,         label: 'Queued'    },
  processed: { cls: 'bg-green-500/10 border-green-500/25 text-green-400', icon: CheckCircle2,  label: 'Processed' },
  error:     { cls: 'bg-red-500/10 border-red-500/25 text-red-400',       icon: AlertTriangle, label: 'Error'     },
}

const ROLE_COLORS = {
  Developer:       'text-blue-400',
  DataEngineer:    'text-cyan-400',
  NetworkEngineer: 'text-amber-400',
  Admin:           'text-purple-400',
}

function CopyButton({ text, label = '' }) {
  const [copied, setCopied] = useState(false)
  function copy() {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }
  return (
    <button
      onClick={copy}
      className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg border border-border
        hover:bg-card transition-colors text-xs text-slate-400 hover:text-white shrink-0"
      title={`Copy ${label}`}
    >
      {copied ? <CheckCheck className="w-3.5 h-3.5 text-green-400" /> : <Copy className="w-3.5 h-3.5" />}
      {copied ? 'Copied!' : 'Copy'}
    </button>
  )
}

function ActivityRow({ ev }) {
  const cfg  = STATUS_CFG[ev.status] ?? STATUS_CFG.accepted
  const Icon = cfg.icon
  const rc   = ROLE_COLORS[ev.owner_role] ?? 'text-slate-400'

  return (
    <div className="flex items-center gap-3 px-4 py-2.5 border-b border-border/50 hover:bg-card/40 transition-colors">
      <div className={`flex items-center justify-center w-7 h-7 rounded-full border shrink-0 ${cfg.cls}`}>
        <Icon className="w-3.5 h-3.5" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs font-semibold text-white font-mono">{ev.source}</span>
          {ev.event_type && (
            <span className="text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-1.5 py-0.5 rounded font-mono">
              {ev.event_type}
            </span>
          )}
          <span className={`text-[10px] font-semibold ${rc}`}>→ {ev.owner_role}</span>
        </div>
        {ev.incident_id && (
          <p className="text-[10px] text-slate-600 mt-0.5">Incident #{ev.incident_id} created</p>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-semibold ${cfg.cls}`}>
          {cfg.label}
        </span>
        <span className="text-[10px] text-slate-600">
          {new Date(ev.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
        </span>
      </div>
    </div>
  )
}

export default function IntegrationsPage() {
  const { role, authFetch } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const [activity, setActivity]   = useState([])
  const [loadingAct, setLoadingAct] = useState(false)
  const [firing, setFiring]       = useState(null)    // integration id being test-fired
  const [fired, setFired]         = useState(new Set())

  const fetchActivity = useCallback(async () => {
    setLoadingAct(true)
    try {
      const res = await authFetch(ACTIVITY_URL)
      if (res.ok) setActivity(await res.json())
    } catch (_) {}
    finally { setLoadingAct(false) }
  }, [authFetch])

  useEffect(() => {
    fetchActivity()
    const t = setInterval(fetchActivity, 8000)
    return () => clearInterval(t)
  }, [fetchActivity])

  async function testFire(integration) {
    setFiring(integration.id)
    try {
      await authFetch(GATEWAY_PATH, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(integration.example),
      })
      setFired((p) => new Set([...p, integration.id]))
      setTimeout(fetchActivity, 1500)
    } catch (_) {}
    finally { setFiring(null) }
  }

  if (role !== 'Admin') {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-3 text-slate-500">
        <ShieldAlert className="w-8 h-8 text-red-500/60" />
        <p className="text-sm">Integrations is restricted to <span className="text-purple-400 font-semibold">Admins</span> only.</p>
      </div>
    )
  }

  const processed = activity.filter(e => e.status === 'processed').length
  const errors    = activity.filter(e => e.status === 'error').length
  const queued    = activity.filter(e => e.status === 'accepted').length

  const rotateName = location.state?.rotateAccountName

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      <div className="rounded-xl border border-border bg-card/40 p-4">
        <p className="text-sm font-semibold text-white">First-class connectors vs MCP</p>
        <p className="text-xs text-slate-400 mt-1 leading-relaxed">
          Slack, Prometheus, Argo CD, Outbound Webhook, GitHub, Kubernetes, and PagerDuty are
          first-class Tool Registry connectors (scoped accounts, read-first ops panels).
          MCP remains the long-tail protocol for edge tools — it does not replace these connectors.
        </p>
        <div className="flex flex-wrap gap-2 mt-3">
          {[
            ['/tool-registry', 'Tool Registry'],
            ['/slack', 'Slack'],
            ['/prometheus', 'Prometheus'],
            ['/argocd', 'Argo CD'],
            ['/outbound-webhook', 'Outbound Webhook'],
            ['/k8s', 'Kubernetes'],
            ['/pagerduty', 'PagerDuty'],
          ].map(([to, label]) => (
            <button
              key={to}
              type="button"
              onClick={() => navigate(to)}
              className="px-2.5 py-1 rounded-lg border border-border text-[11px] text-slate-300 hover:text-white hover:bg-card"
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {rotateName && (
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-100">
          <p className="text-sm">
            <span className="font-semibold text-amber-200">Credential rotation:</span>{' '}
            review integration credentials for <strong className="text-white">{rotateName}</strong>
            {location.state?.rotateTool ? (
              <span className="text-amber-200/90"> ({location.state.rotateTool})</span>
            ) : null}
            .
          </p>
          <button
            type="button"
            onClick={() => navigate('.', { replace: true, state: {} })}
            className="shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-amber-900/40 border border-amber-600/50 hover:bg-amber-900/60 text-amber-50"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Plug className="w-5 h-5 text-purple-400" />
            Webhook Gateway
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Inbound event routing for GitHub, Airflow, Snowflake, AWS, Datadog and more
          </p>
        </div>
        <span className="px-3 py-1.5 rounded-lg border border-purple-500/25 bg-purple-500/10 text-purple-400 text-xs font-semibold">
          🛡️ Admin Only
        </span>
      </div>

      {/* Gateway URL banner */}
      <div className="flex flex-col gap-3 p-5 rounded-2xl border border-purple-500/20 bg-purple-500/5">
        <div className="flex items-center gap-2 mb-1">
          <Terminal className="w-4 h-4 text-purple-400" />
          <p className="text-sm font-bold text-white">Universal Inbound Gateway URL</p>
        </div>
        <div className="flex items-center gap-2 bg-black/50 border border-border rounded-xl px-4 py-3 font-mono text-sm">
          <span className="text-slate-400">POST</span>
          <span className="text-purple-300 flex-1 truncate">{GATEWAY_URL}</span>
          <CopyButton text={GATEWAY_URL} label="URL" />
        </div>
        <p className="text-xs text-slate-600">
          Send <code className="text-slate-400">{"{ source, event_type, payload }"}</code> — the gateway auto-routes by source and returns{' '}
          <code className="text-slate-400">202 Accepted</code> immediately.
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Events Processed', value: processed, cls: 'border-green-500/20 bg-green-500/5 text-green-400' },
          { label: 'Events Queued',    value: queued,    cls: 'border-blue-500/20  bg-blue-500/5  text-blue-400'  },
          { label: 'Processing Errors', value: errors,   cls: 'border-red-500/20   bg-red-500/5   text-red-400'   },
        ].map(({ label, value, cls }) => (
          <div key={label} className={`flex items-center gap-3 px-5 py-4 rounded-2xl border ${cls}`}>
            <span className="text-3xl font-bold text-white">{value}</span>
            <span className="text-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Integration cards */}
      <div>
        <h2 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
          <Plug className="w-4 h-4 text-slate-400" />
          Configured Source Integrations
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {INTEGRATIONS.map((intg) => {
            const Icon   = intg.icon
            const isFire = firing === intg.id
            const done   = fired.has(intg.id)

            const curlCmd = `curl -s -X POST ${GATEWAY_URL} \\
  -H "Content-Type: application/json" \\
  -d '${JSON.stringify({ source: intg.id, event_type: intg.events[0], payload: { message: `Test event from ${intg.label}` } })}'`

            return (
              <div key={intg.id}
                className="flex flex-col gap-4 p-4 rounded-2xl border border-border bg-card hover:border-slate-600 transition-all"
              >
                {/* Header */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2.5">
                    <div className={`flex items-center justify-center w-9 h-9 rounded-xl border ${intg.bg} shrink-0`}>
                      <Icon className={`w-4 h-4 ${intg.color}`} />
                    </div>
                    <div>
                      <p className="text-sm font-bold text-white">{intg.label}</p>
                      <p className={`text-[10px] font-semibold ${intg.roleColor}`}>→ {intg.role}</p>
                    </div>
                  </div>
                  <span className="text-[10px] text-green-400 border border-green-500/25 bg-green-500/10 px-2 py-0.5 rounded-full font-semibold">
                    Active
                  </span>
                </div>

                {/* Events */}
                <div className="flex flex-wrap gap-1.5">
                  {intg.events.map(e => (
                    <span key={e} className="text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded font-mono">
                      {e}
                    </span>
                  ))}
                </div>

                {/* Webhook URL */}
                <div className="flex items-center gap-2 bg-black/40 border border-border rounded-lg px-3 py-2">
                  <span className="text-[10px] text-slate-500 font-mono flex-1 truncate">
                    source=<span className="text-slate-300">{intg.id}</span>
                  </span>
                  <CopyButton text={curlCmd} label="cURL" />
                </div>

                {/* Test fire */}
                <div className="flex items-center justify-between pt-1 border-t border-border">
                  <p className="text-[10px] text-slate-600">Send a test event to the gateway</p>
                  {done ? (
                    <span className="flex items-center gap-1 text-[11px] text-green-400 font-semibold">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Sent
                    </span>
                  ) : (
                    <button
                      onClick={() => testFire(intg)}
                      disabled={!!firing}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[11px] font-semibold
                        bg-purple-500/10 border border-purple-500/25 text-purple-400
                        hover:bg-purple-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {isFire
                        ? <><Loader2 className="w-3 h-3 animate-spin" /> Firing…</>
                        : <><Zap className="w-3 h-3" /> Test Fire</>
                      }
                    </button>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Recent activity feed */}
      <div className="flex flex-col rounded-2xl border border-border bg-card overflow-hidden">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <div className="flex items-center gap-2">
            <Activity className="w-4 h-4 text-accent" />
            <h3 className="text-sm font-bold text-white">Recent Webhook Activity</h3>
            {activity.length > 0 && (
              <span className="text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-full">
                {activity.length} events
              </span>
            )}
          </div>
          <button
            onClick={fetchActivity}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border
              hover:bg-card/60 transition-colors text-xs text-slate-400 hover:text-white"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingAct ? 'animate-spin text-accent' : ''}`} />
            Refresh
          </button>
        </div>

        {activity.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-12 gap-2 text-slate-600">
            <Plug className="w-6 h-6" />
            <p className="text-sm">No webhook events yet.</p>
            <p className="text-xs">Use "Test Fire" on any integration card above to send a sample event.</p>
          </div>
        ) : (
          <div className="flex flex-col overflow-y-auto max-h-96">
            {activity.map((ev) => <ActivityRow key={ev.id} ev={ev} />)}
          </div>
        )}
      </div>
    </div>
  )
}
