import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell,
  PieChart, Pie,
  LineChart, Line, CartesianGrid,
} from 'recharts'
import {
  AlertTriangle, Activity, Layers, RefreshCw, Clock, Wifi,
  Package, ShieldCheck, Zap, BookOpen,
} from 'lucide-react'
import AgentApprovalsWidget from './AgentApprovalsWidget'
import OncallWidget from './OncallWidget'
import DoraStrip from './dashboard/DoraStrip'
import AwsCostCard from './dashboard/AwsCostCard'
import LogScannerCard from './dashboard/LogScannerCard'
import { Card, StatCard, PageHeader, EmptyState } from './ui'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'
import useDashboardData from '../hooks/useDashboardData'

const API = `${API_BASE}/api/analytics`
const DORA_API = `${API_BASE}/api/cicd/dora-metrics`
const REPORTS_API = `${API_BASE}/api/reports`

const SEVERITY_COLORS = {
  Critical: '#ef4444',
  High: '#f97316',
  Medium: '#eab308',
  Warning: '#f59e0b',
  Low: '#3b82f6',
  Unknown: '#6b7280',
}

function DarkTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-sidebar border border-border rounded-xl px-3 py-2.5 shadow-xl text-xs">
      {label && <p className="text-slate-400 mb-1 font-semibold">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color ?? p.fill ?? '#6366f1' }}>
          {p.name}: <span className="font-bold text-white">{p.value}</span>
        </p>
      ))}
    </div>
  )
}

function DonutLabel({ cx, cy, total }) {
  return (
    <>
      <text x={cx} y={cy - 8} textAnchor="middle" fill="#fff" fontSize={28} fontWeight={700}>
        {total}
      </text>
      <text x={cx} y={cy + 14} textAnchor="middle" fill="#64748b" fontSize={11}>
        total
      </text>
    </>
  )
}

export default function DashboardView() {
  const { authFetch } = useAuth()
  const { data, isLoading, error, refetch } = useDashboardData()
  const [analyticsData, setAnalyticsData] = useState(null)
  const [analyticsLoading, setAnalyticsLoading] = useState(true)
  const [lastFetch, setLastFetch] = useState(null)
  const [platform, setPlatform] = useState(null)
  const [standardsStats, setStandardsStats] = useState(null)
  const [openActionsCount, setOpenActionsCount] = useState(0)
  const [dora, setDora] = useState(null)

  async function fetchPlatformSummary() {
    try {
      const [catRes, stdRes, scoreRes, pathsRes, actionsRes] = await Promise.all([
        authFetch(`${REPORTS_API}/catalog-overview`),
        authFetch(`${REPORTS_API}/standards-overview`),
        authFetch(`${REPORTS_API}/scorecards-overview`),
        authFetch(`${API_BASE}/api/golden-paths`),
        authFetch(`${API_BASE}/api/entity-actions`),
      ])
      const next = {}
      if (catRes.ok) next.catalog = await catRes.json()
      if (stdRes.ok) next.standards = await stdRes.json()
      if (scoreRes.ok) next.scorecards = await scoreRes.json()
      if (pathsRes.ok) {
        const paths = await pathsRes.json()
        next.goldenPathCount = Array.isArray(paths) ? paths.length : 0
      }
      if (actionsRes.ok) {
        const actions = await actionsRes.json()
        next.actionCount = Array.isArray(actions) ? actions.length : 0
      }
      setPlatform(next)
    } catch {
      /* optional summary */
    }
  }

  async function fetchAnalytics() {
    setAnalyticsLoading(true)
    try {
      const [res, doraRes] = await Promise.all([authFetch(API), authFetch(DORA_API)])
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      setAnalyticsData(await res.json())
      setLastFetch(new Date())
      if (doraRes.ok) setDora(await doraRes.json())
      void fetchPlatformSummary()
    } catch {
      /* surfaced via analyticsData remaining null */
    } finally {
      setAnalyticsLoading(false)
    }
  }

  useEffect(() => {
    void fetchAnalytics()
  }, [])

  useEffect(() => {
    async function loadPortalKpis() {
      try {
        const stdRes = await authFetch(`${REPORTS_API}/standards-overview`)
        if (stdRes.ok) setStandardsStats(await stdRes.json())
      } catch {
        /* optional */
      }
      try {
        const runsRes = await authFetch(`${API_BASE}/api/entity-action-runs`)
        if (runsRes.ok) {
          const d = await runsRes.json()
          const runs = d.runs || d || []
          setOpenActionsCount(runs.filter((r) => r.status === 'pending').length)
        }
      } catch {
        /* optional */
      }
    }
    void loadPortalKpis()
  }, [authFetch])

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-slate-500">
        <RefreshCw className="w-5 h-5 animate-spin text-accent" />
        <span className="text-sm">Loading...</span>
      </div>
    )
  }

  if (error) {
    return (
      <div className="error-state flex flex-col items-center justify-center h-64 gap-2 text-red-400 text-sm">
        {error}{' '}
        <button
          type="button"
          onClick={refetch}
          className="mt-2 px-4 py-2 rounded-lg border border-red-500/30 hover:bg-red-500/10 text-xs transition-colors"
        >
          Retry
        </button>
      </div>
    )
  }

  const d = analyticsData
  const sev = d?.incidents_by_severity ?? []
  const sources = d?.top_sources ?? []
  const overtime = d?.incidents_over_time ?? []
  const sevTotal = sev.reduce((s, i) => s + i.value, 0)

  const doraFromSummary = data?.dora
    ? {
        deployment_frequency: {
          value: data.dora.deployment_frequency,
          level: 'High',
          trend: 'from dashboard summary',
          trend_dir: 'flat',
        },
        lead_time: {
          value: `${data.dora.lead_time_hours}h`,
          level: 'High',
          trend: 'from dashboard summary',
          trend_dir: 'flat',
        },
        change_failure_rate: {
          value: `${Math.round((data.dora.change_failure_rate || 0) * 100)}%`,
          level: 'High',
          trend: 'from dashboard summary',
          trend_dir: 'flat',
        },
        mttr: {
          value: `${data.dora.mttr_hours}h`,
          level: 'High',
          trend: 'from dashboard summary',
          trend_dir: 'flat',
        },
      }
    : dora

  const catalogTotal = data?.services?.total ?? platform?.catalog?.total_entities ?? '—'
  const standardsPct = platform?.standards?.pass_rate_pct != null
    ? `${platform.standards.pass_rate_pct}%`
    : standardsStats?.total_evaluated
      ? `${Math.round((standardsStats.passed / standardsStats.total_evaluated) * 100)}%`
      : '—'

  return (
    <div className="flex flex-col gap-6 animate-fade-in">
      {data?.mock === true && (
        <div className="bg-amber-500/10 border border-amber-500/30 text-amber-200 px-4 py-2 rounded-xl text-sm">
          Dashboard is showing sample data — connect your data sources to see live metrics
        </div>
      )}

      <PageHeader
        title="Dashboard"
        subtitle="Platform-wide health and activity"
        actions={(
          <div className="flex items-center gap-3">
            {lastFetch && (
              <span className="text-[10px] text-slate-600">
                Updated {lastFetch.toLocaleTimeString()}
              </span>
            )}
            <button
              type="button"
              onClick={() => { void fetchAnalytics(); refetch() }}
              disabled={analyticsLoading || isLoading}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white disabled:opacity-40"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${analyticsLoading || isLoading ? 'animate-spin' : ''}`} />
              Refresh
            </button>
          </div>
        )}
      />

      {/* Single KPI row — merged catalog / standards / actions / incidents / critical */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
        <StatCard
          to="/catalog"
          icon={BookOpen}
          iconClass="bg-accent/15 text-accent"
          label="Catalog Entities"
          value={catalogTotal}
          sub={
            data?.services
              ? `${data.services.healthy} healthy · ${data.services.degraded} degraded`
              : platform?.catalog?.missing_owner
                ? `${platform.catalog.missing_owner} missing owner`
                : undefined
          }
        />
        <StatCard
          to="/standards"
          icon={ShieldCheck}
          iconClass="bg-success/15 text-emerald-400"
          label="Standards Compliance"
          value={standardsPct}
          sub={`${standardsStats?.passed ?? platform?.standards?.passed ?? 0} passed`}
        />
        <StatCard
          to="/entity-actions"
          icon={Zap}
          iconClass="bg-warning/15 text-amber-400"
          label="Open Actions"
          value={data?.open_incidents ?? openActionsCount}
          sub="pending runs"
        />
        <StatCard
          icon={Layers}
          iconClass="bg-accent/15 text-accent"
          label="Total Incidents"
          value={data?.open_incidents ?? d?.total_incidents}
          sub="Open / all time"
        />
        <StatCard
          icon={AlertTriangle}
          iconClass="bg-danger/15 text-red-400"
          label="Critical Alerts"
          value={d?.critical_alerts}
          sub={
            d?.total_incidents
              ? `${Math.round((d.critical_alerts / d.total_incidents) * 100)}% of total`
              : undefined
          }
        />
      </div>

      <DoraStrip dora={doraFromSummary} />

      {/* Two-column body: charts + cost | right rail */}
      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        <div className="xl:col-span-8 flex flex-col gap-4">
          <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
            <Card title="Incidents by Severity" icon={Activity} iconColor="text-red-400" className="lg:col-span-2">
              {sev.length === 0 ? (
                <EmptyState title="No incidents yet" className="py-8" />
              ) : (
                <>
                  <ResponsiveContainer width="100%" height={200}>
                    <PieChart>
                      <Pie
                        data={sev}
                        cx="50%"
                        cy="50%"
                        innerRadius={55}
                        outerRadius={80}
                        paddingAngle={3}
                        dataKey="value"
                        stroke="none"
                      >
                        {sev.map((entry) => (
                          <Cell key={entry.name} fill={SEVERITY_COLORS[entry.name] ?? '#6b7280'} />
                        ))}
                      </Pie>
                      <Tooltip content={<DarkTooltip />} />
                      <DonutLabel cx="50%" cy="50%" total={sevTotal} />
                    </PieChart>
                  </ResponsiveContainer>
                  <div className="flex flex-wrap justify-center gap-x-4 gap-y-1.5">
                    {sev.map((s) => (
                      <div key={s.name} className="flex items-center gap-1.5 text-xs text-slate-400">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: SEVERITY_COLORS[s.name] }} />
                        {s.name} <span className="text-white font-semibold">({s.value})</span>
                      </div>
                    ))}
                  </div>
                </>
              )}
            </Card>

            <Card title="Incidents by Source" icon={Package} iconColor="text-accent" className="lg:col-span-3">
              {sources.length === 0 ? (
                <EmptyState title="No data yet" className="py-8" />
              ) : (
                <ResponsiveContainer width="100%" height={220}>
                  <BarChart data={sources} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                    <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                    <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                    <Tooltip content={<DarkTooltip />} cursor={{ fill: '#1e293b' }} />
                    <Bar dataKey="value" name="Incidents" radius={[6, 6, 0, 0]} maxBarSize={48}>
                      {sources.map((_, i) => (
                        <Cell key={i} fill={i === 0 ? '#6366f1' : i === 1 ? '#3b82f6' : '#a855f7'} fillOpacity={0.85} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </Card>
          </div>

          <Card title="Incidents — Last 7 Days" icon={Activity} iconColor="text-blue-400">
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={overtime} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<DarkTooltip />} cursor={{ stroke: '#334155' }} />
                <Line
                  type="monotone"
                  dataKey="count"
                  name="Incidents"
                  stroke="#6366f1"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: '#6366f1', strokeWidth: 0 }}
                  activeDot={{ r: 6, fill: '#818cf8' }}
                />
              </LineChart>
            </ResponsiveContainer>
          </Card>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <StatCard
              icon={Clock}
              iconClass="bg-blue-500/15 text-blue-400"
              label="Avg Gap (MTTR proxy)"
              value={data?.dora?.mttr_hours != null ? `${data.dora.mttr_hours}h` : d?.mttr}
              sub="Between incidents"
            />
            <StatCard
              icon={Wifi}
              iconClass="bg-cyan-500/15 text-cyan-400"
              label="Unread Notifications"
              value={d?.unread_notifications}
              sub="Pending review"
            />
            <div className="sm:col-span-1">
              <AwsCostCard />
            </div>
          </div>
        </div>

        <aside className="xl:col-span-4 flex flex-col gap-4">
          <AgentApprovalsWidget />
          <OncallWidget />
          <LogScannerCard onIncidentCreated={() => { void fetchAnalytics() }} />
        </aside>
      </div>
    </div>
  )
}
