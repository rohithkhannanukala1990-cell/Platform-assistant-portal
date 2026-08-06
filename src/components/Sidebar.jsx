import { useEffect, useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard,
  Bell,
  AlertTriangle,
  HeartPulse,
  CheckSquare,
  BookOpen,
  GitFork,
  ClipboardCheck,
  BadgeCheck,
  ShieldCheck,
  Zap,
  Route,
  Layout,
  BarChart2,
  TrendingUp,
  GitBranch,
  Rocket,
  BookMarked,
  Server,
  Hammer,
  Users,
  Wrench,
  Download,
  Grid,
  Plug,
  Webhook,
  Settings,
  Sparkles,
  Database,
  Activity,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Bot,
  Code2,
  TerminalSquare,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const ICON_MAP = {
  LayoutDashboard,
  Bell,
  AlertTriangle,
  HeartPulse,
  CheckSquare,
  BookOpen,
  GitFork,
  ClipboardCheck,
  BadgeCheck,
  ShieldCheck,
  Zap,
  Route,
  Layout,
  BarChart2,
  TrendingUp,
  GitBranch,
  Rocket,
  BookMarked,
  Server,
  Hammer,
  Users,
  Wrench,
  Download,
  Grid,
  Plug,
  Webhook,
  Settings,
  Sparkles,
  Database,
  Activity,
  Bot,
  Code2,
  TerminalSquare,
}

const NAV_GROUPS = [
  {
    name: 'Ops & Incidents',
    defaultOpen: true,
    items: [
      { label: 'Dashboard', path: '/dashboard', icon: 'LayoutDashboard' },
      { label: 'Alert Triage', path: '/alerts', icon: 'Bell' },
      { label: 'Incidents', path: '/incidents', icon: 'AlertTriangle' },
      { label: 'Health', path: '/health', icon: 'HeartPulse' },
      { label: 'Approvals', path: '/approvals', icon: 'CheckSquare' },
    ],
  },
  {
    name: 'IDP Platform',
    defaultOpen: false,
    items: [
      { label: 'Catalog', path: '/catalog', icon: 'BookOpen' },
      { label: 'Dependency Graph', path: '/dependency-graph', icon: 'GitFork' },
      { label: 'Scorecards', path: '/scorecards', icon: 'ClipboardCheck' },
      { label: 'Standards', path: '/standards', icon: 'BadgeCheck' },
      { label: 'Entity Actions', path: '/entity-actions', icon: 'Zap' },
      { label: 'Golden Paths', path: '/golden-paths', icon: 'Route' },
      { label: 'Template Gallery', path: '/template-gallery', icon: 'Layout' },
    ],
  },
  {
    name: 'Engineering Reports',
    defaultOpen: false,
    items: [
      { label: 'Reports', path: '/reports', icon: 'BarChart2' },
      { label: 'DORA Metrics', path: '/dora', icon: 'TrendingUp' },
    ],
  },
  {
    name: 'Developer Tools',
    defaultOpen: false,
    items: [
      { label: 'CI/CD Pipelines', path: '/cicd', icon: 'GitBranch' },
      { label: 'Deployments', path: '/deployments', icon: 'Rocket', preview: true },
      { label: 'Kubernetes', path: '/k8s', icon: 'Server' },
      { label: 'Infra Builder', path: '/infra', icon: 'Hammer' },
      { label: 'Runbooks', path: '/runbooks', icon: 'BookMarked' },
      { label: 'Data Tools', path: '/data-tools', icon: 'Database' },
      { label: 'Connectors', path: '/connectors', icon: 'Plug' },
    ],
  },
  {
    name: 'Administration',
    defaultOpen: false,
    adminOnly: true,
    items: [
      { label: 'RBAC Manager', path: '/rbac', icon: 'Users' },
      { label: 'Tool Registry', path: '/tool-registry', icon: 'Wrench' },
      { label: 'Account Import', path: '/account-import', icon: 'Download' },
      { label: 'Workspaces', path: '/workspaces', icon: 'Grid' },
      { label: 'Integrations', path: '/integrations', icon: 'Webhook' },
      { label: 'Settings', path: '/settings', icon: 'Settings' },
    ],
  },
  {
    name: 'AI',
    defaultOpen: true,
    items: [
      { label: 'AI Assistant', path: '/ai-assistant', icon: 'Sparkles' },
      { label: 'Agents', path: '/agents', icon: 'Bot', badgeKey: 'agentApprovals' },
      { label: 'Run History', path: '/agent-history', icon: 'Activity' },
      { label: 'Code Editor', path: '/editor', icon: 'Code2' },
      { label: 'Terminal', path: '/terminal', icon: 'TerminalSquare' },
    ],
  },
]

const OPEN_GROUPS_STORAGE_KEY = 'sidebar_open_groups'

function readStoredOpenGroups() {
  const defaults = Object.fromEntries(NAV_GROUPS.map((g) => [g.name, g.defaultOpen]))
  try {
    const raw = localStorage.getItem(OPEN_GROUPS_STORAGE_KEY)
    if (!raw) return defaults
    const stored = JSON.parse(raw)
    return { ...defaults, ...stored }
  } catch {
    return defaults
  }
}

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

export default function Sidebar({ user, open = false, onClose }) {
  const location = useLocation()
  const { role, authFetch } = useAuth()
  const isAdmin = role === 'Admin'
  const [agentApprovalCount, setAgentApprovalCount] = useState(0)

  const [collapsed, setCollapsed] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )
  const [narrow, setNarrow] = useState(() =>
    typeof window !== 'undefined' ? window.innerWidth < 768 : false
  )
  const [openGroups, setOpenGroups] = useState(readStoredOpenGroups)

  const toggleGroup = (name) =>
    setOpenGroups((prev) => {
      const next = { ...prev, [name]: !prev[name] }
      try {
        localStorage.setItem(OPEN_GROUPS_STORAGE_KEY, JSON.stringify(next))
      } catch {
        /* persistence is best-effort */
      }
      return next
    })

  useEffect(() => {
    const onResize = () => {
      const isNarrow = window.innerWidth < 768
      setNarrow(isNarrow)
      if (isNarrow) setCollapsed(true)
    }
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  useEffect(() => {
    let cancelled = false

    async function loadApprovals() {
      try {
        const res = await authFetch('/api/agents/approvals')
        if (!res.ok) {
          if (!cancelled) setAgentApprovalCount(0)
          return
        }
        const data = await res.json()
        if (!cancelled) setAgentApprovalCount(Array.isArray(data) ? data.length : 0)
      } catch {
        if (!cancelled) setAgentApprovalCount(0)
      }
    }

    void loadApprovals()
    const t = setInterval(() => void loadApprovals(), 15000)
    return () => {
      cancelled = true
      clearInterval(t)
    }
  }, [authFetch])

  const widthClass = collapsed ? (narrow ? 'w-0 border-r-0' : 'w-14') : 'w-60'
  const hiddenOnNarrow = collapsed && narrow

  function NavItem({ label, path, icon, badgeKey, preview }) {
    const Icon = ICON_MAP[icon] || LayoutDashboard
    const badgeCount = badgeKey === 'agentApprovals' ? agentApprovalCount : 0
    const layoutClasses = collapsed && !narrow ? 'justify-center px-2' : 'px-3'
    return (
      <NavLink
        to={path}
        end
        title={collapsed ? (preview ? `${label} (preview)` : label) : undefined}
        aria-current={isActivePath(location.pathname, path) ? 'page' : undefined}
        className={({ isActive }) => {
          const active =
            path === '/dashboard' ? isActive || location.pathname === '/' : isActive
          return `flex items-center gap-3 py-2 rounded-lg mx-2 text-sm transition-colors ${layoutClasses} ${
            active
              ? 'bg-accent text-white font-medium'
              : 'text-neutral-400 hover:bg-neutral-800 hover:text-white'
          }`
        }}
      >
        <span className="relative shrink-0">
          <Icon className="w-4 h-4" strokeWidth={2} />
          {collapsed && !narrow && badgeCount > 0 && (
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-amber-500" />
          )}
        </span>
        {!collapsed && (
          <>
            <span className="truncate flex-1">{label}</span>
            {preview && (
              <span className="shrink-0 text-[9px] uppercase tracking-wider font-semibold text-amber-400/90 border border-amber-500/30 rounded px-1 py-0.5">
                Preview
              </span>
            )}
            {badgeCount > 0 && (
              <span className="inline-flex items-center justify-center min-w-[1.25rem] h-5 px-1 rounded-full bg-amber-500 text-neutral-950 text-[10px] font-bold">
                {badgeCount > 99 ? '99+' : badgeCount}
              </span>
            )}
          </>
        )}
      </NavLink>
    )
  }

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 md:hidden"
          onClick={onClose}
        />
      )}
      <aside
        className={`
          fixed inset-y-0 left-0 z-50 w-64
          transform transition-transform duration-200
          md:relative md:translate-x-0 md:w-auto
          ${open ? 'translate-x-0' : '-translate-x-full'}
          bg-neutral-900 border-r border-neutral-800
          flex flex-col shrink-0 overflow-hidden ${widthClass}
        `}
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
        {isAdmin && (
          <nav className="mb-3 px-2">
            <NavLink
              to="/admin"
              title={collapsed ? 'Admin Console' : undefined}
              aria-current={location.pathname === '/admin' ? 'page' : undefined}
              className={({ isActive }) =>
                `flex items-center gap-3 py-2 rounded-lg text-sm transition-colors ${
                  collapsed && !narrow ? 'justify-center px-2' : 'px-3'
                } ${
                  isActive
                    ? 'bg-accent text-white font-medium'
                    : 'text-accent-hover hover:bg-neutral-800 hover:text-white border border-accent/30'
                }`
              }
            >
              <ShieldCheck className="w-4 h-4 shrink-0" strokeWidth={2} />
              {!collapsed && !hiddenOnNarrow && <span className="truncate">Admin Console</span>}
            </NavLink>
          </nav>
        )}
        {NAV_GROUPS.map((group) => {
          if (group.adminOnly && !isAdmin) return null

          if (collapsed && !narrow) {
            return (
              <nav key={group.name} className="flex flex-col gap-0.5 mb-1">
                {group.items.map((item) => (
                  <NavItem key={item.path} {...item} />
                ))}
              </nav>
            )
          }

          return (
            <div key={group.name} className="mb-1">
              <button
                type="button"
                onClick={() => toggleGroup(group.name)}
                className="flex items-center justify-between w-full px-3 py-1.5 text-xs font-semibold uppercase tracking-wider text-neutral-500 hover:text-neutral-300 transition-colors mt-2"
              >
                <span>{group.name}</span>
                <ChevronDown
                  className={`w-3 h-3 transition-transform duration-200 ${
                    openGroups[group.name] ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {openGroups[group.name] && (
                <div className="flex flex-col gap-0.5">
                  {group.items.map((item) => (
                    <NavItem key={item.path} {...item} />
                  ))}
                </div>
              )}
            </div>
          )
        })}
      </div>

      <div
        className={`border-t border-neutral-800 p-3 flex items-center gap-2 ${
          hiddenOnNarrow ? 'invisible h-0 p-0 border-0 overflow-hidden' : collapsed ? 'justify-center' : ''
        }`}
        title={user?.username || 'User'}
      >
        <div className="w-8 h-8 rounded-full bg-accent flex items-center justify-center text-sm font-bold text-white shrink-0">
          {userInitial(user)}
        </div>
        {!collapsed && !hiddenOnNarrow && (
          <div className="min-w-0 flex-1">
            <p className="text-sm text-white truncate">{user?.username || 'User'}</p>
            <span className="text-xs bg-neutral-800 text-neutral-300 px-1.5 rounded inline-block mt-0.5">
              {role || user?.role || '—'}
            </span>
          </div>
        )}
      </div>
    </aside>
    </>
  )
}
