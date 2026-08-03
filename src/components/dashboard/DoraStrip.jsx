import { useNavigate } from 'react-router-dom'
import {
  Gauge,
  Rocket,
  Clock,
  AlertTriangle,
  RefreshCw,
  ArrowUpRight,
  ArrowDownRight,
  Minus,
} from 'lucide-react'
import { SectionHeader } from '../ui'

const LEVEL_COLORS = {
  Elite:  { text: 'text-emerald-400', bg: 'bg-emerald-500/15', border: 'border-emerald-500/30' },
  High:   { text: 'text-blue-400',    bg: 'bg-blue-500/15',    border: 'border-blue-500/30'    },
  Medium: { text: 'text-amber-400',   bg: 'bg-amber-500/15',   border: 'border-amber-500/30'   },
  Low:    { text: 'text-red-400',     bg: 'bg-red-500/15',     border: 'border-red-500/30'     },
}

function DoraCard({ label, icon: Icon, iconColor, metric }) {
  if (!metric) return null
  const lvl = LEVEL_COLORS[metric.level] ?? LEVEL_COLORS.High
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
        <TrendIcon size={11} className={
          metric.trend_dir === 'down_good' || metric.trend_dir === 'up'
            ? 'text-emerald-400'
            : 'text-slate-500'
        } />
        {metric.trend}
      </div>
    </div>
  )
}

export default function DoraStrip({ dora }) {
  const navigate = useNavigate()
  if (!dora) return null

  return (
    <div className="flex flex-col gap-3">
      <SectionHeader
        title="DORA Metrics"
        icon={Gauge}
        hint="Engineering delivery performance"
        actions={(
          <button
            type="button"
            onClick={() => navigate('/dora')}
            className="flex items-center gap-1 text-xs text-accent-hover hover:text-white transition-colors"
          >
            Details
            <ArrowUpRight className="w-3.5 h-3.5" />
          </button>
        )}
      />
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <DoraCard label="Deploy Frequency" icon={Rocket}        iconColor="text-emerald-400" metric={dora.deployment_frequency} />
        <DoraCard label="Lead Time"        icon={Clock}         iconColor="text-blue-400"    metric={dora.lead_time} />
        <DoraCard label="Change Failure"   icon={AlertTriangle} iconColor="text-amber-400"   metric={dora.change_failure_rate} />
        <DoraCard label="MTTR"             icon={RefreshCw}     iconColor="text-violet-400"  metric={dora.mttr} />
      </div>
    </div>
  )
}
