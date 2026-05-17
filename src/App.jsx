import { useState, useCallback, useEffect } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { RoleProvider } from './contexts/RoleContext'
import { useAuth } from './contexts/AuthContext'

import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import CatalogPage from './components/CatalogPage'
import DependencyGraph from './components/DependencyGraph'
import StandardsPage from './components/StandardsPage'
import EntityActionsPage from './components/EntityActionsPage'
import GoldenPathsPage from './components/GoldenPathsPage'
import DashboardView from './components/DashboardView'
import TriageView from './components/TriageView'
import InfraBuilderView from './components/InfraBuilderView'
import CICDView from './components/CICDView'
import IntegrationsPage from './components/IntegrationsPage'
import ToolRegistryView from './components/ToolRegistryView'
import SettingsModal from './components/SettingsModal'
import RBACManager from './components/RBACManager'
import AIAssistant from './components/AIAssistant'
import HealthDashboard from './components/HealthDashboard'
import AgentApprovalsWidget from './components/AgentApprovalsWidget'
import QueryAnalyzerView from './components/QueryAnalyzerView'
import OpsPortal from './components/OpsPortal'
import DeveloperPortal from './components/DeveloperPortal'
import DataEngineerPortal from './components/DataEngineerPortal'
import DatabasePortal from './components/DatabasePortal'
import HistoryPanel from './components/HistoryPanel'
import StorageView from './components/StorageView'
import RunbooksView from './components/RunbooksView'
import WorkspaceBuilder from './components/WorkspaceBuilder'
import TemplateGallery from './components/TemplateGallery'
import AccountImportView from './components/AccountImportView'

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
  'rbac',
  'ai-assistant',
  'import',
])

function PrivateRoute({ children }) {
  const { isAuthenticated, loading } = useAuth()
  const location = useLocation()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[40vh]">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
      </div>
    )
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }

  return children
}

function SettingsPage() {
  const location = useLocation()
  return <SettingsModal onClose={() => window.history.back()} key={location.key} />
}

function OpsPortalRoute() {
  const location = useLocation()
  const [currentView, setCurrentView] = useState('dashboard')
  useEffect(() => {
    const v = new URLSearchParams(location.search).get('view')
    if (v && OPS_URL_VIEWS.has(v)) setCurrentView(v)
  }, [location.pathname, location.search])

  const handleBreadcrumb = useCallback(() => {}, [])

  return (
    <OpsPortal
      currentView={currentView}
      onViewChange={setCurrentView}
      onBreadcrumb={handleBreadcrumb}
    />
  )
}

function DeveloperPortalRoute() {
  const location = useLocation()
  const [currentView, setCurrentView] = useState('catalog')

  useEffect(() => {
    const search = location.state?.catalogSearch
    if (search) setCurrentView('catalog')
  }, [location.state])

  return <DeveloperPortal currentView={currentView} />
}

function AuthenticatedRoutes() {
  const { user, logout, isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-neutral-950">
        <Loader2 className="w-8 h-8 animate-spin text-indigo-400" />
      </div>
    )
  }

  return (
    <Routes>
      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />

      <Route
        element={
          isAuthenticated ? (
            <Layout user={user} onLogout={logout} />
          ) : (
            <Navigate to="/login" replace />
          )
        }
      >
        <Route path="/" element={<PrivateRoute><DashboardView /></PrivateRoute>} />
        <Route path="/incidents" element={<PrivateRoute><TriageView /></PrivateRoute>} />
        <Route path="/infra" element={<PrivateRoute><InfraBuilderView /></PrivateRoute>} />
        <Route path="/cicd" element={<PrivateRoute><CICDView /></PrivateRoute>} />
        <Route path="/webhooks" element={<PrivateRoute><IntegrationsPage /></PrivateRoute>} />
        <Route path="/tools" element={<PrivateRoute><ToolRegistryView /></PrivateRoute>} />
        <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
        <Route path="/rbac" element={<PrivateRoute><RBACManager /></PrivateRoute>} />
        <Route path="/ai-assistant" element={<PrivateRoute><AIAssistant /></PrivateRoute>} />
        <Route path="/health" element={<PrivateRoute><HealthDashboard /></PrivateRoute>} />
        <Route path="/approvals" element={<PrivateRoute><AgentApprovalsWidget /></PrivateRoute>} />
        <Route path="/db-analyzer" element={<PrivateRoute><QueryAnalyzerView /></PrivateRoute>} />
        <Route path="/catalog" element={<PrivateRoute><CatalogPage /></PrivateRoute>} />
        <Route path="/standards" element={<PrivateRoute><StandardsPage /></PrivateRoute>} />
        <Route path="/entity-actions" element={<PrivateRoute><EntityActionsPage /></PrivateRoute>} />
        <Route path="/golden-paths" element={<PrivateRoute><GoldenPathsPage /></PrivateRoute>} />
        <Route path="/dependency-graph" element={<PrivateRoute><DependencyGraph /></PrivateRoute>} />

        {/* Legacy / role portals — preserved */}
        <Route path="/ops" element={<PrivateRoute><OpsPortalRoute /></PrivateRoute>} />
        <Route path="/developer" element={<PrivateRoute><DeveloperPortalRoute /></PrivateRoute>} />
        <Route path="/data" element={<PrivateRoute><DataEngineerPortal currentView="pipelines" /></PrivateRoute>} />
        <Route path="/database" element={<PrivateRoute><DatabasePortal currentView="dbhealth" /></PrivateRoute>} />
        <Route path="/history" element={<PrivateRoute><HistoryPanel /></PrivateRoute>} />
        <Route path="/integrations" element={<PrivateRoute><IntegrationsPage /></PrivateRoute>} />
        <Route path="/system-health" element={<Navigate to="/health" replace />} />
        <Route path="/storage" element={<PrivateRoute><StorageView /></PrivateRoute>} />
        <Route path="/runbooks" element={<PrivateRoute><RunbooksView /></PrivateRoute>} />
        <Route path="/workspaces" element={<PrivateRoute><WorkspaceBuilder /></PrivateRoute>} />
        <Route path="/templates" element={<PrivateRoute><TemplateGallery /></PrivateRoute>} />
        <Route path="/import" element={<PrivateRoute><AccountImportView /></PrivateRoute>} />
        <Route path="/notifications" element={<PrivateRoute><HistoryPanel /></PrivateRoute>} />

        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <RoleProvider>
        <AuthenticatedRoutes />
      </RoleProvider>
    </BrowserRouter>
  )
}
