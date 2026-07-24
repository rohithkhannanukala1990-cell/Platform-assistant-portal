import { useEffect, useMemo, useState, useCallback, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Search, ChevronRight, Zap, Shield } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import { usePlatformContext } from '../contexts/PlatformContext'
import EnvironmentSwitcher from './EnvironmentSwitcher'
import WorkspaceSwitcher from './WorkspaceSwitcher'
import AccountSwitcher from './AccountSwitcher'
import NotificationDropdown from './NotificationDropdown'
import UserMenu from './UserMenu'
import { usePortalWebSocket } from '../hooks/usePortalWebSocket'
import { OPS_HEADER_TOOL_BY_VIEW } from '../constants/opsHeaderTools'

const EXTRA_ROUTE_TOOLS = {
  'live-pipelines': 'github',
  'schema-browser': 'postgres',
  'db-analyzer': 'postgres',
  database: 'postgres',
  deployments: 'github',
  integrations: 'github',
}

function headerToolIdFromPath(pathname) {
  const seg = pathname.split('/').filter(Boolean)[0]
  if (!seg) return 'github'
  return OPS_HEADER_TOOL_BY_VIEW[seg] ?? EXTRA_ROUTE_TOOLS[seg] ?? 'github'
}

function WsIndicator({ connected }) {
  return (
    <div className="relative group cursor-default flex items-center">
      <span
        className={`w-2 h-2 rounded-full transition-colors ${
          connected ? 'bg-green-400' : 'bg-yellow-400 animate-pulse'
        }`}
      />
      <span className="absolute right-0 top-5 hidden group-hover:block bg-neutral-800 text-xs text-white px-2 py-1 rounded whitespace-nowrap z-50 border border-neutral-700 shadow-xl">
        {connected ? 'Live updates active' : 'Reconnecting…'}
      </span>
    </div>
  )
}

const SEGMENT_LABELS = {
  dashboard: 'Dashboard',
  catalog: 'Catalog',
  standards: 'Standards',
  'entity-actions': 'Entity Actions',
  'golden-paths': 'Golden Paths',
  reports: 'Reports',
  deployments: 'Deployments',
  'live-pipelines': 'Live Pipelines',
  'schema-browser': 'Schema Browser',
  'data-lineage': 'Data Lineage',
  'tool-registry': 'Tool Registry',
  'dependency-graph': 'Dependency Map',
  incidents: 'Incidents',
  webhooks: 'Webhooks',
  approvals: 'HITL Approvals',
  'ai-assistant': 'AI Assistant',
  infra: 'Infra Builder',
  cicd: 'CI/CD Generator',
  'db-analyzer': 'DB Analyzer',
  rbac: 'RBAC',
  tools: 'Tool Registry',
  settings: 'Settings',
  health: 'Health',
  ops: 'Operations',
  developer: 'Developer',
  data: 'Data Engineer',
  database: 'Database',
  history: 'History',
  integrations: 'Integrations',
  'system-health': 'System Health',
  storage: 'Storage',
  runbooks: 'Runbooks',
  notifications: 'Notifications',
  workspaces: 'Workspaces',
  templates: 'Templates',
  import: 'Import',
}

function isMacPlatform() {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent)
}

function formatToolLabel(toolId) {
  if (!toolId) return 'Tool'
  return toolId
    .split(/[-_]/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1).toLowerCase())
    .join(' ')
}

function WorkspaceBreadcrumb() {
  const { activeWorkspace } = usePortalContext()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!open) return undefined
    function onDoc(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs"
      >
        <span>🗂</span>
        <span className="max-w-[120px] truncate">{activeWorkspace?.name || 'Select Workspace'}</span>
        <span>▾</span>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50">
          <WorkspaceSwitcher
            isOpen
            onOpenChange={setOpen}
            onClose={() => setOpen(false)}
            renderTrigger={false}
          />
        </div>
      )}
    </div>
  )
}

function AccountBreadcrumb({ toolId }) {
  const { authFetch } = useAuth()
  const [open, setOpen] = useState(false)
  const [accountLabel, setAccountLabel] = useState(null)
  const rootRef = useRef(null)

  useEffect(() => {
    if (!toolId) {
      setAccountLabel(null)
      return undefined
    }
    let cancelled = false
    async function load() {
      try {
        const res = await authFetch('/api/context')
        if (!res.ok || cancelled) return
        const ctx = await res.json()
        const row = (ctx.active_accounts || {})[toolId]
        if (cancelled) return
        if (row?.account_name) {
          setAccountLabel(`${formatToolLabel(toolId)}: ${row.account_name}`)
        } else {
          setAccountLabel(null)
        }
      } catch {
        if (!cancelled) setAccountLabel(null)
      }
    }
    void load()
    const onCtx = () => void load()
    window.addEventListener('context-changed', onCtx)
    return () => {
      cancelled = true
      window.removeEventListener('context-changed', onCtx)
    }
  }, [authFetch, toolId])

  useEffect(() => {
    if (!open) return undefined
    function onDoc(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const label = accountLabel || (toolId ? 'No Account Selected' : 'No Tool Selected')

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 px-2 py-0.5 rounded bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs"
      >
        <span>🔧</span>
        <span className="max-w-[140px] truncate">{label}</span>
        <span>▾</span>
      </button>
      {open && toolId && (
        <div className="absolute top-full left-0 mt-1 z-50">
          <AccountSwitcher toolId={toolId} onClose={() => setOpen(false)} />
        </div>
      )}
    </div>
  )
}

function EnvironmentBreadcrumb() {
  const { environment } = usePlatformContext()
  const [open, setOpen] = useState(false)
  const rootRef = useRef(null)

  const envConfig = {
    production: {
      label: 'production',
      bg: 'bg-red-900/50',
      text: 'text-red-300',
      border: 'border-red-700',
    },
    staging: {
      label: 'staging',
      bg: 'bg-yellow-900/50',
      text: 'text-yellow-300',
      border: 'border-yellow-700',
    },
    dev: {
      label: 'dev',
      bg: 'bg-green-900/50',
      text: 'text-green-300',
      border: 'border-green-700',
    },
    development: {
      label: 'development',
      bg: 'bg-green-900/50',
      text: 'text-green-300',
      border: 'border-green-700',
    },
  }

  const cfg = envConfig[environment] || {
    label: environment || 'dev',
    bg: 'bg-gray-800',
    text: 'text-gray-300',
    border: 'border-gray-600',
  }

  useEffect(() => {
    if (!open) return undefined
    function onDoc(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className={`flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-medium ${cfg.bg} ${cfg.text} ${cfg.border} hover:brightness-110`}
      >
        <span>{cfg.label}</span>
        <span>▾</span>
      </button>
      {open && (
        <div className="absolute top-full left-0 mt-1 z-50">
          <EnvironmentSwitcher onClose={() => setOpen(false)} />
        </div>
      )}
    </div>
  )
}

export default function TopBar({ user, onLogout, onOpenCommandPalette, onMenuOpen }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { pendingApprovalCount } = usePortalContext()
  const [llmLabel, setLlmLabel] = useState('LLM')
  const [unreadCount, setUnreadCount] = useState(0)

  const headerToolId = useMemo(
    () => headerToolIdFromPath(location.pathname),
    [location.pathname]
  )

  const { connected: wsConnected } = usePortalWebSocket({
    userId: user?.username || 'anonymous',
    onMessage: useCallback(() => {}, []),
  })

  const breadcrumbs = useMemo(() => {
    const parts = location.pathname.split('/').filter(Boolean)
    if (parts.length === 0) return [{ label: 'Dashboard', path: '/dashboard' }]
    return parts.map((seg, i) => ({
      label: SEGMENT_LABELS[seg] || seg.charAt(0).toUpperCase() + seg.slice(1).replace(/-/g, ' '),
      path: `/${parts.slice(0, i + 1).join('/')}`,
    }))
  }, [location.pathname])

  useEffect(() => {
    let cancelled = false
    async function loadLlmStatus() {
      try {
        const res = await authFetch('/api/ai/llm/status')
        if (!res.ok) {
          if (!cancelled) setLlmLabel('LLM')
          return
        }
        const data = await res.json()
        if (cancelled) return
        const model = (data.default_model || '').trim()
        setLlmLabel(model || 'LLM')
      } catch {
        if (!cancelled) setLlmLabel('LLM')
      }
    }
    void loadLlmStatus()
    return () => {
      cancelled = true
    }
  }, [authFetch])

  useEffect(() => {
    let cancelled = false
    async function loadNotifications() {
      try {
        const res = await authFetch('/api/notifications')
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return
        const list = Array.isArray(data) ? data : []
        setUnreadCount(list.filter((n) => !n.is_read).length)
      } catch {
        if (!cancelled) setUnreadCount(0)
      }
    }
    void loadNotifications()
    const id = window.setInterval(loadNotifications, 60000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [authFetch])

  const openPalette = () => {
    if (onOpenCommandPalette) onOpenCommandPalette()
    else window.dispatchEvent(new CustomEvent('open-command-palette'))
  }

  const shortcutLabel = isMacPlatform() ? '⌘K' : 'Ctrl+K'

  return (
    <header className="shrink-0 flex flex-col border-b border-neutral-800 bg-neutral-900">
      <div className="flex items-center gap-3 px-6 py-3">
      <button
        type="button"
        className="md:hidden p-2 text-slate-400 hover:text-white transition-colors"
        onClick={onMenuOpen}
      >
        ☰
      </button>
      <div className="flex items-center gap-2 min-w-0 shrink-0">
        <span className="hidden lg:inline text-xs font-semibold text-neutral-500 uppercase tracking-wider shrink-0">
          Platform
        </span>
        <nav className="flex items-center gap-1 min-w-0 text-sm" aria-label="Breadcrumb">
          <button
            type="button"
            onClick={() => navigate('/dashboard')}
            className="text-neutral-400 hover:text-white shrink-0"
          >
            Home
          </button>
          {breadcrumbs.map((crumb) => (
            <span key={crumb.path} className="flex items-center gap-1 min-w-0">
              <ChevronRight className="w-3.5 h-3.5 text-neutral-500 shrink-0" />
              <button
                type="button"
                onClick={() => navigate(crumb.path)}
                className="text-neutral-300 hover:text-white truncate capitalize"
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </nav>
        <EnvironmentSwitcher />
        <WorkspaceSwitcher />
      </div>

      <div className="flex-1 min-w-2" aria-hidden />

      <button
        type="button"
        onClick={openPalette}
        className="hidden sm:flex items-center gap-2 bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-neutral-400 text-sm w-56 lg:w-64 hover:border-neutral-600 hover:text-neutral-300 transition-colors shrink-0"
      >
        <Search className="w-4 h-4 shrink-0" />
        <span className="flex-1 text-left">Search</span>
        <kbd className="px-1 py-0.5 rounded bg-neutral-700 text-[10px] font-mono text-neutral-400">
          {shortcutLabel}
        </kbd>
      </button>

      <div className="flex items-center gap-2 shrink-0">
        <AccountSwitcher toolId={headerToolId} onAccountChanged={() => {}} />

        {pendingApprovalCount > 0 && (
          <button
            type="button"
            onClick={() => navigate('/ai-assistant')}
            title={`${pendingApprovalCount} awaiting approval`}
            className="relative flex items-center justify-center w-9 h-9 rounded-lg border border-neutral-700 hover:bg-neutral-800 text-neutral-300"
          >
            <Shield className="w-4 h-4" />
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-0.5 flex items-center justify-center rounded-full bg-rose-500 text-white text-[10px] font-bold">
              {pendingApprovalCount > 99 ? '99+' : pendingApprovalCount}
            </span>
          </button>
        )}

        <span className="hidden xl:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300">
          <Zap className="w-3.5 h-3.5" />
          {llmLabel}
        </span>

        <WsIndicator connected={wsConnected} />

        <div className="relative">
          <NotificationDropdown
            onSelectIncident={() => navigate('/incidents')}
            onOpenHealthDashboard={() => navigate('/health')}
          />
          {unreadCount > 0 && (
            <span className="pointer-events-none absolute top-0 right-0 z-10 w-4 h-4 flex items-center justify-center bg-rose-500 text-white text-[10px] rounded-full font-bold">
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </div>

        <UserMenu
          onLogout={onLogout}
          onOpenSettings={() => navigate('/settings')}
        />
      </div>
      </div>

      {/* Context Breadcrumb Row */}
      <div className="flex items-center gap-1 px-4 py-1.5 bg-gray-900 border-b border-gray-700 text-sm overflow-x-auto">
        <WorkspaceBreadcrumb />
        <span className="text-gray-600 mx-1">›</span>
        <AccountBreadcrumb toolId={headerToolId} />
        <span className="text-gray-600 mx-1">›</span>
        <EnvironmentBreadcrumb />
      </div>
    </header>
  )
}
