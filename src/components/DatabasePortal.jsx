import { useState } from 'react'
import {
  Database, Activity, AlertTriangle, CheckCircle2,
  HardDrive, Zap, Clock, RefreshCw, TrendingDown,
  BarChart3, ShieldCheck, Loader2, Table2,
} from 'lucide-react'
import AgentApprovalsWidget  from './AgentApprovalsWidget'
import QueryAnalyzerView from './QueryAnalyzerView'
import SchemaBrowserView from './SchemaBrowserView'

// ── Mock data ──────────────────────────────────────────────────────────────────

const DB_INSTANCES = [
  { name: 'prod-postgres-primary',  engine: 'PostgreSQL 16', role: 'Primary', connections: 142, maxConn: 200, slowQueries: 3,  status: 'healthy',  storage: 68, storageMax: '500 GB', uptime: '99.97%' },
  { name: 'prod-postgres-replica',  engine: 'PostgreSQL 16', role: 'Replica', connections: 84,  maxConn: 200, slowQueries: 1,  status: 'healthy',  storage: 67, storageMax: '500 GB', uptime: '99.95%' },
  { name: 'analytics-mysql',        engine: 'MySQL 8.0',     role: 'Primary', connections: 31,  maxConn: 100, slowQueries: 9,  status: 'warning',  storage: 89, storageMax: '1 TB',   uptime: '99.81%' },
  { name: 'cache-redis-cluster',    engine: 'Redis 7.2',     role: 'Cluster', connections: 512, maxConn: 1000, slowQueries: 0, status: 'healthy',  storage: 44, storageMax: '32 GB',  uptime: '100%'   },
  { name: 'reporting-clickhouse',   engine: 'ClickHouse 24', role: 'Primary', connections: 18,  maxConn: 50,  slowQueries: 21, status: 'critical', storage: 93, storageMax: '2 TB',   uptime: '98.40%' },
  { name: 'dev-postgres',           engine: 'PostgreSQL 15', role: 'Primary', connections: 5,   maxConn: 50,  slowQueries: 0,  status: 'healthy',  storage: 12, storageMax: '50 GB',  uptime: '99.50%' },
]

const SLOW_QUERIES = [
  { db: 'analytics-mysql',      query: 'SELECT * FROM events JOIN users ON … WHERE date > …', duration: '12.4s', count: 4,  table: 'events'    },
  { db: 'reporting-clickhouse', query: 'SELECT toDate(timestamp), count(*) FROM logs …',      duration: '8.1s',  count: 11, table: 'logs'      },
  { db: 'reporting-clickhouse', query: 'SELECT user_id, sum(revenue) FROM sales GROUP BY …',  duration: '6.7s',  count: 6,  table: 'sales'     },
  { db: 'prod-postgres-primary',query: 'UPDATE sessions SET last_seen = NOW() WHERE …',       duration: '3.2s',  count: 3,  table: 'sessions'  },
  { db: 'analytics-mysql',      query: 'INSERT INTO audit_log SELECT … FROM …',               duration: '2.8s',  count: 2,  table: 'audit_log' },
]

const STATUS_CFG = {
  healthy:  { cls: 'text-green-400 bg-green-500/10 border-green-500/25',   label: 'Healthy',  dot: 'bg-green-400'  },
  warning:  { cls: 'text-amber-400 bg-amber-500/10 border-amber-500/25',   label: 'Warning',  dot: 'bg-amber-400'  },
  critical: { cls: 'text-red-400   bg-red-500/10   border-red-500/25',     label: 'Critical', dot: 'bg-red-400 animate-pulse' },
}

// ── Sub-components ─────────────────────────────────────────────────────────────

function MiniBar({ value, max, color }) {
  const pct = Math.min(Math.round((value / max) * 100), 100)
  const barColor = pct > 85 ? 'bg-red-500' : pct > 60 ? 'bg-amber-500' : color
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-500 w-8 text-right">{pct}%</span>
    </div>
  )
}

function InstanceCard({ db, onKillSlowQueries }) {
  const cfg  = STATUS_CFG[db.status]
  const [killing, setKilling] = useState(false)
  const [killed,  setKilled]  = useState(false)

  function killQueries() {
    setKilling(true)
    setTimeout(() => { setKilling(false); setKilled(true) }, 1800)
  }

  return (
    <div className={`flex flex-col gap-3 p-4 rounded-2xl border bg-card transition-all
      ${db.status === 'critical' ? 'border-red-500/30' : db.status === 'warning' ? 'border-amber-500/25' : 'border-border'}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-xs font-bold text-white font-mono truncate">{db.name}</p>
          <p className="text-[10px] text-slate-500 mt-0.5">{db.engine} · {db.role}</p>
        </div>
        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[10px] font-bold shrink-0 ${cfg.cls}`}>
          <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} />
          {cfg.label}
        </span>
      </div>

      {/* Metrics */}
      <div className="flex flex-col gap-2.5">
        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-500 flex items-center gap-1"><Activity className="w-3 h-3" /> Connections</span>
            <span className="text-slate-300 font-semibold">{db.connections} / {db.maxConn}</span>
          </div>
          <MiniBar value={db.connections} max={db.maxConn} color="bg-blue-500" />
        </div>

        <div className="flex flex-col gap-1">
          <div className="flex items-center justify-between text-[10px]">
            <span className="text-slate-500 flex items-center gap-1"><HardDrive className="w-3 h-3" /> Storage</span>
            <span className={`font-semibold ${db.storage > 85 ? 'text-red-400' : 'text-slate-300'}`}>{db.storage}% of {db.storageMax}</span>
          </div>
          <MiniBar value={db.storage} max={100} color="bg-cyan-500" />
        </div>

        <div className="flex items-center justify-between text-[10px]">
          <span className="text-slate-500 flex items-center gap-1"><Clock className="w-3 h-3" /> Uptime</span>
          <span className="text-green-400 font-semibold">{db.uptime}</span>
        </div>
      </div>

      {/* Slow queries */}
      <div className="flex items-center justify-between pt-2 border-t border-border">
        <span className={`text-[11px] font-semibold flex items-center gap-1
          ${db.slowQueries > 5 ? 'text-red-400' : db.slowQueries > 0 ? 'text-amber-400' : 'text-green-400'}`}>
          <Zap className="w-3 h-3" />
          {db.slowQueries} slow {db.slowQueries === 1 ? 'query' : 'queries'}
        </span>

        {db.slowQueries > 0 && (
          killed ? (
            <span className="text-[11px] text-green-400 font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" /> Killed
            </span>
          ) : (
            <button
              onClick={killQueries}
              disabled={killing}
              className="flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-semibold
                bg-red-500/10 border border-red-500/25 text-red-400
                hover:bg-red-500/20 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {killing ? <><Loader2 className="w-3 h-3 animate-spin" /> Killing…</> : 'Kill Queries'}
            </button>
          )
        )}
      </div>
    </div>
  )
}

// ── Main portal ────────────────────────────────────────────────────────────────

export default function DatabasePortal({ currentView = 'dbhealth' }) {
  if (currentView === 'queries') return <QueryAnalyzerView />
  if (currentView === 'schemas') return <SchemaBrowserView />
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState(new Date())

  function handleRefresh() {
    setRefreshing(true)
    setTimeout(() => { setRefreshing(false); setLastRefresh(new Date()) }, 1200)
  }

  const totalConns   = DB_INSTANCES.reduce((s, d) => s + d.connections, 0)
  const totalSlow    = DB_INSTANCES.reduce((s, d) => s + d.slowQueries, 0)
  const criticalDBs  = DB_INSTANCES.filter(d => d.status === 'critical').length
  const healthyDBs   = DB_INSTANCES.filter(d => d.status === 'healthy').length

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Database className="w-5 h-5 text-rose-400" />
            Database Health
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Active connections, slow queries, and storage across all instances
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600">
            Refreshed {lastRefresh.toLocaleTimeString()}
          </span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border
              text-xs text-slate-400 hover:text-white hover:bg-card transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin text-accent' : ''}`} />
            Refresh
          </button>
          <span className="px-3 py-1.5 rounded-lg border border-rose-500/25 bg-rose-500/10 text-rose-400 text-xs font-semibold">
            🗄️ Database Developer View
          </span>
        </div>
      </div>

      {/* HITL widget — pinned to DatabaseDeveloper queue */}
      <AgentApprovalsWidget roleFilter="DatabaseDeveloper" />

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Connections', value: totalConns,  icon: Activity,      cls: 'border-blue-500/20  bg-blue-500/5  text-blue-400'  },
          { label: 'Slow Queries',      value: totalSlow,   icon: TrendingDown,  cls: 'border-amber-500/20 bg-amber-500/5 text-amber-400' },
          { label: 'Critical DBs',      value: criticalDBs, icon: AlertTriangle, cls: 'border-red-500/20   bg-red-500/5   text-red-400'   },
          { label: 'Healthy DBs',       value: healthyDBs,  icon: ShieldCheck,   cls: 'border-green-500/20 bg-green-500/5 text-green-400' },
        ].map(({ label, value, icon: Icon, cls }) => (
          <div key={label} className={`flex items-center gap-4 px-5 py-4 rounded-2xl border ${cls}`}>
            <Icon className="w-5 h-5 shrink-0" />
            <div>
              <p className="text-2xl font-bold text-white leading-none">{value}</p>
              <p className="text-xs text-slate-400 mt-1">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Instance grid */}
      <div>
        <h2 className="text-sm font-bold text-white mb-3 flex items-center gap-2">
          <Table2 className="w-4 h-4 text-slate-400" />
          Database Instances
        </h2>
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
          {DB_INSTANCES.map(db => <InstanceCard key={db.name} db={db} />)}
        </div>
      </div>

      {/* Slow query log */}
      <div className="flex flex-col rounded-2xl border border-border bg-card overflow-hidden">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-border">
          <BarChart3 className="w-4 h-4 text-amber-400" />
          <h3 className="text-sm font-bold text-white">Slow Query Log</h3>
          <span className="ml-auto text-[10px] text-slate-600">Threshold: &gt; 2s</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="border-b border-border text-[10px] text-slate-600 font-semibold uppercase tracking-widest">
                <th className="text-left px-4 py-2.5">Database</th>
                <th className="text-left px-4 py-2.5">Query</th>
                <th className="text-left px-4 py-2.5">Table</th>
                <th className="text-right px-4 py-2.5">Duration</th>
                <th className="text-right px-4 py-2.5">Count</th>
              </tr>
            </thead>
            <tbody>
              {SLOW_QUERIES.map((q, i) => (
                <tr key={i} className="border-b border-border/50 hover:bg-slate-800/30 transition-colors">
                  <td className="px-4 py-2.5 font-mono text-rose-400 whitespace-nowrap">{q.db}</td>
                  <td className="px-4 py-2.5 text-slate-400 max-w-xs truncate font-mono text-[10px]" title={q.query}>{q.query}</td>
                  <td className="px-4 py-2.5 text-slate-500 font-mono whitespace-nowrap">{q.table}</td>
                  <td className="px-4 py-2.5 text-right">
                    <span className={`font-bold ${parseFloat(q.duration) > 8 ? 'text-red-400' : parseFloat(q.duration) > 4 ? 'text-amber-400' : 'text-yellow-400'}`}>
                      {q.duration}
                    </span>
                  </td>
                  <td className="px-4 py-2.5 text-right text-slate-400">{q.count}×</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

    </div>
  )
}
