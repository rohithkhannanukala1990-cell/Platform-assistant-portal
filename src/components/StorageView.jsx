import { useState } from 'react'
import {
  HardDrive, AlertTriangle, CheckCircle2, TrendingUp,
  TrendingDown, RefreshCw, DollarSign, Cloud, Archive,
  Loader2,
} from 'lucide-react'
import { DemoPreviewBanner } from './ui'

const BUCKETS = [
  { id: 'bq-warehouse',   name: 'Data Warehouse',     provider: 'BigQuery',   region: 'us-central1', usedGB: 7800, totalGB: 10240, cost: 312.40, trend: +4.2,  status: 'warning',  icon: '📦', lastModified: '2 min ago' },
  { id: 'gcs-datalake',   name: 'Data Lake (Raw)',     provider: 'GCS',        region: 'us-central1', usedGB: 26624, totalGB: 51200, cost: 531.20, trend: +8.1,  status: 'ok',       icon: '🗄️', lastModified: '15 min ago' },
  { id: 'gcs-processed',  name: 'Processed Layer',     provider: 'GCS',        region: 'us-east1',    usedGB: 4096, totalGB: 10240, cost: 81.90,  trend: -1.2,  status: 'ok',       icon: '✅', lastModified: '1 h ago' },
  { id: 's3-archive',     name: 'Cold Archive',        provider: 'S3 Glacier', region: 'us-east-1',   usedGB: 102400, totalGB: 204800, cost: 46.08, trend: +12.0, status: 'ok',      icon: '🧊', lastModified: '1 d ago' },
  { id: 'gcs-ml-models',  name: 'ML Model Registry',   provider: 'GCS',        region: 'us-central1', usedGB: 912, totalGB: 1024, cost: 18.20,  trend: +21.5, status: 'critical', icon: '🤖', lastModified: '5 min ago' },
  { id: 'gcs-logs',       name: 'Application Logs',    provider: 'GCS',        region: 'eu-west1',    usedGB: 6144, totalGB: 10240, cost: 122.90, trend: +3.0,  status: 'warning',  icon: '📋', lastModified: '30 sec ago' },
]

const COST_BY_TEAM = [
  { team: 'Data Engineering', cost: 612, pct: 48, color: 'bg-cyan-500' },
  { team: 'ML Platform',      cost: 248, pct: 19, color: 'bg-purple-500' },
  { team: 'Backend Eng',      cost: 192, pct: 15, color: 'bg-blue-500' },
  { team: 'Analytics',        cost: 154, pct: 12, color: 'bg-amber-500' },
  { team: 'DevOps',           cost: 76,  pct:  6, color: 'bg-slate-500' },
]

const STATUS_CFG = {
  ok:       { cls: 'text-green-400 bg-green-500/10 border-green-500/25',  label: 'Healthy',  bar: 'bg-green-500'  },
  warning:  { cls: 'text-amber-400 bg-amber-500/10 border-amber-500/25',  label: 'High',     bar: 'bg-amber-500'  },
  critical: { cls: 'text-red-400   bg-red-500/10   border-red-500/25',    label: 'Critical', bar: 'bg-red-500'    },
}

function fmtGB(gb) {
  return gb >= 1024 ? `${(gb / 1024).toFixed(1)} TB` : `${gb} GB`
}

export default function StorageView() {
  const [refreshing, setRefreshing] = useState(false)
  const [lastRefresh, setLastRefresh] = useState('Just now')

  function handleRefresh() {
    setRefreshing(true)
    setTimeout(() => { setRefreshing(false); setLastRefresh('Just now') }, 1800)
  }

  const totalCost = BUCKETS.reduce((s, b) => s + b.cost, 0)
  const criticalCount = BUCKETS.filter(b => b.status === 'critical').length
  const warningCount  = BUCKETS.filter(b => b.status === 'warning').length

  return (
    <div className="flex flex-col gap-6 max-w-6xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-cyan-400" />
            Storage
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Cloud storage usage, capacity, and cost breakdown</p>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-slate-600">Last refreshed: {lastRefresh}</span>
          <button
            onClick={handleRefresh}
            disabled={refreshing}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-700 text-slate-400
              hover:text-white hover:border-slate-600 text-xs transition-colors disabled:opacity-40"
          >
            <RefreshCw className={`w-3 h-3 ${refreshing ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      <DemoPreviewBanner title="Preview — sample storage">
        Bucket sizes and costs below are illustrative until cloud storage connectors report live usage.
      </DemoPreviewBanner>

      {/* Summary cards */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Total Buckets',   value: BUCKETS.length,         icon: HardDrive,    cls: 'text-cyan-400',   bg: 'border-cyan-500/20   bg-cyan-500/5'   },
          { label: 'Critical Usage',  value: criticalCount,          icon: AlertTriangle, cls: 'text-red-400',    bg: 'border-red-500/20    bg-red-500/5'    },
          { label: 'High Usage',      value: warningCount,           icon: AlertTriangle, cls: 'text-amber-400',  bg: 'border-amber-500/20  bg-amber-500/5'  },
          { label: 'Monthly Cost',    value: `$${totalCost.toFixed(0)}`, icon: DollarSign, cls: 'text-green-400', bg: 'border-green-500/20  bg-green-500/5'  },
        ].map(({ label, value, icon: Icon, cls, bg }) => (
          <div key={label} className={`flex items-center gap-3 px-4 py-4 rounded-2xl border ${bg}`}>
            <Icon className={`w-5 h-5 ${cls} shrink-0`} />
            <div>
              <p className="text-lg font-bold text-white">{value}</p>
              <p className="text-[10px] text-slate-500">{label}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Bucket cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {BUCKETS.map(b => {
          const cfg = STATUS_CFG[b.status]
          const pct = Math.round((b.usedGB / b.totalGB) * 100)
          return (
            <div key={b.id} className="flex flex-col gap-3 p-4 rounded-2xl border border-border bg-card hover:border-slate-600 transition-all">
              {/* Bucket header */}
              <div className="flex items-start justify-between gap-2">
                <div className="flex items-center gap-2.5">
                  <span className="text-xl">{b.icon}</span>
                  <div>
                    <p className="text-sm font-bold text-white">{b.name}</p>
                    <p className="text-[10px] text-slate-500 flex items-center gap-1">
                      <Cloud className="w-2.5 h-2.5" /> {b.provider} · {b.region}
                    </p>
                  </div>
                </div>
                <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold shrink-0 ${cfg.cls}`}>
                  {cfg.label}
                </span>
              </div>

              {/* Usage bar */}
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between text-[10px]">
                  <span className="text-slate-400 font-semibold">{fmtGB(b.usedGB)} used</span>
                  <span className="text-slate-500">{fmtGB(b.totalGB)} total</span>
                </div>
                <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full transition-all ${cfg.bar}`} style={{ width: `${pct}%` }} />
                </div>
                <div className="flex items-center justify-between text-[10px]">
                  <span className={`font-bold ${pct >= 90 ? 'text-red-400' : pct >= 75 ? 'text-amber-400' : 'text-green-400'}`}>{pct}% used</span>
                  <span className="text-slate-600">Last write: {b.lastModified}</span>
                </div>
              </div>

              {/* Cost + trend */}
              <div className="flex items-center justify-between pt-2 border-t border-border">
                <div className="flex items-center gap-1.5 text-xs text-slate-400">
                  <DollarSign className="w-3 h-3 text-green-400" />
                  <span className="font-semibold text-white">${b.cost.toFixed(2)}</span>
                  <span className="text-slate-600">/ mo</span>
                </div>
                <div className={`flex items-center gap-1 text-[11px] font-semibold ${b.trend >= 0 ? 'text-red-400' : 'text-green-400'}`}>
                  {b.trend >= 0
                    ? <TrendingUp className="w-3 h-3" />
                    : <TrendingDown className="w-3 h-3" />
                  }
                  {b.trend >= 0 ? '+' : ''}{b.trend}% MoM
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Cost by team */}
      <div className="p-5 rounded-2xl border border-border bg-card flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <p className="text-sm font-bold text-white flex items-center gap-2">
            <DollarSign className="w-4 h-4 text-green-400" />
            Monthly Cost by Team
          </p>
          <span className="text-xs font-bold text-white">${totalCost.toFixed(0)} total</span>
        </div>
        <div className="flex flex-col gap-3">
          {COST_BY_TEAM.map(t => (
            <div key={t.team} className="flex items-center gap-3">
              <span className="text-xs text-slate-400 w-36 shrink-0">{t.team}</span>
              <div className="flex-1 h-2 bg-slate-800 rounded-full overflow-hidden">
                <div className={`h-full rounded-full ${t.color}`} style={{ width: `${t.pct}%` }} />
              </div>
              <span className="text-xs text-slate-400 w-16 text-right shrink-0">${t.cost}</span>
              <span className="text-[10px] text-slate-600 w-8 text-right shrink-0">{t.pct}%</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
