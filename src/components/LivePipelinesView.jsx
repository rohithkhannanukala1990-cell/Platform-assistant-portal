import { useState, useEffect, useCallback } from 'react'
import {
  GitBranch, RefreshCw, CheckCircle2, XCircle,
  Clock, AlertTriangle, Loader2, User, Zap,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const ACTIVE_API   = '/api/cicd/active-runs'
const MONITOR_API  = '/api/cicd/monitor'

const STAGES = ['Build', 'Test', 'Security Scan', 'Deploy']

const STATUS_CONFIG = {
  success: { color: 'text-emerald-400', bg: 'bg-emerald-500/15 border-emerald-500/30', label: 'Passed' },
  running: { color: 'text-blue-400',    bg: 'bg-blue-500/15 border-blue-500/30',       label: 'Running' },
  failed:  { color: 'text-red-400',     bg: 'bg-red-500/15 border-red-500/30',         label: 'Failed'  },
  pending: { color: 'text-slate-500',   bg: 'bg-slate-700/40 border-slate-600/30',     label: 'Queued'  },
}

const RUN_STATUS_BADGE = {
  running: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
  failed:  'bg-red-500/20  text-red-300  border border-red-500/30',
  success: 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30',
}

function StageNode({ stage, stageStatus, isActive }) {
  const cfg = STATUS_CONFIG[stageStatus] ?? STATUS_CONFIG.pending

  return (
    <div className="flex flex-col items-center gap-1.5">
      <div className={`relative flex items-center justify-center w-9 h-9 rounded-full border-2 ${cfg.bg} transition-all duration-300`}>
        {stageStatus === 'running' && (
          <Loader2 size={16} className="animate-spin text-blue-400" />
        )}
        {stageStatus === 'success' && (
          <CheckCircle2 size={16} className="text-emerald-400" />
        )}
        {stageStatus === 'failed' && (
          <XCircle size={16} className="text-red-400" />
        )}
        {stageStatus === 'pending' && (
          <div className="w-2 h-2 rounded-full bg-slate-500" />
        )}
        {stageStatus === 'running' && (
          <span className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-blue-400 animate-ping opacity-75" />
        )}
      </div>
      <span className={`text-[10px] font-medium whitespace-nowrap ${cfg.color}`}>{stage}</span>
    </div>
  )
}

function Connector({ fromStatus }) {
  const filled = fromStatus === 'success'
  return (
    <div className="flex-1 flex items-center px-1" style={{ minWidth: 20, marginBottom: 18 }}>
      <div
        className={`h-0.5 w-full transition-all duration-500 ${filled ? 'bg-emerald-500/60' : 'bg-slate-600/40'}`}
      />
    </div>
  )
}

function PipelineRow({ run, onSelectRun, selected }) {
  const stages = STAGES
  const badgeClass = RUN_STATUS_BADGE[run.status] ?? RUN_STATUS_BADGE.running

  return (
    <div
      className={`group cursor-pointer rounded-xl border transition-all duration-200
        ${selected
          ? 'border-blue-500/60 bg-blue-500/10 shadow-lg shadow-blue-500/10'
          : 'border-slate-700/50 bg-slate-800/50 hover:border-slate-600/60 hover:bg-slate-800/70'
        }`}
      onClick={() => onSelectRun(run)}
    >
      {/* Header */}
      <div className="flex items-start justify-between p-3 pb-2">
        <div className="flex items-center gap-2 min-w-0">
          <GitBranch size={13} className="text-slate-400 shrink-0" />
          <div className="min-w-0">
            <p className="text-xs font-semibold text-slate-200 truncate">{run.repository}</p>
            <p className="text-[10px] text-slate-500 truncate">{run.branch}</p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wide ${badgeClass}`}>
            {run.status}
          </span>
          <div className="flex items-center gap-1 text-[10px] text-slate-500">
            <Clock size={10} />
            {run.elapsed_time}
          </div>
        </div>
      </div>

      {/* DAG row */}
      <div className="flex items-center px-4 pb-3">
        {stages.map((stage, i) => (
          <div key={stage} className="flex items-center flex-1 min-w-0">
            <StageNode
              stage={stage}
              stageStatus={run.stage_statuses?.[stage] ?? 'pending'}
              isActive={run.current_stage === stage}
            />
            {i < stages.length - 1 && (
              <Connector fromStatus={run.stage_statuses?.[stage]} />
            )}
          </div>
        ))}
      </div>

      {/* Footer */}
      <div className="flex items-center gap-3 px-3 py-2 border-t border-slate-700/40 text-[10px] text-slate-500">
        <div className="flex items-center gap-1">
          <User size={10} />
          {run.trigger_user}
        </div>
        <span className="text-slate-600">·</span>
        <span className="font-mono text-slate-500">{run.commit}</span>
        <span className="text-slate-600">·</span>
        <span className="truncate">{run.commit_message}</span>
      </div>
    </div>
  )
}

function StageSummaryBar({ runs }) {
  const list = Array.isArray(runs) ? runs : []
  const counts = { success: 0, running: 0, failed: 0, pending: 0 }
  list.forEach(r => {
    const s = r.status
    if (s in counts) counts[s]++
  })
  return (
    <div className="grid grid-cols-4 gap-3 mb-4">
      {[
        { label: 'Running',  key: 'running', icon: Loader2,      cls: 'text-blue-400',    bg: 'bg-blue-500/10 border-blue-500/20'    },
        { label: 'Passed',   key: 'success', icon: CheckCircle2, cls: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/20' },
        { label: 'Failed',   key: 'failed',  icon: XCircle,      cls: 'text-red-400',     bg: 'bg-red-500/10 border-red-500/20'      },
        { label: 'Queued',   key: 'pending', icon: Clock,        cls: 'text-slate-400',   bg: 'bg-slate-700/30 border-slate-600/20'  },
      ].map(({ label, key, icon: Icon, cls, bg }) => (
        <div key={key} className={`flex items-center gap-2 rounded-lg border p-2.5 ${bg}`}>
          <Icon size={16} className={`${cls} ${key === 'running' ? 'animate-spin' : ''}`} />
          <div>
            <p className={`text-lg font-bold ${cls}`}>{counts[key]}</p>
            <p className="text-[10px] text-slate-500 leading-none">{label}</p>
          </div>
        </div>
      ))}
    </div>
  )
}

function RunDetail({ run }) {
  if (!run) return (
    <div className="flex flex-col items-center justify-center h-full text-slate-600 gap-2">
      <GitBranch size={32} />
      <p className="text-sm">Select a pipeline to inspect</p>
    </div>
  )

  const stages = STAGES

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-200">{run.repository}</h3>
        <p className="text-xs text-slate-500">{run.branch} · {run.trigger_event} by {run.trigger_user}</p>
      </div>

      {/* Full stage pipeline */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold mb-4">Pipeline Stages</p>
        <div className="space-y-2">
          {stages.map((stage) => {
            const s = run.stage_statuses?.[stage] ?? 'pending'
            const cfg = STATUS_CONFIG[s]
            return (
              <div key={stage} className={`flex items-center justify-between rounded-lg border px-3 py-2 ${cfg.bg}`}>
                <div className="flex items-center gap-2">
                  {s === 'running' && <Loader2 size={13} className="animate-spin text-blue-400" />}
                  {s === 'success' && <CheckCircle2 size={13} className="text-emerald-400" />}
                  {s === 'failed'  && <XCircle      size={13} className="text-red-400" />}
                  {s === 'pending' && <Clock        size={13} className="text-slate-500" />}
                  <span className={`text-xs font-medium ${cfg.color}`}>{stage}</span>
                </div>
                <span className={`text-[10px] font-semibold uppercase tracking-wide ${cfg.color}`}>
                  {cfg.label}
                </span>
              </div>
            )
          })}
        </div>
      </div>

      {/* Commit info */}
      <div className="rounded-xl border border-slate-700/50 bg-slate-900/50 p-4 space-y-2">
        <p className="text-[10px] uppercase tracking-widest text-slate-500 font-semibold">Commit</p>
        <div className="flex items-center gap-2">
          <code className="text-xs text-violet-300 font-mono">{run.commit}</code>
          <span className="text-slate-600">·</span>
          <span className="text-xs text-slate-400">{run.commit_message}</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <User size={11} />
          <span>{run.trigger_user}</span>
          <span className="text-slate-600">·</span>
          <Clock size={11} />
          <span>{run.elapsed_time}</span>
        </div>
      </div>

      {run.status === 'failed' && (
        <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-3">
          <div className="flex items-center gap-2 mb-1">
            <AlertTriangle size={13} className="text-red-400" />
            <span className="text-xs font-semibold text-red-300">Stage Failed: {run.current_stage}</span>
          </div>
          <p className="text-[11px] text-red-400">
            This pipeline has been flagged and an incident will be created for the responsible team.
          </p>
        </div>
      )}
    </div>
  )
}

export default function LivePipelinesView() {
  const { authFetch } = useAuth()
  const [runs, setRuns]               = useState([])
  const [loading, setLoading]         = useState(true)
  const [selectedRun, setSelectedRun] = useState(null)
  const [scanning, setScanning]       = useState(false)
  const [scanMsg, setScanMsg]         = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [emptyMessage, setEmptyMessage] = useState(null)

  const fetchRuns = useCallback(async () => {
    try {
      const res = await authFetch(ACTIVE_API)
      const data = await res.json()
      const nextRuns = Array.isArray(data)
        ? data
        : Array.isArray(data?.runs)
          ? data.runs
          : []
      setRuns(nextRuns)
      if (data && typeof data === 'object' && !Array.isArray(data) && data.status === 'no_data') {
        setEmptyMessage(
          data.message || 'Connect a GitHub or GitLab CI account to populate active runs.'
        )
      } else {
        setEmptyMessage(null)
      }
      setLastRefresh(new Date())
    } catch {
      /* keep stale data */
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    fetchRuns()
    const iv = setInterval(fetchRuns, 8000)
    return () => clearInterval(iv)
  }, [fetchRuns])

  const triggerMonitor = async () => {
    setScanning(true)
    setScanMsg(null)
    try {
      const res  = await authFetch(MONITOR_API, { method: 'POST' })
      const data = await res.json()
      setScanMsg({ type: 'success', text: `Monitor scan dispatched. Any stuck pipelines will be triaged automatically.` })
    } catch {
      setScanMsg({ type: 'error', text: 'Failed to trigger monitor scan. Check backend connection.' })
    } finally {
      setScanning(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Zap size={16} className="text-blue-400" />
            Live CI/CD Pipelines
          </h2>
          <p className="text-[11px] text-slate-500 mt-0.5">
            Real-time pipeline status · Build → Test → Security Scan → Deploy
            {lastRefresh && (
              <span className="ml-2 text-slate-600">
                · Updated {lastRefresh.toLocaleTimeString()}
              </span>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={triggerMonitor}
            disabled={scanning}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
              bg-amber-500/15 border border-amber-500/30 text-amber-300
              hover:bg-amber-500/25 disabled:opacity-50 transition-all"
          >
            {scanning
              ? <><Loader2 size={12} className="animate-spin" /> Scanning…</>
              : <><AlertTriangle size={12} /> Run Monitor Scan</>
            }
          </button>
          <button
            onClick={fetchRuns}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold
              bg-slate-700/50 border border-slate-600/40 text-slate-300
              hover:bg-slate-600/50 transition-all"
          >
            <RefreshCw size={12} />
            Refresh
          </button>
        </div>
      </div>

      {scanMsg && (
        <div className={`flex items-start gap-2 rounded-lg border p-3 mb-3 text-xs
          ${scanMsg.type === 'success'
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
            : 'bg-red-500/10 border-red-500/30 text-red-300'
          }`}>
          {scanMsg.type === 'success'
            ? <CheckCircle2 size={13} className="shrink-0 mt-0.5" />
            : <XCircle      size={13} className="shrink-0 mt-0.5" />
          }
          {scanMsg.text}
          <button onClick={() => setScanMsg(null)} className="ml-auto opacity-60 hover:opacity-100">
            ×
          </button>
        </div>
      )}

      {loading ? (
        <div className="flex-1 flex items-center justify-center">
          <Loader2 size={28} className="animate-spin text-blue-400" />
        </div>
      ) : (
        <div className="flex-1 grid grid-cols-5 gap-4 min-h-0">
          {/* Left: pipeline list */}
          <div className="col-span-3 flex flex-col gap-3 overflow-y-auto pr-1 min-h-0">
            <StageSummaryBar runs={Array.isArray(runs) ? runs : []} />
            {(Array.isArray(runs) ? runs : []).length === 0 ? (
              <div className="rounded-xl border border-dashed border-slate-700/60 bg-slate-800/30 px-6 py-12 text-center space-y-3">
                <p className="text-sm text-slate-400">
                  {emptyMessage || 'No active runs'}
                </p>
                {emptyMessage ? (
                  <a
                    href="/tool-registry"
                    className="inline-flex text-sm font-medium text-indigo-400 hover:text-indigo-300"
                  >
                    Connect GitHub in Tool Registry
                  </a>
                ) : null}
              </div>
            ) : (
              runs.map(run => (
                <PipelineRow
                  key={run.id}
                  run={run}
                  selected={selectedRun?.id === run.id}
                  onSelectRun={setSelectedRun}
                />
              ))
            )}
          </div>

          {/* Right: detail panel */}
          <div className="col-span-2 rounded-xl border border-slate-700/50 bg-slate-800/40 p-4 overflow-y-auto">
            <RunDetail run={selectedRun} />
          </div>
        </div>
      )}
    </div>
  )
}
