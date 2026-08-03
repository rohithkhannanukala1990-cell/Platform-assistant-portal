import { useEffect, useMemo, useState, useCallback } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Search, ChevronRight, Zap, Shield } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
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
  github: 'github',
  prs: 'github',
  actions: 'github',
  pagerduty: 'pagerduty',
  kubernetes: 'kubernetes',
}

function headerToolIdFromPath(pathname) {
  const seg = pathname.split('/').filter(Boolean)[0]
  if (!seg || seg === 'dashboard') return null
  return OPS_HEADER_TOOL_BY_VIEW[seg] ?? EXTRA_ROUTE_TOOLS[seg] ?? null
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
  github: 'GitHub',
  prs: 'Pull Requests',
  actions: 'Actions',
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

export default function TopBar({ user, onOpenCommandPalette, onMenuOpen }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { pendingApprovalCount } = usePortalContext()
  const [llmLabel, setLlmLabel] = useState('LLM')

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
        const res = await authFetch('/api/llm/status')
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

  const openPalette = () => {
    if (onOpenCommandPalette) onOpenCommandPalette()
    else window.dispatchEvent(new CustomEvent('open-command-palette'))
  }

  const shortcutLabel = isMacPlatform() ? '⌘K' : 'Ctrl+K'

  return (
    <header className="shrink-0 border-b border-neutral-800 bg-neutral-900">
      <div className="flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 min-w-0">
        <button
          type="button"
          className="md:hidden p-2 text-slate-400 hover:text-white transition-colors shrink-0"
          onClick={onMenuOpen}
        >
          ☰
        </button>

        <nav
          className="hidden md:flex items-center gap-1 min-w-0 flex-1 text-sm overflow-hidden"
          aria-label="Breadcrumb"
        >
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
                className="text-neutral-300 hover:text-white truncate capitalize max-w-[10rem]"
              >
                {crumb.label}
              </button>
            </span>
          ))}
        </nav>

        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0 ml-auto">
          <div className="hidden sm:flex items-center gap-1.5 shrink-0">
            <EnvironmentSwitcher />
            <WorkspaceSwitcher />
            {headerToolId ? (
              <div className="max-w-[11rem]">
                <AccountSwitcher toolId={headerToolId} onAccountChanged={() => {}} />
              </div>
            ) : null}
          </div>

          <button
            type="button"
            onClick={openPalette}
            className="hidden md:flex items-center gap-2 bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-neutral-400 text-sm w-36 lg:w-44 hover:border-neutral-600 hover:text-neutral-300 transition-colors shrink-0"
          >
            <Search className="w-4 h-4 shrink-0" />
            <span className="flex-1 text-left truncate">Search</span>
            <kbd className="px-1 py-0.5 rounded bg-neutral-700 text-[10px] font-mono text-neutral-400">
              {shortcutLabel}
            </kbd>
          </button>

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

          <span className="hidden 2xl:inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-950 text-emerald-300">
            <Zap className="w-3.5 h-3.5" />
            {llmLabel}
          </span>

          <div className="hidden sm:block">
            <WsIndicator connected={wsConnected} />
          </div>

          <UserMenu onOpenSettings={() => navigate('/settings')} />

          <NotificationDropdown
            onSelectIncident={() => navigate('/incidents')}
            onOpenHealthDashboard={() => navigate('/health')}
          />
        </div>
      </div>
    </header>
  )
}
