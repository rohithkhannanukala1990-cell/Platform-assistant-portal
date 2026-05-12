import { useNavigate, useLocation } from 'react-router-dom'
import { Activity } from 'lucide-react'
import { useRole, ROLES } from '../contexts/RoleContext'

// ── Nav item sets by role ─────────────────────────────────────────────────────
const OPS_NAV = [
  { id: 'dashboard',     label: 'Dashboard',      emoji: '📊' },
  { id: 'triage',        label: 'Alert Triage',   emoji: '⚡' },
  { id: 'infra',         label: 'Infra Builder',  emoji: '🏗️' },
  { id: 'cicd',          label: 'CI/CD Pipeline', emoji: '🚀' },
  { id: 'integrations',  label: 'Integrations',   emoji: '🔌', adminOnly: true },
  { id: 'import',         label: 'Import',        emoji: '📤', adminOnly: true },
  { id: 'health',         label: 'Health',         emoji: '❤️', adminOnly: true },
  { id: 'tool-registry', label: 'Integration registry', emoji: '🧩', adminOnly: true },
]

const DEV_NAV = [
  { id: 'catalog',    label: 'Software Catalog', emoji: '📦' },
  { id: 'deploys',    label: 'Deployments',       emoji: '🚀' },
  { id: 'livepipes',  label: 'Live Pipelines',    emoji: '🔄' },
  { id: 'runbooks',   label: 'Runbooks',          emoji: '📋' },
]

const DATA_NAV = [
  { id: 'pipelines', label: 'Pipeline Health',  emoji: '⚙️' },
  { id: 'storage',   label: 'Storage',           emoji: '🗄️' },
  { id: 'lineage',   label: 'Data Lineage',      emoji: '🔗' },
]

const DB_NAV = [
  { id: 'dbhealth',  label: 'Database Health',  emoji: '🗄️' },
  { id: 'queries',   label: 'Query Analyzer',    emoji: '🔍' },
  { id: 'schemas',   label: 'Schema Browser',    emoji: '📐' },
]

const NAV_BY_ROLE = {
  Admin:             OPS_NAV,
  NetworkEngineer:   OPS_NAV,
  Developer:         DEV_NAV,
  DataEngineer:      DATA_NAV,
  DatabaseDeveloper: DB_NAV,
}

// ── Sidebar ───────────────────────────────────────────────────────────────────
export default function Sidebar({ activeView, onNavigate, showOpsNav }) {
  const { role, roleInfo } = useRole()
  const navigate           = useNavigate()
  const location           = useLocation()
  const navItems           = NAV_BY_ROLE[role] ?? OPS_NAV

  return (
    <aside className="flex flex-col w-60 min-h-screen bg-sidebar border-r border-border shrink-0">

      {/* Logo — click to go home */}
      <button
        onClick={() => { onNavigate('dashboard'); navigate(roleInfo.portal) }}
        className="flex items-center gap-3 px-5 py-5 border-b border-border w-full text-left
          hover:bg-card/50 transition-colors group cursor-pointer"
        title="Go to Home"
      >
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent/10 border border-accent/30
          group-hover:bg-accent/20 group-hover:border-accent/50 transition-colors shrink-0">
          <Activity className="w-4 h-4 text-accent" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-sm font-bold text-white tracking-wide group-hover:text-accent transition-colors">
            AIOps Portal
          </h1>
          <p className="text-[10px] text-muted font-medium uppercase tracking-widest">Platform Ops</p>
        </div>
      </button>

      {/* Role badge */}
      <div className="px-4 pt-4 pb-2">
        <div className={`inline-flex items-center gap-2 px-3 py-1.5 rounded-lg border text-xs font-semibold ${roleInfo.bg} ${roleInfo.color}`}>
          <span>{roleInfo.emoji}</span>
          {roleInfo.label}
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 px-3 pt-2 flex-1">
        <p className="text-[10px] text-muted font-semibold uppercase tracking-widest px-2 mb-2">
          {role === 'Developer'         ? 'Dev Tools'
         : role === 'DataEngineer'      ? 'Data Tools'
         : role === 'DatabaseDeveloper' ? 'DB Tools'
         : 'Modules'}
        </p>

        {navItems
          .filter((item) => !item.adminOnly || role === 'Admin')
          .map((item) => (
            <NavItem
              key={item.id}
              item={item}
              active={item.externalPath ? location.pathname === item.externalPath : activeView === item.id}
              onNavigate={() => {
                if (item.externalPath) {
                  navigate(item.externalPath)
                  return
                }
                if (item.id === 'health' || item.id === 'tool-registry' || item.id === 'import') {
                  navigate('/ops')
                  onNavigate(item.id)
                  return
                }
                onNavigate(item.id)
              }}
            />
          ))
        }
      </nav>

      {/* Footer */}
      <div className="px-4 py-4 border-t border-border">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-accent animate-pulse" />
          <span className="text-xs text-muted">v0.1.0 — MVP Build</span>
        </div>
      </div>
    </aside>
  )
}

// ── NavItem ───────────────────────────────────────────────────────────────────
function NavItem({ item, active, onNavigate }) {
  const { emoji, label, disabled } = item

  if (disabled) {
    return (
      <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg cursor-not-allowed select-none">
        <span className="text-base opacity-40">{emoji}</span>
        <span className="text-sm font-medium text-slate-600">{label}</span>
        <span className="ml-auto text-[9px] font-semibold uppercase tracking-wider text-slate-700 border border-slate-700 rounded px-1 py-0.5">
          Soon
        </span>
      </div>
    )
  }

  if (active) {
    return (
      <div className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-accent/10 border border-accent/20 cursor-pointer">
        <span className="text-base">{emoji}</span>
        <span className="text-sm font-semibold text-accent">{label}</span>
        <div className="ml-auto w-1.5 h-1.5 rounded-full bg-accent" />
      </div>
    )
  }

  return (
    <button
      onClick={onNavigate}
      className="group flex items-center gap-3 px-3 py-2.5 rounded-lg w-full text-left cursor-pointer hover:bg-card transition-colors"
    >
      <span className="text-base">{emoji}</span>
      <span className="text-sm font-medium text-slate-400 group-hover:text-white transition-colors">{label}</span>
    </button>
  )
}
