import { useState, useCallback, useEffect, lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom'
import { Loader2 } from 'lucide-react'

import { useAuth } from './contexts/AuthContext'
import Layout from './components/Layout'
import LoginPage from './components/LoginPage'
import AuthCallback from './components/AuthCallback'
import PermissionGate from './components/PermissionGate'
import SettingsModal from './components/SettingsModal'

const AdminDashboard = lazy(() => import('./components/admin/AdminDashboard'))
const CatalogPage = lazy(() => import('./components/CatalogPage'))
const DependencyGraph = lazy(() => import('./components/DependencyGraph'))
const StandardsPage = lazy(() => import('./components/StandardsPage'))
const EntityActionsPage = lazy(() => import('./components/EntityActionsPage'))
const GoldenPathsPage = lazy(() => import('./components/GoldenPathsPage'))
const ReportsPage = lazy(() => import('./components/ReportsPage'))
const ScorecardsPage = lazy(() => import('./components/ScorecardsPage'))
const DashboardView = lazy(() => import('./components/DashboardView'))
const TriageView = lazy(() => import('./components/TriageView'))
const IncidentCommandCenter = lazy(() => import('./components/IncidentCommandCenter'))
const InfraBuilderView = lazy(() => import('./components/InfraBuilderView'))
const CICDView = lazy(() => import('./components/CICDView'))
const IntegrationsPage = lazy(() => import('./components/IntegrationsPage'))
const ToolRegistryView = lazy(() => import('./components/ToolRegistryView'))
const RBACManager = lazy(() => import('./components/RBACManager'))
const AIAssistant = lazy(() => import('./components/AIAssistant'))
const HealthDashboard = lazy(() => import('./components/HealthDashboard'))
const AgentApprovalsWidget = lazy(() => import('./components/AgentApprovalsWidget'))
const AgentRunnerPanel = lazy(() => import('./components/AgentRunnerPanel'))
const CodeEditor = lazy(() => import('./components/CodeEditor'))
const Terminal = lazy(() => import('./components/Terminal'))
const QueryAnalyzerView = lazy(() => import('./components/QueryAnalyzerView'))
const OpsPortal = lazy(() => import('./components/OpsPortal'))
const DeveloperPortal = lazy(() => import('./components/DeveloperPortal'))
const DataEngineerPortal = lazy(() => import('./components/DataEngineerPortal'))
const DatabasePortal = lazy(() => import('./components/DatabasePortal'))
const HistoryPanel = lazy(() => import('./components/HistoryPanel'))
const StorageView = lazy(() => import('./components/StorageView'))
const RunbooksView = lazy(() => import('./components/RunbooksView'))
const WorkspaceBuilder = lazy(() => import('./components/WorkspaceBuilder'))
const TemplateGallery = lazy(() => import('./components/TemplateGallery'))
const AccountImportView = lazy(() => import('./components/AccountImportView'))
const DeploymentsView = lazy(() => import('./components/DeploymentsView'))
const DORAPage = lazy(() => import('./components/DORAPage'))
const LivePipelinesView = lazy(() => import('./components/LivePipelinesView'))
const GitHubPRsView = lazy(() => import('./components/GitHubPRsView'))
const GitHubActionsView = lazy(() => import('./components/GitHubActionsView'))
const K8sResourcesView = lazy(() => import('./components/K8sResourcesView'))
const PagerDutyView = lazy(() => import('./components/PagerDutyView'))
const SlackView = lazy(() => import('./components/SlackView'))
const PrometheusView = lazy(() => import('./components/PrometheusView'))
const ArgoCDView = lazy(() => import('./components/ArgoCDView'))
const OutboundWebhookView = lazy(() => import('./components/OutboundWebhookView'))
const SchemaBrowserView = lazy(() => import('./components/SchemaBrowserView'))
const DataLineageView = lazy(() => import('./components/DataLineageView'))
const NotificationsPage = lazy(() => import('./components/NotificationsPage'))

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

function PageLoader() {
  return (
    <div className="flex h-64 items-center justify-center gap-2 text-slate-500">
      <Loader2 className="animate-spin" size={20} aria-hidden />
      <span>Loading…</span>
    </div>
  )
}

function PrivateRoute({ children, adminOnly = false }) {
  const { isAuthenticated, loading, role } = useAuth()
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

  if (adminOnly && role !== 'Admin') {
    return <Navigate to="/dashboard" replace />
  }

  return children
}

function SettingsPage() {
  return <SettingsModal onClose={() => window.history.back()} />
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
    <Suspense fallback={<PageLoader />}>
      <Routes>
        <Route
          path="/login"
          element={isAuthenticated ? <Navigate to="/dashboard" replace /> : <LoginPage />}
        />
        <Route path="/auth/callback" element={<AuthCallback />} />

        <Route
          path="/admin"
          element={(
            <PrivateRoute adminOnly>
              <AdminDashboard />
            </PrivateRoute>
          )}
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
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<PrivateRoute><DashboardView /></PrivateRoute>} />

          <Route path="/catalog" element={<PrivateRoute><CatalogPage /></PrivateRoute>} />
          <Route path="/scorecards" element={<PrivateRoute><ScorecardsPage /></PrivateRoute>} />
          <Route path="/dependency-graph" element={<PrivateRoute><DependencyGraph /></PrivateRoute>} />
          <Route path="/standards" element={<PrivateRoute><StandardsPage /></PrivateRoute>} />
          <Route path="/entity-actions" element={<PrivateRoute><EntityActionsPage /></PrivateRoute>} />
          <Route path="/golden-paths" element={<PrivateRoute><GoldenPathsPage /></PrivateRoute>} />
          <Route path="/reports" element={<PrivateRoute><ReportsPage /></PrivateRoute>} />

          <Route path="/ai-assistant" element={<PrivateRoute><AIAssistant /></PrivateRoute>} />
          <Route path="/integrations" element={<PrivateRoute><IntegrationsPage /></PrivateRoute>} />
          <Route path="/webhooks" element={<PrivateRoute><IntegrationsPage /></PrivateRoute>} />
          <Route
            path="/rbac"
            element={(
              <PrivateRoute>
                <PermissionGate requiredRole="Admin" showFallback>
                  <RBACManager />
                </PermissionGate>
              </PrivateRoute>
            )}
          />
          <Route
            path="/tools"
            element={(
              <PrivateRoute>
                <PermissionGate requiredRole="Admin" showFallback>
                  <ToolRegistryView />
                </PermissionGate>
              </PrivateRoute>
            )}
          />
          <Route
            path="/tool-registry"
            element={(
              <PrivateRoute>
                <PermissionGate requiredRole="Admin" showFallback>
                  <ToolRegistryView />
                </PermissionGate>
              </PrivateRoute>
            )}
          />
          <Route path="/workspaces" element={<PrivateRoute><WorkspaceBuilder /></PrivateRoute>} />
          <Route path="/cicd" element={<PrivateRoute><CICDView /></PrivateRoute>} />
          <Route path="/github/prs" element={<PrivateRoute><GitHubPRsView /></PrivateRoute>} />
          <Route path="/github/actions" element={<PrivateRoute><GitHubActionsView /></PrivateRoute>} />
          <Route path="/k8s" element={<PrivateRoute><K8sResourcesView /></PrivateRoute>} />
          <Route path="/pagerduty" element={<PrivateRoute><PagerDutyView /></PrivateRoute>} />
          <Route path="/slack" element={<PrivateRoute><SlackView /></PrivateRoute>} />
          <Route path="/prometheus" element={<PrivateRoute><PrometheusView /></PrivateRoute>} />
          <Route path="/argocd" element={<PrivateRoute><ArgoCDView /></PrivateRoute>} />
          <Route path="/outbound-webhook" element={<PrivateRoute><OutboundWebhookView /></PrivateRoute>} />
          <Route path="/live-pipelines" element={<PrivateRoute><LivePipelinesView /></PrivateRoute>} />
          <Route path="/deployments" element={<PrivateRoute><DeploymentsView /></PrivateRoute>} />
          <Route path="/schema-browser" element={<PrivateRoute><SchemaBrowserView /></PrivateRoute>} />
          <Route path="/data-lineage" element={<PrivateRoute><DataLineageView /></PrivateRoute>} />

          <Route path="/incidents" element={<PrivateRoute><TriageView /></PrivateRoute>} />
          <Route path="/incidents/:id" element={<PrivateRoute><IncidentCommandCenter /></PrivateRoute>} />
          <Route path="/alerts" element={<PrivateRoute><TriageView /></PrivateRoute>} />
          <Route path="/dora" element={<PrivateRoute><DORAPage /></PrivateRoute>} />
          <Route path="/infra" element={<PrivateRoute><InfraBuilderView /></PrivateRoute>} />
          <Route path="/settings" element={<PrivateRoute><SettingsPage /></PrivateRoute>} />
          <Route path="/health" element={<PrivateRoute><HealthDashboard /></PrivateRoute>} />
          <Route path="/agents" element={<PrivateRoute><AgentRunnerPanel /></PrivateRoute>} />
          <Route path="/agent-history" element={<PrivateRoute><AgentRunnerPanel /></PrivateRoute>} />
          <Route path="/editor" element={<PrivateRoute><CodeEditor /></PrivateRoute>} />
          <Route path="/terminal" element={<PrivateRoute><Terminal /></PrivateRoute>} />
          <Route path="/approvals" element={<PrivateRoute><AgentApprovalsWidget /></PrivateRoute>} />
          <Route path="/db-analyzer" element={<PrivateRoute><QueryAnalyzerView /></PrivateRoute>} />
          <Route path="/query-analyzer" element={<PrivateRoute><QueryAnalyzerView /></PrivateRoute>} />

          {/* Legacy / role portals — preserved */}
          <Route path="/ops" element={<PrivateRoute><OpsPortalRoute /></PrivateRoute>} />
          <Route path="/developer" element={<PrivateRoute><DeveloperPortalRoute /></PrivateRoute>} />
          <Route path="/data" element={<PrivateRoute><DataEngineerPortal currentView="pipelines" /></PrivateRoute>} />
          <Route path="/database" element={<PrivateRoute><DatabasePortal currentView="dbhealth" /></PrivateRoute>} />
          <Route path="/history" element={<PrivateRoute><HistoryPanel /></PrivateRoute>} />
          <Route path="/system-health" element={<Navigate to="/health" replace />} />
          <Route path="/storage" element={<PrivateRoute><StorageView /></PrivateRoute>} />
          <Route path="/runbooks" element={<PrivateRoute><RunbooksView /></PrivateRoute>} />
          <Route path="/templates" element={<PrivateRoute><TemplateGallery /></PrivateRoute>} />
          <Route path="/template-gallery" element={<PrivateRoute><TemplateGallery /></PrivateRoute>} />
          <Route
            path="/import"
            element={(
              <PrivateRoute>
                <PermissionGate requiredRole="Admin" showFallback>
                  <AccountImportView />
                </PermissionGate>
              </PrivateRoute>
            )}
          />
          <Route
            path="/account-import"
            element={(
              <PrivateRoute>
                <PermissionGate requiredRole="Admin" showFallback>
                  <AccountImportView />
                </PermissionGate>
              </PrivateRoute>
            )}
          />
          <Route path="/notifications" element={<PrivateRoute><NotificationsPage /></PrivateRoute>} />

          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Route>
      </Routes>
    </Suspense>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthenticatedRoutes />
    </BrowserRouter>
  )
}
