import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  Home,
  Package,
  GitBranch,
  AlertTriangle,
  Webhook,
  ShieldCheck,
  Bot,
  Boxes,
  Workflow,
  Database,
  Shield,
  Wrench,
  Settings,
  Heart,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useRole } from '../contexts/RoleContext'

const NAV_GROUPS = [
  {
    label: 'PLATFORM',
    items: [
      { label: 'Home', path: '/', icon: Home },
      { label: 'Catalog', path: '/catalog', icon: Package },
      { label: 'Dependency Map', path: '/dependency-graph', icon: GitBranch },
    ],
  },
  {
    label: 'OPERATIONS',
    items: [
      { label: 'Incidents', path: '/incidents', icon: AlertTriangle },
      { label: 'Webhooks', path: '/webhooks', icon: Webhook },
      { label: 'HITL Approvals', path: '/approvals', icon: ShieldCheck },
    ],
  },
  {
    label: 'DEVELOPER TOOLS',
    items: [
      { label: 'AI Assistant', path: '/ai-assistant', icon: Bot },
      { label: 'Infra Builder', path: '/infra', icon: Boxes },
      { label: 'CI/CD Generator', path: '/cicd', icon: Workflow },
      { label: 'DB Analyzer', path: '/db-analyzer', icon: Database },
    ],
  },
  {
    label: 'ADMIN',
    items: [
      { label: 'RBAC', path: '/rbac', icon: Shield },
      { label: 'Tool Registry', path: '/tools', icon: Wrench },
      { label: 'Settings', path: '/settings', icon: Settings },
      { label: 'Health', path: '/health', icon: Heart },
    ],
  },
]

function userInitial(user) {
  const name = user?.username || user?.name || '?'
  return String(name).charAt(0).toUpperCase()
}

export default function Sidebar({ user, onLogout }) {
  const location = useLocation()
  const { role } = useRole()
  const [collapsed, setCollapsed] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )

  useEffect(() => {
    const onResize = () => {
      if (window.innerWidth < 768) setCollapsed(true)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const widthClass = collapsed ? 'w-14' : 'w-60'

  return (
    <aside
      className={`relative flex flex-col shrink-0 bg-neutral-900 border-r border-neutral-800 ${widthClass} transition-[width] duration-200`}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className="absolute top-3 right-2 z-10 p-1 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-800"
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>

      <div className={`flex-1 overflow-y-auto overflow-x-hidden pt-10 pb-2 ${collapsed ? 'px-1' : ''}`}>
        {NAV_GROUPS.map((group) => (
          <div key={group.label} className="mb-1">
            {!collapsed && (
              <p className="text-[10px] uppercase tracking-widest text-neutral-500 px-3 mb-1 mt-4 first:mt-2">
                {group.label}
              </p>
            )}
            <nav className="flex flex-col gap-0.5">
              {group.items.map((item) => {
                const Icon = item.icon
                const active = location.pathname === item.path
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    end={item.path === '/'}
                    title={collapsed ? item.label : undefined}
                    className={`flex items-center gap-3 py-2 rounded-lg mx-2 text-sm transition-colors ${
                      collapsed ? 'justify-center px-2' : 'px-3'
                    } ${
                      active
                        ? 'bg-indigo-600 text-white font-medium'
                        : 'text-neutral-400 hover:bg-neutral-800 hover:text-white'
                    }`}
                  >
                    <Icon className="w-4 h-4 shrink-0" strokeWidth={2} />
                    {!collapsed && <span className="truncate">{item.label}</span>}
                  </NavLink>
                )
              })}
            </nav>
          </div>
        ))}
      </div>

      <div
        className={`border-t border-neutral-800 p-3 flex items-center gap-2 ${
          collapsed ? 'justify-center flex-col' : ''
        }`}
      >
        <div
          className="w-8 h-8 rounded-full bg-indigo-700 flex items-center justify-center text-sm font-bold text-white shrink-0"
          title={user?.username}
        >
          {userInitial(user)}
        </div>
        {!collapsed && (
          <>
            <div className="min-w-0 flex-1">
              <p className="text-sm text-white truncate">{user?.username || 'User'}</p>
              <span className="text-xs bg-neutral-800 text-neutral-300 px-1.5 rounded inline-block mt-0.5">
                {role || user?.role || '—'}
              </span>
            </div>
            <button
              type="button"
              onClick={onLogout}
              className="p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800 shrink-0"
              title="Log out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </>
        )}
        {collapsed && (
          <button
            type="button"
            onClick={onLogout}
            className="p-2 rounded-lg text-neutral-400 hover:text-white hover:bg-neutral-800"
            title="Log out"
          >
            <LogOut className="w-4 h-4" />
          </button>
        )}
      </div>
    </aside>
  )
}
