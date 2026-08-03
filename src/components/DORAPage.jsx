import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
} from 'recharts'
import {
  AlertTriangle,
  Rocket,
  RefreshCw,
  Clock,
  Gauge,
  Loader2,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
  TrendingUp,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'
import { PageHeader, EmptyState, SectionHeader } from './ui'

const DORA_API = `${API_BASE}/api/cicd/dora-metrics`
const REPORTS_API = `${API_BASE}/api/reports`

const DORA_LEVEL_COLORS = {
  Elite:  { text: 'text-emerald-400', bg: 'bg-emerald-500/15', border: 'border-emerald-500/30' },
  High:   { text: 'text-blue-400',    bg: 'bg-blue-500/15',    border: 'border-blue-500/30'    },
  Medium: { text: 'text-amber-400',   bg: 'bg-amber-500/15',   border: 'border-amber-500/30'   },
  Low:    { text: 'text-red-400',     bg: 'bg-red-500/15',     border: 'border-red-500/30'     },
}

const LEGEND_ITEMS = [
  { level: 'Elite',  hint: 'weekly+' },
  { level: 'High',   hint: 'monthly' },
  { level: 'Medium', hint: '6-monthly' },
  { level: 'Low',    hint: 'on-demand' },
]

const HISTORY_LINES = [
  { key: 'deployment_frequency', name: 'Deploy frequency', color: '#22c55e' },
  { key: 'lead_time', name: 'Lead time', color: '#3b82f6' },
  { key: 'change_failure_rate', name: 'Change failure rate', color: '#ef4444' },
  { key: 'mttr', name: 'MTTR', color: '#a855f7' },
]

const TEAM_COLUMNS = [
  { key: 'name', label: 'Team', sortable: true },
  { key: 'avg_score', label: 'Avg Score', sortable: true },
  { key: 'readiness_pct', label: 'Readiness %', sortable: true },
  { key: 'deploy_freq', label: 'Deploy Freq', sortable: false },
  { key: 'open_actions', label: 'Open Actions', sortable: true },
]

function DarkTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null
  return (
    <div className="bg-sidebar border border-border rounded-xl px-3 py-2.5 shadow-xl text-xs">
      {label && <p className="text-slate-400 mb-1 font-semibold">{label}</p>}
      {payload.map((p, i) => (
        <p key={i} style={{ color: p.color ?? p.stroke ?? '#22c55e' }}>
          {p.name}: <span className="font-bold text-white">{p.value}</span>
        </p>
      ))}
    </div>
  )
}

function DoraCard({ label, icon: Icon, iconColor, metric }) {
  if (!metric) return null
  const lvl = DORA_LEVEL_COLORS[metric.level] ?? DORA_LEVEL_COLORS.High
  const TrendIcon =
    metric.trend_dir === 'up'        ? ArrowUpRight :
    metric.trend_dir === 'down_good' ? ArrowDownRight : Minus

  return (
    <div className={`flex flex-col gap-2 p-4 rounded-2xl border ${lvl.border} ${lvl.bg}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-1.5">
          <Icon size={14} className={iconColor} />
          <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{label}</span>
        </div>
        <span className={`text-[9px] font-bold uppercase tracking-widest px-1.5 py-0.5 rounded ${lvl.bg} ${lvl.text} border ${lvl.border}`}>
          {metric.level}
        </span>
      </div>
      <p className={`text-2xl font-extrabold ${lvl.text} leading-none`}>{metric.value}</p>
      <div className="flex items-center gap-1 text-[10px] text-slate-500">
        <TrendIcon
          size={11}
          className={
            metric.trend_dir === 'down_good' ? 'text-emerald-400' :
            metric.trend_dir === 'up'        ? 'text-emerald-400' : 'text-slate-500'
          }
        />
        {metric.trend}
      </div>
    </div>
  )
}

function hasDoraMetrics(d) {
  if (!d || typeof d !== 'object') return false
  if (d.status === 'no_data') return false
  return Boolean(
    d.deployment_frequency?.value ||
    d.lead_time?.value ||
    d.change_failure_rate?.value ||
    d.mttr?.value
  )
}

function normalizeDoraMetrics(data) {
  if (!data || typeof data !== 'object') return null
  if (data.status === 'no_data') {
    return { status: 'no_data', message: data.message || 'Connect CI/CD tools to compute real DORA metrics.' }
  }
  if (hasDoraMetrics(data)) return data
  const freq = data.deploy_frequency ?? data.deployment_frequency
  const lead = data.lead_time_hours ?? data.lead_time
  const cfr = data.change_failure_rate_pct ?? data.change_failure_rate
  const mttr = data.mttr_hours ?? data.mttr
  if (freq == null && lead == null && cfr == null && mttr == null) return data
  return {
    deployment_frequency: {
      value: freq != null ? String(freq) : '—',
      level: 'High',
      trend: '',
      trend_dir: 'up',
    },
    lead_time: {
      value: lead != null ? `${lead}h` : '—',
      level: 'High',
      trend: '',
      trend_dir: 'up',
    },
    change_failure_rate: {
      value: cfr != null ? `${cfr}%` : '—',
      level: 'High',
      trend: '',
      trend_dir: 'up',
    },
    mttr: {
      value: mttr != null ? `${mttr}h` : '—',
      level: 'High',
      trend: '',
      trend_dir: 'up',
    },
  }
}

function MetricSkeleton() {
  return (
    <div className="bg-gray-800 rounded-xl p-5 animate-pulse">
      <div className="h-4 bg-gray-700 rounded w-1/2 mb-3" />
      <div className="h-8 bg-gray-700 rounded w-1/3" />
    </div>
  )
}

function normalizeHistory(data) {
  if (!data) return null
  if (Array.isArray(data.history) && data.history.length) return data.history
  if (Array.isArray(data) && data.length && (data[0].date || data[0].period)) return data
  return null
}

export default function DORAPage() {
  const { authFetch } = useAuth()
  const [dora, setDora] = useState(null)
  const [teams, setTeams] = useState([])
  const [history, setHistory] = useState(null)
  const [historyNote, setHistoryNote] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [sortKey, setSortKey] = useState('avg_score')
  const [sortDir, setSortDir] = useState('desc')

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setHistoryNote(false)
    setHistory(null)
    try {
      const [doraRes, teamsRes, histRes] = await Promise.all([
        authFetch(DORA_API),
        authFetch(`${REPORTS_API}/dora/teams`),
        authFetch(`${DORA_API}?history=true`),
      ])

      if (!doraRes.ok) {
        throw new Error(`Failed to load DORA metrics (${doraRes.status})`)
      }
      const doraData = await doraRes.json()
      setDora(normalizeDoraMetrics(doraData))

      let teamsData = []
      if (teamsRes.ok) {
        const d = await teamsRes.json()
        teamsData = d.teams || d || []
      } else {
        const fallback = await authFetch(`${REPORTS_API}/dora?range=30d`)
        if (fallback.ok) {
          const d = await fallback.json()
          teamsData = d.teams || d || []
        } else {
          const overview = await authFetch(`${REPORTS_API}/team-overview`)
          if (overview.ok) {
            const d = await overview.json()
            teamsData = d.teams || d || []
          }
        }
      }
      setTeams(Array.isArray(teamsData) ? teamsData : [])

      if (histRes.ok) {
        const histData = await histRes.json()
        const rows = normalizeHistory(histData)
        if (rows?.length) setHistory(rows)
        else setHistoryNote(true)
      } else {
        setHistoryNote(true)
      }
    } catch (e) {
      setError(e.message || 'Failed to load DORA page')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    load()
  }, [load])

  const sortedTeams = useMemo(() => {
    const rows = [...teams]
    rows.sort((a, b) => {
      if (sortKey === 'name') {
        const av = (a.name || '').toLowerCase()
        const bv = (b.name || '').toLowerCase()
        const cmp = av.localeCompare(bv)
        return sortDir === 'asc' ? cmp : -cmp
      }
      const av = Number(a[sortKey]) || 0
      const bv = Number(b[sortKey]) || 0
      if (av < bv) return sortDir === 'asc' ? -1 : 1
      if (av > bv) return sortDir === 'asc' ? 1 : -1
      return 0
    })
    return rows
  }, [teams, sortKey, sortDir])

  function toggleSort(key) {
    if (sortKey === key) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else {
      setSortKey(key)
      setSortDir('desc')
    }
  }

  if (error) {
    return (
      <div className="flex flex-col gap-6">
        <PageHeader
          title="DORA Metrics"
          subtitle="Engineering delivery performance — deployment velocity, stability, and recovery"
        />
        <div className="rounded-xl border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-300 flex flex-wrap items-center justify-between gap-3">
          <span>{error}</span>
          <button
            type="button"
            onClick={load}
            className="px-3 py-1.5 rounded-lg border border-red-500/30 hover:bg-red-500/10 text-xs font-medium"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  const showEmptyMetrics = !loading && !hasDoraMetrics(dora)

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="DORA Metrics"
        subtitle="Engineering delivery performance — deployment velocity, stability, and recovery"
      />

      {/* Section A — KPI cards */}
      <section className="flex flex-col gap-3">
        <SectionHeader title="Current performance" />
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {loading ? (
            <>
              <MetricSkeleton />
              <MetricSkeleton />
              <MetricSkeleton />
              <MetricSkeleton />
            </>
          ) : showEmptyMetrics ? (
            <div className="col-span-full">
              <EmptyState
                icon={Gauge}
                title={
                  dora?.status === 'no_data' && dora?.message
                    ? dora.message
                    : 'DORA metrics not yet available — connect your CI/CD pipeline'
                }
                action={(
                  <a
                    href="/tool-registry"
                    className="mt-2 inline-flex text-sm font-medium text-accent hover:text-accent/80"
                  >
                    Connect GitHub in Tool Registry
                  </a>
                )}
              />
            </div>
          ) : (
            <>
              <DoraCard
                label="Deployment Frequency"
                icon={Rocket}
                iconColor="text-emerald-400"
                metric={dora?.deployment_frequency}
              />
              <DoraCard
                label="Lead Time for Changes"
                icon={Clock}
                iconColor="text-blue-400"
                metric={dora?.lead_time}
              />
              <DoraCard
                label="Change Failure Rate"
                icon={AlertTriangle}
                iconColor="text-amber-400"
                metric={dora?.change_failure_rate}
              />
              <DoraCard
                label="MTTR (Mean Time to Restore)"
                icon={RefreshCw}
                iconColor="text-violet-400"
                metric={dora?.mttr}
              />
            </>
          )}
        </div>
      </section>

      {/* Section D — Legend */}
      <section className="flex flex-wrap items-center gap-2">
        {LEGEND_ITEMS.map(({ level, hint }) => {
          const lvl = DORA_LEVEL_COLORS[level]
          return (
            <span
              key={level}
              className={`inline-flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg border ${lvl.border} ${lvl.bg} ${lvl.text}`}
            >
              <span className="font-semibold">{level}:</span>
              <span className="opacity-80">{hint}</span>
            </span>
          )
        })}
      </section>

      {/* Section B — Historical trend */}
      <section className="flex flex-col gap-3 p-5 rounded-2xl border border-border bg-card">
        <div className="flex items-center gap-2">
          <TrendingUp className="w-4 h-4 text-indigo-400" />
          <h2 className="text-sm font-bold text-white">Historical trend</h2>
        </div>
        {history?.length ? (
          <ResponsiveContainer width="100%" height={280}>
            <LineChart data={history} margin={{ top: 8, right: 16, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
              <XAxis dataKey="date" tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <YAxis tick={{ fill: '#94a3b8', fontSize: 11 }} />
              <Tooltip content={<DarkTooltip />} />
              {HISTORY_LINES.map((line) => (
                <Line
                  key={line.key}
                  type="monotone"
                  dataKey={line.key}
                  name={line.name}
                  stroke={line.color}
                  strokeWidth={2}
                  dot={false}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        ) : (
          <p className="text-sm text-slate-500 py-8 text-center">
            {historyNote
              ? 'Historical trend requires extended data collection'
              : 'No historical data available yet'}
          </p>
        )}
      </section>

      {/* Section C — Team table */}
      <section className="flex flex-col gap-3">
        <h2 className="text-sm font-semibold text-slate-300">Team performance</h2>
        <div className="rounded-2xl border border-border bg-card overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-slate-400 text-xs uppercase tracking-wide">
                  {TEAM_COLUMNS.map((col) => (
                    <th key={col.key} className="px-4 py-3 font-semibold">
                      {col.sortable ? (
                        <button
                          type="button"
                          onClick={() => toggleSort(col.key)}
                          className="hover:text-white transition-colors"
                        >
                          {col.label}
                          {sortKey === col.key ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
                        </button>
                      ) : (
                        col.label
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {teams.length === 0 && !loading ? (
                  <tr>
                    <td colSpan={5} className="text-center py-8 text-gray-500 text-sm">
                      No team data available
                    </td>
                  </tr>
                ) : (
                  sortedTeams.map((team) => (
                    <tr key={team.name} className="border-b border-border/60 hover:bg-white/[0.02]">
                      <td className="px-4 py-3 text-white font-medium">{team.name}</td>
                      <td className="px-4 py-3 text-slate-300">{team.avg_score ?? '—'}</td>
                      <td className="px-4 py-3 text-slate-300">
                        {team.readiness_pct != null ? `${team.readiness_pct}%` : '—'}
                      </td>
                      <td className="px-4 py-3 text-slate-500">—</td>
                      <td className="px-4 py-3 text-slate-300">{team.open_actions ?? 0}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  )
}
