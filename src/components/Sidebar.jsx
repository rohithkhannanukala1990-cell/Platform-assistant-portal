import { Activity } from 'lucide-react'

const NAV_ITEMS = [
  { id: 'dashboard', label: 'Dashboard',     emoji: '📊', disabled: false },
  { id: 'triage',    label: 'Alert Triage',  emoji: '⚡', disabled: false },
  { id: 'infra',     label: 'Infra Builder', emoji: '🏗️', disabled: false },
  { id: 'cicd',      label: 'CI/CD Pipeline',emoji: '🚀', disabled: false },
]

export default function Sidebar({ activeView, onNavigate }) {
  return (
    <aside className="flex flex-col w-60 min-h-screen bg-sidebar border-r border-border shrink-0">
      {/* Logo */}
      <div className="flex items-center gap-3 px-5 py-5 border-b border-border">
        <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent/10 border border-accent/30">
          <Activity className="w-4 h-4 text-accent" strokeWidth={2.5} />
        </div>
        <div>
          <h1 className="text-sm font-bold text-white tracking-wide">AIOps Portal</h1>
          <p className="text-[10px] text-muted font-medium uppercase tracking-widest">Platform Ops</p>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex flex-col gap-1 px-3 pt-4 flex-1">
        <p className="text-[10px] text-muted font-semibold uppercase tracking-widest px-2 mb-2">
          Modules
        </p>
        {NAV_ITEMS.map((item) => (
          <NavItem
            key={item.id}
            item={item}
            active={activeView === item.id}
            onNavigate={onNavigate}
          />
        ))}
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

function NavItem({ item, active, onNavigate }) {
  const { id, emoji, label, disabled } = item

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
      onClick={() => onNavigate?.(id)}
      className="group flex items-center gap-3 px-3 py-2.5 rounded-lg w-full text-left cursor-pointer hover:bg-card transition-colors"
    >
      <span className="text-base">{emoji}</span>
      <span className="text-sm font-medium text-slate-400 group-hover:text-white transition-colors">{label}</span>
    </button>
  )
}
