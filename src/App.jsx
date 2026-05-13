import { useState, useCallback, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'

function buildPortalWsUrl() {
  try {
    const u = new URL(API_BASE)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    u.pathname = '/ws/portal'
    u.search = ''
    u.hash = ''
    return u.toString()
  } catch {
    return 'ws://localhost:8000/ws/portal'
  }
}

import { RoleProvider, useRole, ROLES } from './contexts/RoleContext'
import { useAuth } from './contexts/AuthContext'

import Sidebar              from './components/Sidebar'
import OpsPortal            from './components/OpsPortal'
import DeveloperPortal      from './components/DeveloperPortal'
import DataEngineerPortal   from './components/DataEngineerPortal'
import DatabasePortal       from './components/DatabasePortal'
import LoginPage            from './components/LoginPage'
import SettingsModal        from './components/SettingsModal'
import ChatBot              from './components/ChatBot'
import Header               from './components/Header'
import AgentApprovalsWidget from './components/AgentApprovalsWidget'
import HistoryPanel         from './components/HistoryPanel'
import IntegrationsPage     from './components/IntegrationsPage'
import TriageView           from './components/TriageView'
import StorageView          from './components/StorageView'
import RunbooksView         from './components/RunbooksView'
import InfraBuilderView     from './components/InfraBuilderView'
import DeploymentsView      from './components/DeploymentsView'
import LivePipelinesView    from './components/LivePipelinesView'
import HealthDashboard      from './components/HealthDashboard'
import { OPS_HEADER_TOOL_BY_VIEW } from './constants/opsHeaderTools'

const OPS_URL_VIEWS = new Set([
  'dashboard',
  'triage',
  'infra',
  'cicd',
  'integrations',
  'health',
  'tool-registry',
  'workspaces',
  'templates',
  'import',
])

// ── Per-role default portal path ──────────────────────────────────────────────
function defaultPortalForRole(role) {
  return ROLES[role]?.portal ?? '/ops'
}

// ── Inner layout (needs router context via useRole / useNavigate) ─────────────
function AppLayout() {
  // ── ALL hooks at the very top — no exceptions ──
  const { isAuthenticated, loading, logout, authFetch } = useAuth()
  const { role, roleInfo } = useRole()
  const location = useLocation()
  const navigate = useNavigate()

  const [currentOpsView,  setCurrentOpsView]  = useState('dashboard')
  const [currentDevView,  setCurrentDevView]  = useState('catalog')
  const [currentDataView, setCurrentDataView] = useState('pipelines')
  const [currentDbView,   setCurrentDbView]   = useState('dbhealth')
  const [opsBreadcrumb,   setOpsBreadcrumb]   = useState('Dashboard')
  const [settingsOpen,    setSettingsOpen]    = useState(false)
  const [healthStatus, setHealthStatus] = useState('healthy')
  const [criticalHealthBanner, setCriticalHealthBanner] = useState(null)
  const [healthWsToast, setHealthWsToast] = useState(null)

  const openHealthDashboard = useCallback(() => {
    navigate('/ops')
    setCurrentOpsView('health')
  }, [navigate])

  useEffect(() => {
    if (role !== 'Admin') return undefined
    let cancelled = false
    async function pollSummary() {
      try {
        const r = await fetch(`${API_BASE}/api/health/summary`)
        if (!r.ok) return
        const d = await r.json()
        if (!cancelled) setHealthStatus(d.status || 'healthy')
      } catch {
        if (!cancelled) setHealthStatus('warning')
      }
    }
    pollSummary()
    const id = window.setInterval(pollSummary, 60000)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [role])

  useEffect(() => {
    if (role !== 'Admin') return undefined
    let ws
    try {
      ws = new WebSocket(buildPortalWsUrl())
      ws.onmessage = (ev) => {
        let data
        try {
          data = JSON.parse(ev.data)
        } catch {
          return
        }
        if (data.type !== 'health_alert') return
        window.dispatchEvent(new CustomEvent('portal-health-alert', { detail: data }))
        if (data.severity === 'critical') {
          setCriticalHealthBanner(data.message || 'Critical system alert')
        } else if (data.severity === 'warning') {
          setHealthWsToast(data.message || 'Health warning')
          window.setTimeout(() => setHealthWsToast(null), 8000)
        }
      }
    } catch {
      /* WS optional */
    }
    return () => {
      if (ws && ws.readyState <= 1) ws.close()
    }
  }, [role])

  // Unified nav handler — routes to the right state based on active role
  function handleNav(viewId) {
    if (role === 'Admin' || role === 'NetworkEngineer') setCurrentOpsView(viewId)
    else if (role === 'Developer')         setCurrentDevView(viewId)
    else if (role === 'DataEngineer')      setCurrentDataView(viewId)
    else if (role === 'DatabaseDeveloper') setCurrentDbView(viewId)
  }

  // Active view for sidebar highlight
  function activeViewId() {
    if (role === 'Admin' || role === 'NetworkEngineer') return currentOpsView
    if (role === 'Developer')         return currentDevView
    if (role === 'DataEngineer')      return currentDataView
    if (role === 'DatabaseDeveloper') return currentDbView
    return 'dashboard'
  }

  // stable callback so OpsPortal doesn't re-render on every breadcrumb update
  const handleBreadcrumb = useCallback((label) => {
    setOpsBreadcrumb((prev) => (prev === label ? prev : label))
  }, [])

  useEffect(() => {
    if (location.pathname !== '/ops') return
    const p = new URLSearchParams(location.search)
    const v = p.get('view')
    if (v && OPS_URL_VIEWS.has(v)) setCurrentOpsView(v)
  }, [location.pathname, location.search])

  // ── Auth gate AFTER all hooks ──
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-surface">
        <Loader2 className="w-8 h-8 animate-spin text-accent" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <LoginPage />
  }

  const DEV_LABELS  = { catalog: 'Software Catalog', deploys: 'Deployments', livepipes: 'Live Pipelines', runbooks: 'Runbooks' }
  const DATA_LABELS = { pipelines: 'Pipeline Health', storage: 'Storage', lineage: 'Data Lineage' }
  const DB_LABELS   = { dbhealth: 'Database Health', queries: 'Query Analyzer', schemas: 'Schema Browser' }

  function breadcrumb() {
    if (location.pathname === '/system-health') return 'System Health'
    if (location.pathname === '/ops' && currentOpsView === 'health') return 'System Health'
    if (location.pathname === '/ops' && currentOpsView === 'tool-registry') return 'Integrations'
    if (location.pathname === '/ops' && currentOpsView === 'workspaces') return 'Workspaces'
    if (location.pathname === '/ops' && currentOpsView === 'templates') return 'Templates'
    if (location.pathname === '/ops' && currentOpsView === 'import') return 'Import'
    if (location.pathname === '/integrations') return 'Integrations'
    if (location.pathname === '/approvals') return 'Agent Approvals'
    if (location.pathname === '/history') return 'History'
    if (location.pathname === '/storage') return 'Storage'
    if (location.pathname === '/runbooks') return 'Runbooks'
    if (role === 'Developer')         return DEV_LABELS[currentDevView]  ?? 'Developer'
    if (role === 'DataEngineer')      return DATA_LABELS[currentDataView] ?? 'Data Engineer'
    if (role === 'DatabaseDeveloper') return DB_LABELS[currentDbView]     ?? 'Database'
    if (role === 'NetworkEngineer')   return opsBreadcrumb
    return opsBreadcrumb
  }

  const showOpsNav = role === 'Admin' || role === 'NetworkEngineer'
  const showOpsChrome = showOpsNav
  const opsToolId =
    showOpsNav && location.pathname === '/ops'
      ? OPS_HEADER_TOOL_BY_VIEW[currentOpsView] ?? null
      : null

  const breadcrumbLeft = (
    <>
      {roleInfo && (
        <>
          <span className={`text-xs font-semibold ${roleInfo.color}`}>{roleInfo.label}</span>
          <span className="text-slate-700">/</span>
        </>
      )}
      <span className="text-xs font-semibold text-white truncate">{breadcrumb()}</span>
    </>
  )

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-slate-200">

      {/* Left Sidebar */}
      <Sidebar
        activeView={activeViewId()}
        onNavigate={handleNav}
        role={role}
        showOpsNav={showOpsNav}
      />

      {/* Main column */}
      <div className="flex flex-col flex-1 overflow-hidden">
        {criticalHealthBanner && role === 'Admin' && (
          <div className="shrink-0 flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-red-950/80 border-b border-red-700/50 text-red-100 text-sm">
            <span>
              🚨 Critical system alert: {criticalHealthBanner}
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-semibold"
                onClick={openHealthDashboard}
              >
                View Health Dashboard
              </button>
              <button
                type="button"
                className="px-2 py-1 text-xs text-red-200/80 hover:text-white"
                onClick={() => setCriticalHealthBanner(null)}
                aria-label="Dismiss critical alert"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
        {healthWsToast && role === 'Admin' && (
          <div className="fixed bottom-6 right-6 z-[60] max-w-sm px-4 py-3 rounded-lg border border-amber-500/40 bg-amber-950/90 text-amber-100 text-sm shadow-xl">
            ⚠️ {healthWsToast}
          </div>
        )}

        <Header
          breadcrumbLeft={breadcrumbLeft}
          showOpsChrome={showOpsChrome}
          opsToolId={opsToolId}
          showHealthButton={role === 'Admin'}
          healthStatus={healthStatus}
          onOpenHealthDashboard={openHealthDashboard}
          onOpenSettings={() => setSettingsOpen(true)}
          onLogout={() => {
            logout()
            setCurrentOpsView('dashboard')
          }}
          onSelectIncident={(incidentId) => {
            authFetch(`/api/incidents`)
              .then((r) => r.json())
              .then((incidents) => {
                const found = incidents.find((i) => i.id === incidentId)
                if (found) {
                  navigate('/ops')
                  setCurrentOpsView('triage')
                }
              })
              .catch((err) => {
                console.error('Failed to navigate to incident:', err)
              })
          }}
        />

        {/* ── Portal routes ───────────────────────────────────────────────── */}
        <Routes>
          {/* Default redirect: go to the portal that matches the current role */}
          <Route
            path="/"
            element={<Navigate to={defaultPortalForRole(role)} replace />}
          />

          {/* Ops portal (Admin + NetworkEngineer) */}
          <Route
            path="/ops"
            element={
              <OpsPortal
                currentView={currentOpsView}
                onViewChange={setCurrentOpsView}
                onBreadcrumb={handleBreadcrumb}
              />
            }
          />

          {/* Developer portal */}
          <Route path="/developer" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <DeveloperPortal currentView={currentDevView} />
            </div>
          } />

          {/* Data Engineer portal */}
          <Route path="/data" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <DataEngineerPortal currentView={currentDataView} />
            </div>
          } />

          {/* Database Developer portal */}
          <Route path="/database" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <DatabasePortal currentView={currentDbView} />
            </div>
          } />

          <Route path="/approvals" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <AgentApprovalsWidget />
            </div>
          } />
          <Route path="/history" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <HistoryPanel />
            </div>
          } />
          <Route path="/integrations" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <IntegrationsPage />
            </div>
          } />
          <Route path="/system-health" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <HealthDashboard />
            </div>
          } />
          <Route path="/storage" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <StorageView />
            </div>
          } />
          <Route path="/runbooks" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <RunbooksView />
            </div>
          } />

          {/* Catch-all — redirect to role's default */}
          <Route path="*" element={<Navigate to={defaultPortalForRole(role)} replace />} />
        </Routes>
      </div>

      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
      <ChatBot />
    </div>
  )
}

// ── Root export ───────────────────────────────────────────────────────────────
export default function App() {
  return (
    <BrowserRouter>
      <RoleProvider>
        <AppLayout />
      </RoleProvider>
    </BrowserRouter>
  )
}
