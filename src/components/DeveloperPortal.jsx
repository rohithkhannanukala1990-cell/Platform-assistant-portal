import { useState } from 'react'
import {
  GitBranch, CheckCircle2, XCircle, Clock, RefreshCw,
  Rocket, ExternalLink, Package, AlertTriangle, Loader2,
} from 'lucide-react'
import AgentApprovalsWidget from './AgentApprovalsWidget'
import DeploymentsView   from './DeploymentsView'
import RunbooksView      from './RunbooksView'
import LivePipelinesView from './LivePipelinesView'

const SERVICES = [
  {
    name: 'auth-service',
    repo: 'platform/auth-service',
    lang: 'Java 21',
    branch: 'main',
    status: 'passing',
    lastDeploy: '12 min ago',
    version: 'v2.4.1',
    env: 'production',
    coverage: 87,
  },
  {
    name: 'api-gateway',
    repo: 'platform/api-gateway',
    lang: 'Go 1.22',
    branch: 'main',
    status: 'passing',
    lastDeploy: '2 h ago',
    version: 'v1.9.0',
    env: 'production',
    coverage: 92,
  },
  {
    name: 'data-ingestion',
    repo: 'platform/data-ingestion',
    lang: 'Python 3.12',
    branch: 'feature/v2-refactor',
    status: 'failing',
    lastDeploy: '5 h ago',
    version: 'v3.1.0-rc1',
    env: 'staging',
    coverage: 61,
  },
  {
    name: 'notification-svc',
    repo: 'platform/notification-svc',
    lang: 'Node 20',
    branch: 'main',
    status: 'building',
    lastDeploy: '—',
    version: 'v1.2.3',
    env: 'staging',
    coverage: 74,
  },
  {
    name: 'ml-inference',
    repo: 'platform/ml-inference',
    lang: 'Python 3.12',
    branch: 'main',
    status: 'passing',
    lastDeploy: '1 d ago',
    version: 'v0.8.5',
    env: 'production',
    coverage: 55,
  },
  {
    name: 'frontend-web',
    repo: 'platform/frontend-web',
    lang: 'TypeScript',
    branch: 'release/2026-q2',
    status: 'passing',
    lastDeploy: '45 min ago',
    version: 'v4.0.2',
    env: 'production',
    coverage: 79,
  },
]

const STATUS_CFG = {
  passing:  { label: 'Passing',  cls: 'text-green-400 bg-green-500/10 border-green-500/25',  icon: CheckCircle2 },
  failing:  { label: 'Failing',  cls: 'text-red-400   bg-red-500/10   border-red-500/25',    icon: XCircle },
  building: { label: 'Building', cls: 'text-amber-400 bg-amber-500/10 border-amber-500/25',  icon: RefreshCw },
}

const ENV_CFG = {
  production: 'bg-green-500/10 border-green-500/25 text-green-400',
  staging:    'bg-blue-500/10  border-blue-500/25  text-blue-400',
}

function CoverageBadge({ pct }) {
  const color = pct >= 80 ? 'bg-green-500' : pct >= 60 ? 'bg-amber-500' : 'bg-red-500'
  return (
    <div className="flex items-center gap-2 w-full">
      <div className="flex-1 h-1 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-[10px] text-slate-500 w-7 text-right">{pct}%</span>
    </div>
  )
}

export default function DeveloperPortal({ currentView = 'catalog' }) {
  if (currentView === 'deploys')    return <DeploymentsView />
  if (currentView === 'runbooks')   return <RunbooksView />
  if (currentView === 'livepipes')  return (
    <div className="flex flex-col gap-0 max-w-6xl mx-auto pb-16 animate-fade-in h-full">
      <LivePipelinesView />
    </div>
  )
  const [deploying, setDeploying] = useState(null)
  const [deployed, setDeployed]   = useState(new Set())

  function handleDeploy(name) {
    setDeploying(name)
    setTimeout(() => {
      setDeploying(null)
      setDeployed((prev) => new Set([...prev, name]))
    }, 2200)
  }

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <Package className="w-5 h-5 text-blue-400" />
            Software Catalog
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">
            Self-service builds, deployments, and coverage for your services
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-3 py-1.5 rounded-lg border border-blue-500/25 bg-blue-500/10 text-blue-400 text-xs font-semibold">
            💻 Developer View
          </span>
        </div>
      </div>

      {/* HITL widget */}
      <AgentApprovalsWidget />

      {/* Stats bar */}
      <div className="grid grid-cols-3 gap-4">
        {[
          { label: 'Services Passing', value: SERVICES.filter(s => s.status === 'passing').length, cls: 'border-green-500/20 bg-green-500/5 text-green-400' },
          { label: 'Services Failing', value: SERVICES.filter(s => s.status === 'failing').length, cls: 'border-red-500/20 bg-red-500/5 text-red-400' },
          { label: 'Building Now',     value: SERVICES.filter(s => s.status === 'building').length, cls: 'border-amber-500/20 bg-amber-500/5 text-amber-400' },
        ].map(({ label, value, cls }) => (
          <div key={label} className={`flex items-center gap-3 px-5 py-4 rounded-2xl border ${cls}`}>
            <span className="text-3xl font-bold text-white">{value}</span>
            <span className="text-xs text-slate-400">{label}</span>
          </div>
        ))}
      </div>

      {/* Catalog grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-4">
        {SERVICES.map((svc) => {
          const cfg   = STATUS_CFG[svc.status]
          const Icon  = cfg.icon
          const isDep = deploying === svc.name
          const done  = deployed.has(svc.name)

          return (
            <div
              key={svc.name}
              className="flex flex-col gap-4 p-4 rounded-2xl border border-border bg-card
                hover:border-slate-600 transition-all"
            >
              {/* Service header */}
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="text-sm font-bold text-white truncate">{svc.name}</p>
                  <p className="text-[11px] text-slate-500 flex items-center gap-1 mt-0.5">
                    <GitBranch className="w-3 h-3 shrink-0" />
                    {svc.branch}
                  </p>
                </div>
                <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-lg border text-[11px] font-semibold shrink-0 ${cfg.cls}`}>
                  <Icon className={`w-3 h-3 ${svc.status === 'building' ? 'animate-spin' : ''}`} />
                  {cfg.label}
                </span>
              </div>

              {/* Meta row */}
              <div className="flex items-center gap-2 flex-wrap">
                <span className="text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-md font-mono">
                  {svc.lang}
                </span>
                <span className="text-[10px] text-slate-500 bg-slate-800 border border-slate-700 px-2 py-0.5 rounded-md font-mono">
                  {svc.version}
                </span>
                <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${ENV_CFG[svc.env]}`}>
                  {svc.env}
                </span>
              </div>

              {/* Coverage */}
              <div className="flex flex-col gap-1">
                <p className="text-[10px] text-slate-600 font-medium uppercase tracking-widest">Coverage</p>
                <CoverageBadge pct={svc.coverage} />
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between gap-2 pt-1 border-t border-border">
                <div className="flex items-center gap-1 text-[11px] text-slate-600">
                  <Clock className="w-3 h-3" />
                  Last deploy: {svc.lastDeploy}
                </div>
                <div className="flex items-center gap-1.5">
                  <button
                    className="p-1.5 rounded-lg border border-border hover:bg-slate-800 transition-colors text-slate-500 hover:text-white"
                    title="Open in GitHub"
                    onClick={() => window.open(`https://github.com/${svc.repo}`, '_blank')}
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                  </button>
                  {done ? (
                    <span className="flex items-center gap-1 text-[11px] text-green-400 font-semibold">
                      <CheckCircle2 className="w-3.5 h-3.5" /> Deployed
                    </span>
                  ) : (
                    <button
                      onClick={() => handleDeploy(svc.name)}
                      disabled={isDep || svc.status === 'failing'}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-blue-500/15 border border-blue-500/30
                        text-blue-400 text-[11px] font-semibold hover:bg-blue-500/25 transition-colors
                        disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      {isDep
                        ? <><Loader2 className="w-3 h-3 animate-spin" /> Deploying…</>
                        : <><Rocket className="w-3 h-3" /> Deploy</>
                      }
                    </button>
                  )}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
