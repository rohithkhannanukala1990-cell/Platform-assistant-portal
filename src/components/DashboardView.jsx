import { useEffect, useState } from 'react'
import {
  ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, Tooltip, Cell,
  PieChart, Pie,
  LineChart, Line, CartesianGrid,
  Legend,
} from 'recharts'
import {
  AlertTriangle, ShieldAlert, Activity, Layers,
  Construction, Rocket, RefreshCw, TrendingUp,
  Clock, Wifi,
} from 'lucide-react'

const API = 'http://127.0.0.1:8000/api/analytics'

const SEVERITY_COLORS = {
  Critical: '#ef4444',
  High:     '#f97316',
  Medium:   '#eab308',
  Low:      '#3b82f6',
  Unknown:  '#6b7280',
}

const MODULE_COLORS = ['#22c55e', '#3b82f6', '#a855f7']

// ── Custom tooltip ─────────────────────────────────────────────────────────────
function DarkTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-sidebar border border-border rounded-xl px-3 py-2.5 shadow-xl text-xs">
      {label && <p className="text-slate-400 mb-1 font-semibold">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color ?? p.fill ?? '#22c55e' }}>
          {p.name}: <span className="font-bold text-white">{p.value}</span>
        </p>
      ))}
    </div>
  )
}

// ── Donut label ────────────────────────────────────────────────────────────────
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

// ── Summary card ───────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, iconBg, label, value, sub, border }) {
  return (
    <div className={`flex items-center gap-4 px-5 py-4 rounded-2xl border ${border ?? 'border-border'} bg-card`}>
      <div className={`flex items-center justify-center w-11 h-11 rounded-xl ${iconBg} shrink-0`}>
        <Icon className="w-5 h-5" />
      </div>
      <div>
        <p className="text-2xl font-bold text-white leading-none">{value ?? '—'}</p>
        <p className="text-xs text-slate-400 mt-1">{label}</p>
        {sub && <p className="text-[10px] text-slate-600 mt-0.5">{sub}</p>}
      </div>
    </div>
  )
}

// ── Chart card wrapper ─────────────────────────────────────────────────────────
function ChartCard({ title, icon: Icon, iconColor, children, className = '' }) {
  return (
    <div className={`flex flex-col gap-4 p-5 rounded-2xl border border-border bg-card ${className}`}>
      <div className="flex items-center gap-2">
        <Icon className={`w-4 h-4 ${iconColor}`} />
        <h3 className="text-sm font-bold text-white">{title}</h3>
      </div>
      {children}
    </div>
  )
}

export default function DashboardView() {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError]   = useState(null)
  const [lastFetch, setLastFetch] = useState(null)

  async function fetchAnalytics() {
    setLoading(true)
    setError(null)
    try {
      const res  = await fetch(API)
      if (!res.ok) throw new Error(`Server error ${res.status}`)
      const json = await res.json()
      setData(json)
      setLastFetch(new Date())
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchAnalytics() }, [])

  if (loading && !data) {
    return (
      <div className="flex items-center justify-center h-64 gap-3 text-slate-500">
        <RefreshCw className="w-5 h-5 animate-spin text-accent" />
        <span className="text-sm">Loading analytics…</span>
      </div>
    )
  }

  if (error && !data) {
    return (
      <div className="flex flex-col items-center justify-center h-64 gap-2 text-red-400 text-sm">
        <AlertTriangle className="w-6 h-6" />
        <p>Could not load analytics: {error}</p>
        <button onClick={fetchAnalytics} className="mt-2 px-4 py-2 rounded-lg border border-red-500/30 hover:bg-red-500/10 text-xs transition-colors">
          Retry
        </button>
      </div>
    )
  }

  const d        = data
  const sev      = d.incidents_by_severity ?? []
  const sources  = d.top_sources ?? []
  const overtime = d.incidents_over_time ?? []
  const modules  = d.module_activity ?? []
  const sevTotal = sev.reduce((s, i) => s + i.value, 0)

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* ── Page header ───────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight">Analytics Dashboard</h1>
          <p className="text-sm text-slate-500 mt-0.5">Platform-wide health and activity metrics</p>
        </div>
        <div className="flex items-center gap-3">
          {lastFetch && (
            <span className="text-[10px] text-slate-600">
              Updated {lastFetch.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchAnalytics}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* ── Summary cards ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={Layers}
          iconBg="bg-accent/15 text-accent"
          label="Total Incidents"
          value={d.total_incidents}
          sub="All time"
          border="border-accent/20"
        />
        <StatCard
          icon={AlertTriangle}
          iconBg="bg-red-500/15 text-red-400"
          label="Critical Alerts"
          value={d.critical_alerts}
          sub={`${d.total_incidents ? Math.round((d.critical_alerts / d.total_incidents) * 100) : 0}% of total`}
          border="border-red-500/20"
        />
        <StatCard
          icon={Clock}
          iconBg="bg-blue-500/15 text-blue-400"
          label="Avg Gap (MTTR proxy)"
          value={d.mttr}
          sub="Between incidents"
          border="border-blue-500/20"
        />
        <StatCard
          icon={Wifi}
          iconBg="bg-cyan-500/15 text-cyan-400"
          label="Unread Notifications"
          value={d.unread_notifications}
          sub="Pending review"
          border="border-cyan-500/20"
        />
      </div>

      {/* ── Module totals ──────────────────────────────────────────────────── */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Infra Generations', value: d.total_infra, icon: Construction, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/20' },
          { label: 'CI/CD Pipelines',   value: d.total_cicd,  icon: Rocket,       color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/20' },
          { label: 'AI Alerts Triaged', value: d.total_incidents, icon: ShieldAlert, color: 'text-accent', bg: 'bg-accent/10 border-accent/20' },
        ].map(({ label, value, icon: Icon, color, bg }) => (
          <div key={label} className={`flex items-center gap-3 px-4 py-3.5 rounded-xl border ${bg}`}>
            <Icon className={`w-5 h-5 ${color} shrink-0`} />
            <div>
              <p className="text-xl font-bold text-white">{value}</p>
              <p className="text-[11px] text-slate-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* ── Charts row 1 ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">

        {/* Donut — severity */}
        <ChartCard title="Incidents by Severity" icon={Activity} iconColor="text-red-400" className="lg:col-span-2">
          {sev.length === 0 ? (
            <p className="text-xs text-slate-600 py-8 text-center">No incidents yet</p>
          ) : (
            <>
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie
                    data={sev}
                    cx="50%"
                    cy="50%"
                    innerRadius={65}
                    outerRadius={95}
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
              {/* Legend */}
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
        </ChartCard>

        {/* Bar — incidents by source */}
        <ChartCard title="Incidents by Source" icon={TrendingUp} iconColor="text-accent" className="lg:col-span-3">
          {sources.length === 0 ? (
            <p className="text-xs text-slate-600 py-8 text-center">No data yet</p>
          ) : (
            <ResponsiveContainer width="100%" height={250}>
              <BarChart data={sources} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" vertical={false} />
                <XAxis dataKey="name" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<DarkTooltip />} cursor={{ fill: '#1e293b' }} />
                <Bar dataKey="value" name="Incidents" radius={[6, 6, 0, 0]} maxBarSize={48}>
                  {sources.map((_, i) => (
                    <Cell key={i} fill={i === 0 ? '#22c55e' : i === 1 ? '#3b82f6' : '#a855f7'} fillOpacity={0.85} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>
      </div>

      {/* ── Charts row 2 ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">

        {/* Line — incidents over time */}
        <ChartCard title="Incidents — Last 7 Days" icon={Activity} iconColor="text-blue-400" className="lg:col-span-3">
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={overtime} margin={{ top: 4, right: 8, left: -20, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
              <XAxis dataKey="date" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <Tooltip content={<DarkTooltip />} cursor={{ stroke: '#334155' }} />
              <Line
                type="monotone"
                dataKey="count"
                name="Incidents"
                stroke="#22c55e"
                strokeWidth={2.5}
                dot={{ r: 4, fill: '#22c55e', strokeWidth: 0 }}
                activeDot={{ r: 6, fill: '#4ade80' }}
              />
            </LineChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Bar — module activity */}
        <ChartCard title="Module Activity" icon={Layers} iconColor="text-purple-400" className="lg:col-span-2">
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={modules} layout="vertical" margin={{ top: 4, right: 16, left: 8, bottom: 4 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" horizontal={false} />
              <XAxis type="number" tick={{ fill: '#64748b', fontSize: 11 }} axisLine={false} tickLine={false} allowDecimals={false} />
              <YAxis type="category" dataKey="name" tick={{ fill: '#94a3b8', fontSize: 12 }} axisLine={false} tickLine={false} width={52} />
              <Tooltip content={<DarkTooltip />} cursor={{ fill: '#1e293b' }} />
              <Bar dataKey="value" name="Count" radius={[0, 6, 6, 0]} maxBarSize={28}>
                {modules.map((_, i) => (
                  <Cell key={i} fill={MODULE_COLORS[i] ?? '#22c55e'} fillOpacity={0.85} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

      </div>
    </div>
  )
}
