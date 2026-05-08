import { useState } from 'react'
import {
  Database, CheckCircle2, XCircle, Clock, PlayCircle,
  AlertTriangle, TrendingUp, HardDrive, RefreshCw,
  BarChart3, Loader2, Pause,
} from 'lucide-react'
import AgentApprovalsWidget from './AgentApprovalsWidget'

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

export default function DataEngineerPortal() {
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
    </div>
  )
}
