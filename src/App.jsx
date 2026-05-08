import { useState, useRef, useCallback } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Settings } from 'lucide-react'

import { RoleProvider, useRole, ROLES } from './contexts/RoleContext'

import Sidebar              from './components/Sidebar'
import OpsPortal            from './components/OpsPortal'
import DeveloperPortal      from './components/DeveloperPortal'
import DataEngineerPortal   from './components/DataEngineerPortal'
import DatabasePortal       from './components/DatabasePortal'
import SettingsModal        from './components/SettingsModal'
import NotificationDropdown from './components/NotificationDropdown'
import ChatBot              from './components/ChatBot'
import UserMenu             from './components/UserMenu'
import PersonaSwitcher      from './components/PersonaSwitcher'

// ── Ops sub-view labels ───────────────────────────────────────────────────────
const OPS_VIEW_LABELS = {
  dashboard: 'Dashboard',
  triage:    'Alert Triage',
  infra:     'Infra Builder',
  cicd:      'CI/CD Pipeline',
}

// ── Per-role default portal path ──────────────────────────────────────────────
function defaultPortalForRole(role) {
  return ROLES[role]?.portal ?? '/ops'
}

// ── Inner layout (needs router context via useRole / useNavigate) ─────────────
function AppLayout() {
  const { role, setRole, roleInfo } = useRole()

  const [currentOpsView, setCurrentOpsView] = useState('dashboard')
  const [opsBreadcrumb,  setOpsBreadcrumb]  = useState('Dashboard')
  const [settingsOpen,   setSettingsOpen]   = useState(false)
  const [isLoggedIn,     setIsLoggedIn]     = useState(true)

  // stable callback so OpsPortal doesn't re-render on every breadcrumb update
  const handleBreadcrumb = useCallback((label) => {
    setOpsBreadcrumb((prev) => (prev === label ? prev : label))
  }, [])

  // Dynamic breadcrumb depending on which portal is active
  function breadcrumb() {
    if (role === 'Developer')       return 'Software Catalog'
    if (role === 'DataEngineer')    return 'Pipeline Health'
    if (role === 'NetworkEngineer') return opsBreadcrumb
    return opsBreadcrumb   // Admin
  }

  // Nav items are portal-specific; only show for roles that use OpsPortal
  const showOpsNav = role === 'Admin' || role === 'NetworkEngineer'

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-slate-200">

      {/* Left Sidebar */}
      <Sidebar
        activeView={currentOpsView}
        onNavigate={setCurrentOpsView}
        role={role}
        showOpsNav={showOpsNav}
      />

      {/* Main column */}
      <div className="flex flex-col flex-1 overflow-hidden">

        {/* ── Top Header ─────────────────────────────────────────────────── */}
        <header className="flex items-center justify-between px-6 py-3.5 border-b border-border bg-sidebar shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Platform Engineering</span>
            <span className="text-slate-700">/</span>
            <span className={`text-xs font-semibold ${roleInfo.color}`}>{roleInfo.label}</span>
            <span className="text-slate-700">/</span>
            <span className="text-xs font-semibold text-white">{breadcrumb()}</span>
          </div>

          <div className="flex items-center gap-3">
            {/* Persona switcher — visible to all (Admin can switch, others see read-only) */}
            <PersonaSwitcher />

            <NotificationDropdown
              onSelectIncident={(incidentId) => {
                fetch('http://127.0.0.1:8000/api/incidents')
                  .then((r) => r.json())
                  .then((incidents) => {
                    const found = incidents.find((i) => i.id === incidentId)
                    if (found) { setCurrentOpsView('triage') }
                  })
                  .catch(() => {})
              }}
            />

            <button
              onClick={() => setSettingsOpen(true)}
              className="p-2 rounded-lg hover:bg-card transition-colors group"
              title="Settings"
            >
              <Settings className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" />
            </button>

            <UserMenu
              isLoggedIn={isLoggedIn}
              onLogin={() => setIsLoggedIn(true)}
              onLogout={() => { setIsLoggedIn(false); setCurrentOpsView('dashboard') }}
              onOpenSettings={() => setSettingsOpen(true)}
            />
          </div>
        </header>

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
              <DeveloperPortal />
            </div>
          } />

          {/* Data Engineer portal */}
          <Route path="/data" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <DataEngineerPortal />
            </div>
          } />

          {/* Database Developer portal */}
          <Route path="/database" element={
            <div className="flex-1 overflow-y-auto px-8 py-8">
              <DatabasePortal />
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
