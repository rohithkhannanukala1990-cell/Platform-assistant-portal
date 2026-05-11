/**
 * OpsPortal — the full AIOps operations view.
 * Wraps DashboardView, TriageView, InfraBuilderView, CICDView, HealthDashboard,
 * ToolRegistryView, and the universal HistoryPanel.
 */
import { useState, useEffect } from 'react'
import { Heart as HeartIcon, Puzzle as PuzzleIcon } from 'lucide-react'
import DashboardView from './DashboardView'
import TriageView from './TriageView'
import InfraBuilderView from './InfraBuilderView'
import CICDView from './CICDView'
import HistoryPanel from './HistoryPanel'
import IntegrationsPage from './IntegrationsPage'
import HealthDashboard from './HealthDashboard'
import ToolRegistryView from './ToolRegistryView'
import { useRole } from '../contexts/RoleContext'

const VIEW_LABELS = {
  dashboard: 'Dashboard',
  triage: 'Alert Triage',
  infra: 'Infra Builder',
  cicd: 'CI/CD Pipeline',
  integrations: 'Integrations',
  health: 'System Health',
  'tool-registry': 'Integrations',
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
]

export default function OpsPortal({ currentView, onViewChange, onBreadcrumb }) {
  const { role } = useRole()

  const [versions, setVersions] = useState({ alerts: 0, infra: 0, cicd: 0 })
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [selectedInfra, setSelectedInfra] = useState(null)
  const [selectedCICD, setSelectedCICD] = useState(null)

  function bumpVersion(tab) {
    setVersions((v) => ({ ...v, [tab]: v[tab] + 1 }))
  }

  function handleAnalysisComplete() {
    bumpVersion('alerts')
    setSelectedAlert(null)
  }
  function handleInfraComplete() {
    bumpVersion('infra')
    setSelectedInfra(null)
  }
  function handleCICDComplete() {
    bumpVersion('cicd')
    setSelectedCICD(null)
  }

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

  const detailLabel = (() => {
    if (currentView === 'triage' && selectedAlert) return `Incident #${selectedAlert.id}`
    if (currentView === 'infra' && selectedInfra) return `Infra Record #${selectedInfra.id}`
    if (currentView === 'cicd' && selectedCICD) return `Pipeline #${selectedCICD.id}`
    return VIEW_LABELS[currentView] ?? 'Dashboard'
  })()

  useEffect(() => {
    onBreadcrumb?.(detailLabel)
  }, [detailLabel, onBreadcrumb])

  const healthEntry = OPS_NAV_ITEMS.find((x) => x.id === 'health')
  const HealthCmp = healthEntry?.component ?? HealthDashboard
  const toolRegistryEntry = OPS_NAV_ITEMS.find((x) => x.id === 'tool-registry')
  const ToolRegistryCmp = toolRegistryEntry?.component ?? ToolRegistryView

  const showHistoryPanel =
    currentView !== 'dashboard' &&
    currentView !== 'integrations' &&
    currentView !== 'health' &&
    currentView !== 'tool-registry'

  return (
    <div className="flex flex-1 overflow-hidden">
      <main className="flex-1 overflow-y-auto px-8 py-8">
        {currentView === 'dashboard' && <DashboardView />}
        {currentView === 'triage' && (
          <TriageView
            selectedIncident={selectedAlert}
            onSelectIncident={setSelectedAlert}
            onAnalysisComplete={handleAnalysisComplete}
            roleFilter={role === 'Admin' ? null : role}
          />
        )}
        {currentView === 'infra' && (
          <InfraBuilderView
            selectedRecord={selectedInfra}
            onClearRecord={() => setSelectedInfra(null)}
            onGenerateComplete={handleInfraComplete}
          />
        )}
        {currentView === 'cicd' && (
          <CICDView
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
  )
}
