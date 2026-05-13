/**
 * OpsPortal — the full AIOps operations view.
 * Wraps DashboardView, TriageView, InfraBuilderView, CICDView, HealthDashboard,
 * ToolRegistryView, AccountImportView, WorkspaceBuilder, TemplateGallery, environment/account context, and the universal HistoryPanel.
 */
import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Heart as HeartIcon,
  Puzzle as PuzzleIcon,
  Upload as UploadIcon,
  Layers as LayersIcon,
  BookOpen as BookOpenIcon,
  Shield as ShieldIcon,
  Bot as BotIcon,
} from 'lucide-react'
import DashboardView from './DashboardView'
import TriageView from './TriageView'
import InfraBuilderView from './InfraBuilderView'
import CICDView from './CICDView'
import HistoryPanel from './HistoryPanel'
import IntegrationsPage from './IntegrationsPage'
import HealthDashboard from './HealthDashboard'
import ToolRegistryView from './ToolRegistryView'
import AccountImportView from './AccountImportView'
import WorkspaceBuilder from './WorkspaceBuilder'
import TemplateGallery from './TemplateGallery'
import RBACManager from './RBACManager'
import AIAssistant from './AIAssistant'
import { useToast } from './ToastNotification'
import { useRole } from '../contexts/RoleContext'
import { useAuth } from '../contexts/AuthContext'
import { setPortalContextHeaders } from '../utils/portalContextHeaders'
import { usePermissions } from '../hooks/usePermissions'

const VIEW_LABELS = {
  dashboard: 'Dashboard',
  triage: 'Alert Triage',
  infra: 'Infra Builder',
  cicd: 'CI/CD Pipeline',
  integrations: 'Integrations',
  health: 'System Health',
  'tool-registry': 'Integrations',
  workspaces: 'Workspaces',
  import: 'Import',
  templates: 'Templates',
  rbac: 'Access Control',
  'ai-assistant': 'AI Assistant',
}

/**
 * Ops module registry — Sidebar uses matching `id` values.
 * requiredPermission reserved for future RBAC (currently unused).
 */
export const OPS_NAV_ITEMS = [
  {
    id: 'health',
    label: 'Health',
    icon: HeartIcon,
    component: HealthDashboard,
    requiredPermission: 'settings',
    adminOnly: true,
  },
  {
    id: 'tool-registry',
    label: 'Integrations',
    icon: PuzzleIcon,
    component: ToolRegistryView,
    adminOnly: true,
  },
  {
    id: 'workspaces',
    label: 'Workspaces',
    icon: LayersIcon,
    component: WorkspaceBuilder,
    adminOnly: false,
  },
  {
    id: 'templates',
    label: 'Templates',
    icon: BookOpenIcon,
    component: TemplateGallery,
    adminOnly: true,
  },
  {
    id: 'rbac',
    label: 'Access Control',
    icon: ShieldIcon,
    component: RBACManager,
    adminOnly: true,
  },
  {
    id: 'ai-assistant',
    label: 'AI Assistant',
    icon: BotIcon,
    component: AIAssistant,
    adminOnly: false,
  },
  {
    id: 'import',
    label: 'Import',
    icon: UploadIcon,
    component: AccountImportView,
    adminOnly: true,
  },
]

function OpsPortalInner({ currentView, onViewChange, onBreadcrumb }) {
  const { role } = useRole()
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const { isAdmin } = usePermissions()
  const permAdmin = isAdmin()
  const visibleOpsNavItems = useMemo(
    () => OPS_NAV_ITEMS.filter((item) => !item.adminOnly || permAdmin),
    [permAdmin]
  )

  const [versions, setVersions] = useState({ alerts: 0, infra: 0, cicd: 0 })
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [selectedInfra, setSelectedInfra] = useState(null)
  const [selectedCICD, setSelectedCICD] = useState(null)

  const [showProductionBanner, setShowProductionBanner] = useState(false)
  const [activeContext, setActiveContext] = useState(null)
  const [activeEnvironment, setActiveEnvironment] = useState('development')

  const bumpVersion = useCallback((tab) => {
    setVersions((v) => ({ ...v, [tab]: v[tab] + 1 }))
  }, [])

  useEffect(() => {
    setPortalContextHeaders({
      activeEnvironment,
    })
  }, [activeEnvironment])

  const fetchContext = useCallback(async () => {
    try {
      const res = await authFetch('/api/context')
      if (!res.ok) return
      const ctx = await res.json()
      setActiveContext(ctx)
      const env = (ctx.active_environment || 'development').toLowerCase()
      setActiveEnvironment(env)
      setShowProductionBanner(env === 'production' || env === 'dr')
    } catch {
      /* noop */
    }
  }, [authFetch])

  const handleContextChange = useCallback(
    (event) => {
      const d = event.detail || {}
      const applyCtx = (ctx) => {
        if (!ctx) return
        setActiveContext(ctx)
        const env = (ctx.active_environment || 'development').toLowerCase()
        setActiveEnvironment(env)
        setShowProductionBanner(env === 'production' || env === 'dr')
      }
      if (d.context) {
        applyCtx(d.context)
      } else {
        void authFetch('/api/context').then(async (r) => {
          if (r.ok) applyCtx(await r.json())
        })
      }

      if (d.source !== 'account-pin' && d.source !== 'portal-context') {
        const envLabel = String(
          d.environment ?? d.context?.active_environment ?? 'development'
        ).toLowerCase()
        showToast(`✅ Switched to ${envLabel}`, 'success')
      }

      if (currentView === 'triage') bumpVersion('alerts')
      else if (currentView === 'infra') bumpVersion('infra')
      else if (currentView === 'cicd') bumpVersion('cicd')
    },
    [authFetch, showToast, currentView, bumpVersion]
  )

  useEffect(() => {
    void fetchContext()
    window.addEventListener('context-changed', handleContextChange)
    return () => window.removeEventListener('context-changed', handleContextChange)
  }, [fetchContext, handleContextChange])

  const handleAnalysisComplete = useCallback(() => {
    bumpVersion('alerts')
    setSelectedAlert(null)
  }, [bumpVersion])
  const handleInfraComplete = useCallback(() => {
    bumpVersion('infra')
    setSelectedInfra(null)
  }, [bumpVersion])
  const handleCICDComplete = useCallback(() => {
    bumpVersion('cicd')
    setSelectedCICD(null)
  }, [bumpVersion])

  function handleHistorySelect(tab, item) {
    if (tab === 'alerts') {
      setSelectedAlert(item)
      onViewChange('triage')
    } else if (tab === 'infra') {
      setSelectedInfra(item)
      onViewChange('infra')
    } else if (tab === 'cicd') {
      setSelectedCICD(item)
      onViewChange('cicd')
    }
  }

  const selectedIds = {
    alerts: selectedAlert?.id ?? null,
    infra: selectedInfra?.id ?? null,
    cicd: selectedCICD?.id ?? null,
  }

  const detailLabel = useMemo(() => {
    if (currentView === 'triage' && selectedAlert) return `Incident #${selectedAlert.id}`
    if (currentView === 'infra' && selectedInfra) return `Infra Record #${selectedInfra.id}`
    if (currentView === 'cicd' && selectedCICD) return `Pipeline #${selectedCICD.id}`
    return VIEW_LABELS[currentView] ?? 'Dashboard'
  }, [currentView, selectedAlert, selectedInfra, selectedCICD])

  useEffect(() => {
    onBreadcrumb?.(detailLabel)
  }, [detailLabel, onBreadcrumb])

  const healthEntry = visibleOpsNavItems.find((x) => x.id === 'health')
  const HealthCmp = healthEntry?.component ?? HealthDashboard
  const toolRegistryEntry = visibleOpsNavItems.find((x) => x.id === 'tool-registry')
  const ToolRegistryCmp = toolRegistryEntry?.component ?? ToolRegistryView
  const importEntry = visibleOpsNavItems.find((x) => x.id === 'import')
  const ImportCmp = importEntry?.component ?? AccountImportView
  const workspacesEntry = visibleOpsNavItems.find((x) => x.id === 'workspaces')
  const WorkspacesCmp = workspacesEntry?.component ?? WorkspaceBuilder
  const templatesEntry = visibleOpsNavItems.find((x) => x.id === 'templates')
  const TemplatesCmp = templatesEntry?.component ?? TemplateGallery
  const rbacEntry = visibleOpsNavItems.find((x) => x.id === 'rbac')
  const RBACCmp = rbacEntry?.component ?? RBACManager
  const aiAssistantEntry = visibleOpsNavItems.find((x) => x.id === 'ai-assistant')
  const AIAssistantCmp = aiAssistantEntry?.component ?? AIAssistant

  const showHistoryPanel =
    currentView !== 'dashboard' &&
    currentView !== 'integrations' &&
    currentView !== 'health' &&
    currentView !== 'tool-registry' &&
    currentView !== 'import' &&
    currentView !== 'workspaces' &&
    currentView !== 'templates' &&
    currentView !== 'rbac' &&
    currentView !== 'ai-assistant'

  const exitProduction = useCallback(async () => {
    try {
      const res = await authFetch('/api/context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_environment: 'staging' }),
      })
      if (!res.ok) return
      const data = await res.json()
      setActiveContext(data)
      setActiveEnvironment('staging')
      setShowProductionBanner(false)
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: { context: data, environment: 'staging', source: 'exit-production' },
        })
      )
    } catch {
      /* noop */
    }
  }, [authFetch])

  return (
    <div className="flex flex-1 flex-col min-h-0 overflow-hidden">
      {showProductionBanner && (
        <div className="sticky top-0 z-50 shrink-0 w-full bg-red-600 text-white shadow-md">
          <div className="flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 max-w-[1400px] mx-auto">
            <div className="flex items-center gap-3 min-w-0">
              <span className="text-xl shrink-0" aria-hidden>
                🚨
              </span>
              <div className="min-w-0">
                <p className="text-sm font-bold tracking-wide">PRODUCTION ENVIRONMENT</p>
                <p className="text-xs text-red-100/95">All actions require human approval (HITL)</p>
                <p className="text-xs text-red-100/90">This session is being audited</p>
                {activeContext?.user_id && (
                  <p className="text-[10px] text-red-100/80 mt-0.5">Context user: {activeContext.user_id}</p>
                )}
              </div>
            </div>
            <button
              type="button"
              onClick={() => void exitProduction()}
              className="shrink-0 px-3 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 text-xs font-semibold border border-white/30"
            >
              Exit Production
            </button>
          </div>
        </div>
      )}

      <div className="flex flex-1 overflow-hidden min-h-0">
        <main
          className={`flex-1 px-8 py-8 flex flex-col min-w-0 min-h-0 ${
            currentView === 'ai-assistant' ? 'overflow-hidden' : 'overflow-y-auto'
          }`}
        >
          {currentView === 'dashboard' && <DashboardView />}
          {currentView === 'triage' && (
            <TriageView
              key={versions.alerts}
              selectedIncident={selectedAlert}
              onSelectIncident={setSelectedAlert}
              onAnalysisComplete={handleAnalysisComplete}
              roleFilter={role === 'Admin' ? null : role}
            />
          )}
          {currentView === 'infra' && (
            <InfraBuilderView
              key={versions.infra}
              selectedRecord={selectedInfra}
              onClearRecord={() => setSelectedInfra(null)}
              onGenerateComplete={handleInfraComplete}
            />
          )}
          {currentView === 'cicd' && (
            <CICDView
              key={versions.cicd}
              selectedRecord={selectedCICD}
              onClearRecord={() => setSelectedCICD(null)}
              onGenerateComplete={handleCICDComplete}
            />
          )}
          {currentView === 'integrations' && <IntegrationsPage />}
          {currentView === 'health' && role === 'Admin' && (
            <div>
              {healthEntry?.icon
                ? (() => {
                    const Icon = healthEntry.icon
                    return (
                      <div className="flex items-center gap-2 mb-4 text-slate-400">
                        <Icon className="w-5 h-5 text-rose-400" aria-hidden />
                        <span className="text-xs font-medium uppercase tracking-wider">Health module</span>
                      </div>
                    )
                  })()
                : null}
              <HealthCmp />
            </div>
          )}
          {currentView === 'tool-registry' && role === 'Admin' && (
            <div>
              {toolRegistryEntry?.icon
                ? (() => {
                    const Icon = toolRegistryEntry.icon
                    return (
                      <div className="flex items-center gap-2 mb-4 text-slate-400">
                        <Icon className="w-5 h-5 text-violet-400" aria-hidden />
                        <span className="text-xs font-medium uppercase tracking-wider">Integrations</span>
                      </div>
                    )
                  })()
                : null}
              <ToolRegistryCmp />
            </div>
          )}
          {currentView === 'workspaces' && (
            <div>
              {workspacesEntry?.icon
                ? (() => {
                    const Icon = workspacesEntry.icon
                    return (
                      <div className="flex items-center gap-2 mb-4 text-slate-400">
                        <Icon className="w-5 h-5 text-indigo-400" aria-hidden />
                        <span className="text-xs font-medium uppercase tracking-wider">Workspaces</span>
                      </div>
                    )
                  })()
                : null}
              <WorkspacesCmp />
            </div>
          )}
          {currentView === 'templates' && (
            <div>
              {role === 'Admin' ? (
                <>
                  {templatesEntry?.icon
                    ? (() => {
                        const Icon = templatesEntry.icon
                        return (
                          <div className="flex items-center gap-2 mb-4 text-slate-400">
                            <Icon className="w-5 h-5 text-indigo-400" aria-hidden />
                            <span className="text-xs font-medium uppercase tracking-wider">Templates</span>
                          </div>
                        )
                      })()
                    : null}
                  <TemplatesCmp />
                </>
              ) : (
                <p className="text-slate-400 text-sm">Templates are available to administrators only.</p>
              )}
            </div>
          )}
          {currentView === 'rbac' && (
            <div>
              {role === 'Admin' ? (
                <>
                  {rbacEntry?.icon
                    ? (() => {
                        const Icon = rbacEntry.icon
                        return (
                          <div className="flex items-center gap-2 mb-4 text-slate-400">
                            <Icon className="w-5 h-5 text-emerald-400" aria-hidden />
                            <span className="text-xs font-medium uppercase tracking-wider">Access Control</span>
                          </div>
                        )
                      })()
                    : null}
                  <RBACCmp />
                </>
              ) : (
                <p className="text-slate-400 text-sm">Access Control is available to administrators only.</p>
              )}
            </div>
          )}
          {currentView === 'ai-assistant' && (
            <div className="flex flex-col flex-1 min-h-0 min-w-0">
              {aiAssistantEntry?.icon
                ? (() => {
                    const Icon = aiAssistantEntry.icon
                    return (
                      <div className="flex items-center gap-2 mb-4 text-slate-400 shrink-0">
                        <Icon className="w-5 h-5 text-blue-400" aria-hidden />
                        <span className="text-xs font-medium uppercase tracking-wider">AI Assistant</span>
                      </div>
                    )
                  })()
                : null}
              <AIAssistantCmp />
            </div>
          )}
          {currentView === 'import' && role === 'Admin' && (
            <div>
              {importEntry?.icon
                ? (() => {
                    const Icon = importEntry.icon
                    return (
                      <div className="flex items-center gap-2 mb-4 text-slate-400">
                        <Icon className="w-5 h-5 text-sky-400" aria-hidden />
                        <span className="text-xs font-medium uppercase tracking-wider">Import</span>
                      </div>
                    )
                  })()
                : null}
              <ImportCmp />
            </div>
          )}
        </main>

        {showHistoryPanel && (
          <HistoryPanel
            versions={versions}
            onSelect={handleHistorySelect}
            selectedIds={selectedIds}
            activeView={currentView}
            roleFilter={role === 'Admin' ? null : role}
          />
        )}
      </div>
    </div>
  )
}

export default function OpsPortal(props) {
  return <OpsPortalInner {...props} />
}
