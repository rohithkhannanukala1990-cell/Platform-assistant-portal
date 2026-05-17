import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Package,
  ClipboardCheck,
  GitBranch,
  BookOpen,
  Workflow,
  ShieldCheck,
  Play,
  Briefcase,
  Plug,
  Rocket,
  Cog,
  Bot,
  BarChart2,
  Shield,
  Wrench,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import { useRole } from '../contexts/RoleContext'

const NAV_GROUPS = [
  {
    label: 'DEVELOPER TOOLS',
    items: [
      { label: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
      { label: 'Catalog', path: '/catalog', icon: Package },
      { label: 'Scorecards', path: '/scorecards', icon: ClipboardCheck },
      { label: 'Dependency Graph', path: '/dependency-graph', icon: GitBranch },
      { label: 'Templates', path: '/templates', icon: BookOpen },
      { label: 'Golden Paths', path: '/golden-paths', icon: Workflow },
    ],
  },
  {
    label: 'PLATFORM',
    items: [
      { label: 'Standards', path: '/standards', icon: ShieldCheck },
      { label: 'Entity Actions', path: '/entity-actions', icon: Play },
      { label: 'Workspaces', path: '/workspaces', icon: Briefcase },
      { label: 'Integrations', path: '/integrations', icon: Plug },
    ],
  },
  {
    label: 'OPERATIONS',
    items: [
      { label: 'CI/CD', path: '/cicd', icon: Cog },
      { label: 'Deployments', path: '/deployments', icon: Rocket },
      { label: 'AI Assistant', path: '/ai-assistant', icon: Bot },
    ],
  },
  {
    label: 'ADMIN',
    items: [
      { label: 'Reports', path: '/reports', icon: BarChart2 },
      { label: 'RBAC Manager', path: '/rbac', icon: Shield },
      { label: 'Tool Registry', path: '/tool-registry', icon: Wrench },
    ],
  },
]

function userInitial(user) {
  const name = user?.username || user?.name || '?'
  return String(name).charAt(0).toUpperCase()
}

function isActivePath(pathname, itemPath) {
  if (itemPath === '/dashboard') {
    return pathname === '/dashboard' || pathname === '/'
  }
  return pathname === itemPath
}

export default function Sidebar({ user, onLogout }) {
  const location = useLocation()
  const { role } = useRole()
  const [collapsed, setCollapsed] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )
  const [narrow, setNarrow] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )

  useEffect(() => {
    const onResize = () => {
      const isNarrow = window.innerWidth < 768
      setNarrow(isNarrow)
      if (isNarrow) setCollapsed(true)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  const widthClass = collapsed ? (narrow ? 'w-0 border-r-0' : 'w-14') : 'w-60'
  const hiddenOnNarrow = collapsed && narrow

  return (
    <aside
      className={`relative flex flex-col shrink-0 bg-neutral-900 border-r border-neutral-800 overflow-hidden ${widthClass} transition-[width] duration-200`}
    >
      <button
        type="button"
        onClick={() => setCollapsed((c) => !c)}
        className={`absolute top-3 z-10 p-1 rounded-md text-neutral-400 hover:text-white hover:bg-neutral-800 ${
          hiddenOnNarrow ? 'left-2' : 'right-2'
        }`}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
      >
        {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
      </button>

      <div
        className={`flex-1 overflow-y-auto overflow-x-hidden pt-10 pb-2 ${
          collapsed && !narrow ? 'px-1' : ''
        } ${hiddenOnNarrow ? 'invisible' : ''}`}
      >
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
                const active = isActivePath(location.pathname, item.path)
                return (
                  <NavLink
                    key={item.path}
                    to={item.path}
                    title={collapsed ? item.label : undefined}
                    className={`flex items-center gap-3 py-2 rounded-lg mx-2 text-sm transition-colors ${
                      collapsed && !narrow ? 'justify-center px-2' : 'px-3'
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
          hiddenOnNarrow ? 'invisible h-0 p-0 border-0 overflow-hidden' : collapsed ? 'justify-center flex-col' : ''
        }`}
      >
        <div
          className="w-8 h-8 rounded-full bg-indigo-700 flex items-center justify-center text-sm font-bold text-white shrink-0"
          title={user?.username}
        >
          {userInitial(user)}
        </div>
        {!collapsed && !hiddenOnNarrow && (
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
        {collapsed && !hiddenOnNarrow && (
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
