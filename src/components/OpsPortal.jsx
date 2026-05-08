/**
 * OpsPortal — the full AIOps operations view.
 * Wraps DashboardView, TriageView, InfraBuilderView, CICDView, and the
 * universal HistoryPanel inside the same state-based navigation that was
 * previously embedded directly in App.jsx.  Extracted here so React Router
 * can mount it at /ops while keeping the sub-navigation state local.
 */
import { useState } from 'react'
import DashboardView    from './DashboardView'
import TriageView       from './TriageView'
import InfraBuilderView from './InfraBuilderView'
import CICDView         from './CICDView'
import HistoryPanel     from './HistoryPanel'
import IntegrationsPage from './IntegrationsPage'
import { useRole }      from '../contexts/RoleContext'

const VIEW_LABELS = {
  dashboard:    'Dashboard',
  triage:       'Alert Triage',
  infra:        'Infra Builder',
  cicd:         'CI/CD Pipeline',
  integrations: 'Integrations',
}

export default function OpsPortal({ currentView, onViewChange, onBreadcrumb }) {
  const { role } = useRole()

  // Per-module version counters
  const [versions, setVersions]         = useState({ alerts: 0, infra: 0, cicd: 0 })
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [selectedInfra, setSelectedInfra] = useState(null)
  const [selectedCICD,  setSelectedCICD]  = useState(null)

  function bumpVersion(tab) { setVersions((v) => ({ ...v, [tab]: v[tab] + 1 })) }

  function handleAnalysisComplete() { bumpVersion('alerts'); setSelectedAlert(null) }
  function handleInfraComplete()    { bumpVersion('infra');  setSelectedInfra(null) }
  function handleCICDComplete()     { bumpVersion('cicd');   setSelectedCICD(null)  }

  function handleHistorySelect(tab, item) {
    if (tab === 'alerts')      { setSelectedAlert(item); onViewChange('triage') }
    else if (tab === 'infra')  { setSelectedInfra(item); onViewChange('infra') }
    else if (tab === 'cicd')   { setSelectedCICD(item);  onViewChange('cicd') }
  }

  const selectedIds = {
    alerts: selectedAlert?.id ?? null,
    infra:  selectedInfra?.id  ?? null,
    cicd:   selectedCICD?.id   ?? null,
  }

  // Expose the current detail breadcrumb label to parent
  const detailLabel = (() => {
    if (currentView === 'triage' && selectedAlert) return `Incident #${selectedAlert.id}`
    if (currentView === 'infra'  && selectedInfra) return `Infra Record #${selectedInfra.id}`
    if (currentView === 'cicd'   && selectedCICD)  return `Pipeline #${selectedCICD.id}`
    return VIEW_LABELS[currentView] ?? 'Dashboard'
  })()

  // Sync breadcrumb label upward so the navbar can show it
  if (onBreadcrumb) onBreadcrumb(detailLabel)

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
      </main>

      {currentView !== 'dashboard' && currentView !== 'integrations' && (
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
