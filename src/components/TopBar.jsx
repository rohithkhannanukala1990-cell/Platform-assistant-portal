import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { Search, ChevronRight, Zap, Shield } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import PersonaSwitcher from './PersonaSwitcher'
import NotificationDropdown from './NotificationDropdown'

const SEGMENT_LABELS = {
  dashboard: 'Dashboard',
  catalog: 'Catalog',
  standards: 'Standards',
  'entity-actions': 'Entity Actions',
  'golden-paths': 'Golden Paths',
  reports: 'Reports',
  deployments: 'Deployments',
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

function userInitial(user) {
  const name = user?.username || user?.name || '?'
  return String(name).charAt(0).toUpperCase()
}

function isMacPlatform() {
  if (typeof navigator === 'undefined') return false
  return /Mac|iPhone|iPad|iPod/i.test(navigator.platform || navigator.userAgent)
}

export default function TopBar({ user }) {
  const location = useLocation()
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { pendingApprovalCount } = usePortalContext()
  const [aiProvider, setAiProvider] = useState('ollama')
  const [unreadCount, setUnreadCount] = useState(0)
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
    async function loadSettings() {
      try {
        const res = await authFetch('/api/settings')
        if (!res.ok) return
        const data = await res.json()
        if (cancelled) return
        const provider = (data.ai_provider || data.AI_PROVIDER || 'ollama').toLowerCase()
        setAiProvider(provider.includes('gemini') ? 'gemini' : 'ollama')
      } catch {
        if (!cancelled) setAiProvider('ollama')
      }
    }
    void loadSettings()
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
    window.dispatchEvent(new CustomEvent('open-command-palette'))
  }

  const shortcutLabel = isMacPlatform() ? '⌘K' : 'Ctrl+K'

  return (
    <header className="shrink-0 flex items-center gap-4 px-6 py-3 border-b border-neutral-800 bg-neutral-900">
      <nav className="flex items-center gap-1 min-w-0 flex-1 text-sm" aria-label="Breadcrumb">
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

      <button
        type="button"
        onClick={openPalette}
        className="hidden sm:flex items-center gap-2 bg-neutral-800 border border-neutral-700 rounded-lg px-3 py-1.5 text-neutral-400 text-sm w-64 hover:border-neutral-600 hover:text-neutral-300 transition-colors"
      >
        <Search className="w-4 h-4 shrink-0" />
        <span className="flex-1 text-left">Search anything...</span>
        <kbd className="text-[10px] text-neutral-500 font-mono">{shortcutLabel}</kbd>
      </button>

      <div className="flex items-center gap-3 shrink-0 ml-auto">
        <PersonaSwitcher />

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

        <span
          className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold ${
            aiProvider === 'gemini'
              ? 'bg-blue-900 text-blue-300'
              : 'bg-purple-900 text-purple-300'
          }`}
        >
          <Zap className="w-3.5 h-3.5" />
          {aiProvider === 'gemini' ? 'Gemini' : 'Ollama'}
        </span>

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

        <div className="flex items-center gap-2 pl-1 border-l border-neutral-800">
          <div className="w-8 h-8 rounded-full bg-indigo-700 flex items-center justify-center text-sm font-bold text-white">
            {userInitial(user)}
          </div>
          <span className="text-sm text-white hidden md:inline truncate max-w-[120px]">
            {user?.username || 'User'}
          </span>
        </div>
      </div>
    </header>
  )
}
