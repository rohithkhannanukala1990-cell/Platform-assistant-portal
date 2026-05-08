import { useState } from 'react'
import {
  Rocket, CheckCircle2, XCircle, Clock, RefreshCw,
  GitBranch, GitCommit, User, ChevronDown, AlertTriangle,
  RotateCcw, FileText, Filter, Loader2, Terminal,
} from 'lucide-react'

const ENVIRONMENTS = ['All', 'production', 'staging', 'dev']

const DEPLOYMENTS = [
  { id: 'dpl-001', service: 'auth-service',      version: 'v2.4.1', env: 'production', status: 'success',  triggeredBy: 'rohit.k',    commit: 'a3f91bc', message: 'fix: token refresh race condition',        duration: '3m 12s', time: '12 min ago'  },
  { id: 'dpl-002', service: 'api-gateway',        version: 'v1.9.0', env: 'production', status: 'success',  triggeredBy: 'ci-bot',      commit: 'd7e22fa', message: 'feat: rate limiting per endpoint',         duration: '2m 48s', time: '2 h ago'     },
  { id: 'dpl-003', service: 'data-ingestion',     version: 'v3.1.0', env: 'staging',    status: 'failed',   triggeredBy: 'priya.m',     commit: 'c14a3b2', message: 'refactor: switch to async queue',          duration: '1m 05s', time: '5 h ago'     },
  { id: 'dpl-004', service: 'frontend-web',       version: 'v4.0.2', env: 'production', status: 'success',  triggeredBy: 'ci-bot',      commit: 'f80d91e', message: 'chore: bump dependency versions',          duration: '4m 33s', time: '45 min ago'  },
  { id: 'dpl-005', service: 'ml-inference',       version: 'v0.8.5', env: 'production', status: 'success',  triggeredBy: 'james.t',     commit: 'b55aec1', message: 'perf: model quantisation for faster P99',   duration: '6m 11s', time: '1 d ago'     },
  { id: 'dpl-006', service: 'notification-svc',   version: 'v1.2.3', env: 'staging',    status: 'running',  triggeredBy: 'ana.v',       commit: '3e6f02d', message: 'feat: Slack notification templating',        duration: '—',      time: 'Just now'    },
  { id: 'dpl-007', service: 'auth-service',       version: 'v2.4.0', env: 'production', status: 'success',  triggeredBy: 'ci-bot',      commit: '9a7d213', message: 'chore: update log4j to 2.23.1',             duration: '3m 01s', time: '3 d ago'     },
  { id: 'dpl-008', service: 'api-gateway',        version: 'v1.8.9', env: 'production', status: 'rolled_back', triggeredBy: 'rohit.k', commit: '1c3b820', message: 'feat: add gRPC transcoding',                 duration: '1m 44s', time: '4 d ago'     },
]

const STATUS_CFG = {
  success:     { label: 'Success',     cls: 'text-green-400  bg-green-500/10  border-green-500/25',  icon: CheckCircle2 },
  failed:      { label: 'Failed',      cls: 'text-red-400    bg-red-500/10    border-red-500/25',    icon: XCircle },
  running:     { label: 'Deploying',   cls: 'text-blue-400   bg-blue-500/10   border-blue-500/25',   icon: RefreshCw },
  rolled_back: { label: 'Rolled Back', cls: 'text-amber-400  bg-amber-500/10  border-amber-500/25',  icon: RotateCcw },
}

const ENV_CFG = {
  production: 'bg-green-500/10 border-green-500/25 text-green-400',
  staging:    'bg-blue-500/10  border-blue-500/25  text-blue-400',
  dev:        'bg-slate-500/10 border-slate-500/25 text-slate-400',
}

const MOCK_LOG = `[00:00] Initialising deployment pipeline...
[00:01] Pulling image: ghcr.io/platform/{service}:{version}
[00:02] Running pre-deploy health checks...
[00:04] Draining old pods from load balancer...
[00:06] Rolling update: 0/3 pods replaced
[00:08] Rolling update: 1/3 pods replaced
[00:10] Rolling update: 2/3 pods replaced
[00:12] Rolling update: 3/3 pods replaced ✓
[00:13] Running smoke tests...
[00:14] Smoke tests PASSED (12/12)
[00:15] ✅ Deployment complete. All replicas healthy.`

export default function DeploymentsView() {
  const [envFilter,    setEnvFilter]    = useState('All')
  const [logsFor,      setLogsFor]      = useState(null)
  const [rolling,      setRolling]      = useState(null)
  const [rolledBack,   setRolledBack]   = useState(new Set())
  const [deploying,    setDeploying]    = useState(false)
  const [newSvc,       setNewSvc]       = useState('auth-service')
  const [newEnv,       setNewEnv]       = useState('staging')
  const [newDeployLog, setNewDeployLog] = useState(null)

  const filtered = DEPLOYMENTS.filter(d => envFilter === 'All' || d.env === envFilter)

  function handleRollback(id) {
    setRolling(id)
    setTimeout(() => {
      setRolling(null)
      setRolledBack(prev => new Set([...prev, id]))
    }, 2500)
  }

  function handleNewDeploy() {
    setDeploying(true)
    setNewDeployLog(null)
    setTimeout(() => {
      setDeploying(false)
      setNewDeployLog(MOCK_LOG.replace(/{service}/g, newSvc).replace(/{version}/g, 'latest'))
    }, 3000)
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Rocket className="w-5 h-5 text-blue-400" />
            Deployments
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Deployment history and rollback controls for all services</p>
        </div>
      </div>

      {/* New deploy panel */}
      <div className="p-5 rounded-2xl border border-blue-500/20 bg-blue-500/5 flex flex-col gap-4">
        <p className="text-xs font-bold text-blue-400 uppercase tracking-widest">Trigger New Deployment</p>
        <div className="flex items-end gap-3 flex-wrap">
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-500 uppercase font-semibold tracking-widest">Service</label>
            <select
              value={newSvc}
              onChange={e => setNewSvc(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              {['auth-service','api-gateway','data-ingestion','notification-svc','ml-inference','frontend-web'].map(s => (
                <option key={s} value={s}>{s}</option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1.5">
            <label className="text-[10px] text-slate-500 uppercase font-semibold tracking-widest">Environment</label>
            <select
              value={newEnv}
              onChange={e => setNewEnv(e.target.value)}
              className="bg-slate-900 border border-slate-700 text-slate-200 text-xs rounded-lg px-3 py-2 focus:outline-none focus:border-blue-500"
            >
              {['staging','production','dev'].map(e => <option key={e} value={e}>{e}</option>)}
            </select>
          </div>
          <button
            onClick={handleNewDeploy}
            disabled={deploying}
            className="flex items-center gap-2 px-4 py-2 rounded-xl bg-blue-500/20 border border-blue-500/40
              text-blue-400 text-xs font-bold hover:bg-blue-500/30 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {deploying
              ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Deploying…</>
              : <><Rocket className="w-3.5 h-3.5" /> Deploy Now</>
            }
          </button>
        </div>
        {newDeployLog && (
          <div className="flex flex-col rounded-xl border border-green-500/20 overflow-hidden">
            <div className="flex items-center gap-2 px-4 py-2 bg-black/60 border-b border-green-500/15">
              <div className="flex gap-1.5">
                <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
                <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
              </div>
              <Terminal className="w-3 h-3 text-green-400" />
              <span className="text-[10px] font-mono text-green-400 font-semibold">{newSvc} → {newEnv}</span>
            </div>
            <pre className="px-4 py-3 bg-black text-[10px] font-mono text-green-400 leading-relaxed whitespace-pre max-h-48 overflow-y-auto">
              {newDeployLog}
            </pre>
          </div>
        )}
      </div>

      {/* Filter bar */}
      <div className="flex items-center gap-2 flex-wrap">
        <Filter className="w-3.5 h-3.5 text-slate-500" />
        <span className="text-[10px] text-slate-500 uppercase font-semibold tracking-widest">Environment:</span>
        {ENVIRONMENTS.map(env => (
          <button
            key={env}
            onClick={() => setEnvFilter(env)}
            className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
              envFilter === env
                ? 'bg-accent/15 border-accent/40 text-accent'
                : 'bg-transparent border-slate-700 text-slate-500 hover:text-white hover:border-slate-600'
            }`}
          >
            {env}
          </button>
        ))}
        <span className="ml-auto text-[10px] text-slate-600">{filtered.length} deployments</span>
      </div>

      {/* Deployment table */}
      <div className="flex flex-col rounded-2xl border border-border overflow-hidden">
        <div className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr_1fr_auto] gap-0 px-4 py-2.5 bg-slate-900 border-b border-border">
          {['Service / Commit', 'Version', 'Environment', 'Status', 'Triggered By', 'Duration', ''].map(h => (
            <span key={h} className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">{h}</span>
          ))}
        </div>
        {filtered.map(d => {
          const cfg  = STATUS_CFG[rolledBack.has(d.id) ? 'rolled_back' : d.status]
          const Icon = cfg.icon
          return (
            <div
              key={d.id}
              className="grid grid-cols-[2fr_1fr_1fr_1fr_1.5fr_1fr_auto] items-center gap-0 px-4 py-3 border-b border-border/50 last:border-0 hover:bg-card/40 transition-colors"
            >
              {/* Service + commit */}
              <div className="flex flex-col gap-0.5 min-w-0">
                <span className="text-xs font-semibold text-white truncate">{d.service}</span>
                <div className="flex items-center gap-1.5 text-[10px] text-slate-500">
                  <GitCommit className="w-2.5 h-2.5 shrink-0" />
                  <span className="font-mono">{d.commit}</span>
                  <span className="truncate text-slate-600" title={d.message}>{d.message}</span>
                </div>
              </div>
              <span className="text-xs font-mono text-slate-400">{d.version}</span>
              <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold w-fit ${ENV_CFG[d.env]}`}>{d.env}</span>
              <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[10px] font-semibold w-fit ${cfg.cls}`}>
                <Icon className={`w-3 h-3 ${d.status === 'running' ? 'animate-spin' : ''}`} />
                {cfg.label}
              </span>
              <div className="flex items-center gap-1 text-[10px] text-slate-500">
                <User className="w-2.5 h-2.5" />{d.triggeredBy}
                <span className="ml-2 flex items-center gap-1 text-slate-600"><Clock className="w-2.5 h-2.5" />{d.time}</span>
              </div>
              <span className="text-[10px] text-slate-500 flex items-center gap-1">
                <Clock className="w-2.5 h-2.5" />{d.duration}
              </span>
              <div className="flex items-center gap-1.5">
                <button
                  onClick={() => setLogsFor(logsFor === d.id ? null : d.id)}
                  className="p-1.5 rounded-lg border border-border hover:bg-slate-800 text-slate-500 hover:text-white transition-colors"
                  title="View logs"
                >
                  <FileText className="w-3 h-3" />
                </button>
                {d.status === 'success' && !rolledBack.has(d.id) && (
                  <button
                    onClick={() => handleRollback(d.id)}
                    disabled={rolling === d.id}
                    className="p-1.5 rounded-lg border border-amber-500/25 bg-amber-500/5 hover:bg-amber-500/15 text-amber-500 transition-colors disabled:opacity-40"
                    title="Rollback"
                  >
                    {rolling === d.id
                      ? <Loader2 className="w-3 h-3 animate-spin" />
                      : <RotateCcw className="w-3 h-3" />
                    }
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

      {/* Inline log drawer */}
      {logsFor && (
        <div className="flex flex-col rounded-2xl border border-slate-700 overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 bg-black/60 border-b border-slate-700">
            <div className="flex gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-red-500/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-yellow-500/60" />
              <span className="w-2.5 h-2.5 rounded-full bg-green-500/60" />
            </div>
            <Terminal className="w-3 h-3 text-slate-400" />
            <span className="text-[10px] font-mono text-slate-400">deploy-log — {DEPLOYMENTS.find(d => d.id === logsFor)?.service}</span>
            <button onClick={() => setLogsFor(null)} className="ml-auto text-slate-600 hover:text-white text-xs">✕</button>
          </div>
          <pre className="px-4 py-3 bg-black/80 text-[10px] font-mono text-green-400 leading-relaxed whitespace-pre max-h-52 overflow-y-auto">
            {MOCK_LOG.replace(/{service}/g, DEPLOYMENTS.find(d => d.id === logsFor)?.service ?? '').replace(/{version}/g, DEPLOYMENTS.find(d => d.id === logsFor)?.version ?? '')}
          </pre>
        </div>
      )}
    </div>
  )
}
