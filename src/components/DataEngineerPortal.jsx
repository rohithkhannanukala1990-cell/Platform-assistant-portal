import { useState, useEffect } from 'react'
import {
  Database, CheckCircle2, XCircle, Clock, PlayCircle,
  AlertTriangle, TrendingUp, HardDrive, RefreshCw,
  BarChart3, Loader2, Pause, GitBranch, Zap,
} from 'lucide-react'
import AgentApprovalsWidget from './AgentApprovalsWidget'
import StorageView     from './StorageView'
import DataLineageView from './DataLineageView'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const CICD_API = `${API_BASE}/api/cicd/active-runs`

const DBT_RUNS = [
  { id: 'dbt-001', model: 'marts.fct_orders',          status: 'success', duration: '1m 22s', tests: 14,  testsPassed: 14, trigger: 'schedule', time: '5 min ago' },
  { id: 'dbt-002', model: 'marts.dim_customers',       status: 'success', duration: '0m 48s', tests: 8,   testsPassed: 8,  trigger: 'ci-push',  time: '12 min ago' },
  { id: 'dbt-003', model: 'staging.stg_clickstream',   status: 'failed',  duration: '—',      tests: 5,   testsPassed: 2,  trigger: 'ci-push',  time: '31 min ago' },
  { id: 'dbt-004', model: 'marts.fct_revenue_daily',   status: 'running', duration: '0m 37s', tests: 12,  testsPassed: 0,  trigger: 'schedule', time: '1 min ago' },
  { id: 'dbt-005', model: 'intermediate.int_sessions', status: 'success', duration: '2m 01s', tests: 6,   testsPassed: 6,  trigger: 'manual',   time: '1 h ago' },
]

const AIRFLOW_DAGS = [
  { id: 'af-001', dag: 'data_quality_check_ci',       status: 'success', runs: 48,  successRate: 97, lastRun: '10 min ago', env: 'prod' },
  { id: 'af-002', dag: 'schema_migration_validation', status: 'running', runs: 12,  successRate: 100, lastRun: '2 min ago',  env: 'staging' },
  { id: 'af-003', dag: 'dbt_ci_smoke_tests',          status: 'failed',  runs: 120, successRate: 84,  lastRun: '1 h ago',    env: 'prod' },
  { id: 'af-004', dag: 'pipeline_regression_suite',   status: 'success', runs: 23,  successRate: 96,  lastRun: '45 min ago', env: 'staging' },
]

const CI_STATUS_CFG = {
  success: { label: 'Passed',  cls: 'text-emerald-400 bg-emerald-500/10 border-emerald-500/25', icon: CheckCircle2, spin: false },
  running: { label: 'Running', cls: 'text-blue-400    bg-blue-500/10    border-blue-500/25',    icon: RefreshCw,    spin: true  },
  failed:  { label: 'Failed',  cls: 'text-red-400     bg-red-500/10     border-red-500/25',     icon: XCircle,      spin: false },
}

function CIPipelineWidget() {
  const [tab, setTab] = useState('dbt')
  const [activePipes, setActivePipes] = useState([])

  useEffect(() => {
    fetch(CICD_API)
      .then(r => r.json())
      .then(data => setActivePipes(data.filter(r => r.status === 'running')))
      .catch(() => {})
  }, [])

  return (
    <div className="flex flex-col gap-4 p-5 rounded-2xl border border-border bg-card">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-2">
        <div className="flex items-center gap-2">
          <Zap size={15} className="text-violet-400" />
          <h3 className="text-sm font-bold text-white">dbt / Airflow CI Pipeline Runs</h3>
        </div>
        <div className="flex items-center gap-1 p-0.5 rounded-lg bg-slate-800/60 border border-slate-700/40">
          {['dbt', 'airflow', 'active'].map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`px-3 py-1 rounded-md text-xs font-semibold transition-all capitalize
                ${tab === t ? 'bg-violet-600 text-white shadow' : 'text-slate-400 hover:text-slate-200'}`}
            >
              {t === 'active' ? `Live (${activePipes.length})` : t}
            </button>
          ))}
        </div>
      </div>

      {/* dbt tab */}
      {tab === 'dbt' && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">dbt Model Runs</p>
          {DBT_RUNS.map(run => {
            const cfg  = CI_STATUS_CFG[run.status] ?? CI_STATUS_CFG.success
            const Icon = cfg.icon
            const pct  = run.tests > 0 ? Math.round((run.testsPassed / run.tests) * 100) : 100
            return (
              <div key={run.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-slate-700/40 bg-slate-800/40 hover:bg-slate-800/60 transition-colors">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-semibold shrink-0 ${cfg.cls}`}>
                  <Icon size={10} className={cfg.spin ? 'animate-spin' : ''} />
                  {cfg.label}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-slate-200 truncate">{run.model}</p>
                  <p className="text-[10px] text-slate-500">
                    {run.trigger} · {run.time}
                    {run.duration !== '—' && ` · ${run.duration}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className={`text-xs font-bold ${pct === 100 ? 'text-emerald-400' : pct > 50 ? 'text-amber-400' : 'text-red-400'}`}>
                    {run.testsPassed}/{run.tests} tests
                  </p>
                  <div className="mt-1 h-1 w-16 bg-slate-700 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full ${pct === 100 ? 'bg-emerald-500' : pct > 50 ? 'bg-amber-500' : 'bg-red-500'}`}
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Airflow tab */}
      {tab === 'airflow' && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Airflow CI DAGs</p>
          {AIRFLOW_DAGS.map(dag => {
            const cfg  = CI_STATUS_CFG[dag.status] ?? CI_STATUS_CFG.success
            const Icon = cfg.icon
            const good = dag.successRate >= 95
            return (
              <div key={dag.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-slate-700/40 bg-slate-800/40 hover:bg-slate-800/60 transition-colors">
                <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-lg border text-[10px] font-semibold shrink-0 ${cfg.cls}`}>
                  <Icon size={10} className={cfg.spin ? 'animate-spin' : ''} />
                  {cfg.label}
                </span>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-mono text-slate-200 truncate">{dag.dag}</p>
                  <p className="text-[10px] text-slate-500">{dag.env} · {dag.runs} total runs · {dag.lastRun}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className={`text-xs font-bold ${good ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {dag.successRate}%
                  </p>
                  <p className="text-[10px] text-slate-500">success rate</p>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Live active pipelines from backend */}
      {tab === 'active' && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Currently Running Pipelines</p>
          {activePipes.length === 0 ? (
            <p className="text-center text-sm text-slate-600 py-6">No active pipeline runs</p>
          ) : activePipes.map(run => (
            <div key={run.id} className="flex items-center gap-3 px-3 py-2.5 rounded-xl border border-blue-500/25 bg-blue-500/10">
              <RefreshCw size={13} className="animate-spin text-blue-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold text-slate-200 truncate">{run.repository}</p>
                <p className="text-[10px] text-slate-500">
                  {run.branch} · Stage: <span className="text-blue-300 font-semibold">{run.current_stage}</span>
                </p>
              </div>
              <div className="shrink-0 text-right">
                <p className="text-xs text-blue-300 font-semibold">{run.elapsed_time}</p>
                <p className="text-[10px] text-slate-500">by {run.trigger_user}</p>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const ETL_JOBS = [
  { id: 'etl-001', name: 'Customer Events → Warehouse',  schedule: '*/15 * * * *', status: 'running',  lastRun: '2 min ago', duration: '1m 12s', records: '1.2M', owner: 'DataEngineer' },
  { id: 'etl-002', name: 'Clickstream Aggregation',      schedule: '0 * * * *',    status: 'succeeded', lastRun: '48 min ago', duration: '3m 44s', records: '8.7M', owner: 'DataEngineer' },
  { id: 'etl-003', name: 'Sales Reconciliation ETL',     schedule: '0 6 * * *',    status: 'failed',    lastRun: '6 h ago',   duration: '—',       records: '—',    owner: 'DataEngineer' },
  { id: 'etl-004', name: 'User Profile Sync',            schedule: '0 2 * * *',    status: 'succeeded', lastRun: '4 h ago',   duration: '8m 01s',  records: '450K', owner: 'DataEngineer' },
  { id: 'etl-005', name: 'Fraud Detection Features',     schedule: '*/5 * * * *',  status: 'running',   lastRun: '1 min ago', duration: '0m 52s',  records: '230K', owner: 'DataEngineer' },
  { id: 'etl-006', name: 'Log Archival → Cold Storage',  schedule: '0 0 * * *',    status: 'paused',    lastRun: '1 d ago',   duration: '22m 18s', records: '42M',  owner: 'DataEngineer' },
]

const STORAGE = [
  { name: 'Data Warehouse (BQ)', used: 78, total: '10 TB', unit: 'TB', color: 'bg-cyan-500' },
  { name: 'Data Lake (GCS)',     used: 52, total: '50 TB', unit: 'TB', color: 'bg-blue-500' },
  { name: 'Redis Cache',         used: 91, total: '32 GB', unit: 'GB', color: 'bg-red-500'  },
  { name: 'Kafka Lag (events)',  used: 34, total: '100M',  unit: 'M',  color: 'bg-amber-500' },
]

const STATUS_CFG = {
  running:   { label: 'Running',   cls: 'text-blue-400   bg-blue-500/10   border-blue-500/25',   icon: RefreshCw,   spin: true },
  succeeded: { label: 'Succeeded', cls: 'text-green-400  bg-green-500/10  border-green-500/25',  icon: CheckCircle2, spin: false },
  failed:    { label: 'Failed',    cls: 'text-red-400    bg-red-500/10    border-red-500/25',    icon: XCircle,      spin: false },
  paused:    { label: 'Paused',    cls: 'text-slate-400  bg-slate-500/10  border-slate-500/25',  icon: Pause,        spin: false },
}

function StorageBar({ item }) {
  const warn = item.used > 85
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between text-xs">
        <span className="text-slate-300 font-medium">{item.name}</span>
        <span className={warn ? 'text-red-400 font-semibold' : 'text-slate-500'}>
          {item.used}% {warn && '⚠'}
        </span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${item.used > 85 ? 'bg-red-500' : item.color}`}
          style={{ width: `${item.used}%` }}
        />
      </div>
      <p className="text-[10px] text-slate-600">of {item.total}</p>
    </div>
  )
}

export default function DataEngineerPortal({ currentView = 'pipelines' }) {
  if (currentView === 'storage') return <StorageView />
  if (currentView === 'lineage') return <DataLineageView />
  const [triggering, setTriggering] = useState(null)
  const [triggered, setTriggered]   = useState(new Set())

  function triggerRun(id) {
    setTriggering(id)
    setTimeout(() => {
      setTriggering(null)
      setTriggered((p) => new Set([...p, id]))
    }, 2000)
  }

  const running   = ETL_JOBS.filter(j => j.status === 'running').length
  const failed    = ETL_JOBS.filter(j => j.status === 'failed').length
  const succeeded = ETL_JOBS.filter(j => j.status === 'succeeded').length

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Database className="w-5 h-5 text-cyan-400" />
            Pipeline Health
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            ETL job statuses, storage capacity, and on-demand pipeline controls
          </p>
        </div>
        <span className="px-3 py-1.5 rounded-lg border border-cyan-500/25 bg-cyan-500/10 text-cyan-400 text-xs font-semibold">
          📊 Data Engineer View
        </span>
      </div>

      {/* HITL widget */}
      <AgentApprovalsWidget />

      {/* Stat bar */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Jobs Running',   value: running,   cls: 'border-blue-500/20  bg-blue-500/5  text-blue-400'  },
          { label: 'Jobs Succeeded', value: succeeded, cls: 'border-green-500/20 bg-green-500/5 text-green-400' },
          { label: 'Jobs Failed',    value: failed,    cls: 'border-red-500/20   bg-red-500/5   text-red-400'   },
        ].map(({ label, value, cls }) => (
          <div key={label} className={`flex items-center gap-3 px-5 py-4 rounded-2xl border ${cls}`}>
            <span className="text-3xl font-bold text-white">{value}</span>
            <span className="text-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Two-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">

        {/* ETL Jobs table — 2/3 width */}
        <div className="lg:col-span-2 flex flex-col gap-3 p-5 rounded-2xl border border-border bg-card">
          <div className="flex items-center gap-2 mb-1">
            <BarChart3 className="w-4 h-4 text-cyan-400" />
            <h3 className="text-sm font-bold text-white">ETL Job Scheduler</h3>
          </div>

          <div className="flex flex-col gap-2">
            {ETL_JOBS.map((job) => {
              const cfg  = STATUS_CFG[job.status]
              const Icon = cfg.icon
              const isT  = triggering === job.id
              const done = triggered.has(job.id)

              return (
                <div
                  key={job.id}
                  className="flex items-center gap-3 px-4 py-3 rounded-xl border border-border
                    bg-sidebar/50 hover:bg-sidebar transition-colors"
                >
                  <div className="flex-1 min-w-0">
                    <p className="text-xs font-semibold text-white truncate">{job.name}</p>
                    <p className="text-[10px] text-slate-600 font-mono mt-0.5">{job.schedule}</p>
                  </div>

                  <div className="flex flex-col items-end gap-1 text-[10px] text-slate-600 shrink-0 w-24 text-right">
                    <span className="flex items-center gap-1"><Clock className="w-2.5 h-2.5" />{job.lastRun}</span>
                    <span>{job.records} rows</span>
                  </div>

                  <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[11px] font-semibold shrink-0 ${cfg.cls}`}>
                    <Icon className={`w-3 h-3 ${cfg.spin ? 'animate-spin' : ''}`} />
                    {cfg.label}
                  </span>

                  {done ? (
                    <span className="text-[11px] text-green-400 font-semibold shrink-0">✓ Queued</span>
                  ) : (
                    <button
                      onClick={() => triggerRun(job.id)}
                      disabled={isT || job.status === 'running'}
                      className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg bg-cyan-500/10 border border-cyan-500/25
                        text-cyan-400 text-[11px] font-semibold hover:bg-cyan-500/20 transition-colors
                        disabled:opacity-30 disabled:cursor-not-allowed shrink-0"
                      title="Trigger manual run"
                    >
                      {isT
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : <PlayCircle className="w-3 h-3" />
                      }
                    </button>
                  )}
                </div>
              )
            })}
          </div>
        </div>

        {/* Storage panel — 1/3 width */}
        <div className="flex flex-col gap-5 p-5 rounded-2xl border border-border bg-card">
          <div className="flex items-center gap-2">
            <HardDrive className="w-4 h-4 text-blue-400" />
            <h3 className="text-sm font-bold text-white">Storage Capacity</h3>
          </div>
          <div className="flex flex-col gap-5">
            {STORAGE.map((s) => <StorageBar key={s.name} item={s} />)}
          </div>
          <div className="mt-auto pt-4 border-t border-border">
            <p className="text-[10px] text-slate-600 flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-amber-400" />
              Redis cache is near capacity — consider eviction policy review
            </p>
          </div>
        </div>
      </div>

      {/* CI/CD Pipeline Widget */}
      <CIPipelineWidget />
    </div>
  )
}
