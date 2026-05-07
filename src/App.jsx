import { useState } from 'react'
import { Settings, UserCircle2 } from 'lucide-react'
import Sidebar from './components/Sidebar'
import DashboardView from './components/DashboardView'
import TriageView from './components/TriageView'
import InfraBuilderView from './components/InfraBuilderView'
import CICDView from './components/CICDView'
import HistoryPanel from './components/HistoryPanel'
import SettingsModal from './components/SettingsModal'
import NotificationDropdown from './components/NotificationDropdown'

const VIEW_LABELS = {
  dashboard: 'Dashboard',
  triage:    'Alert Triage',
  infra:     'Infra Builder',
  cicd:      'CI/CD Pipeline',
}

export default function App() {
  const [currentView, setCurrentView] = useState('dashboard')

  // Per-module version counters — bump to tell HistoryPanel to refresh that tab
  const [versions, setVersions] = useState({ alerts: 0, infra: 0, cicd: 0 })

  // Per-module selected history records
  const [selectedAlert, setSelectedAlert] = useState(null)
  const [selectedInfra, setSelectedInfra]  = useState(null)
  const [selectedCICD, setSelectedCICD]    = useState(null)

  // Settings modal
  const [settingsOpen, setSettingsOpen] = useState(false)

  // ── Helpers ───────────────────────────────────────────────────────────────

  function bumpVersion(tab) {
    setVersions((v) => ({ ...v, [tab]: v[tab] + 1 }))
  }

  function handleNavigate(view) {
    setCurrentView(view)
  }

  // Called by TriageView when a new analysis completes
  function handleAnalysisComplete() {
    bumpVersion('alerts')
    setSelectedAlert(null)
  }

  // Called by InfraBuilderView when generation completes
  function handleInfraComplete() {
    bumpVersion('infra')
    setSelectedInfra(null)
  }

  // Called by CICDView when generation completes
  function handleCICDComplete() {
    bumpVersion('cicd')
    setSelectedCICD(null)
  }

  // Called by HistoryPanel when the user clicks any history item
  function handleHistorySelect(tab, item) {
    if (tab === 'alerts') {
      setSelectedAlert(item)
      setCurrentView('triage')
    } else if (tab === 'infra') {
      setSelectedInfra(item)
      setCurrentView('infra')
    } else if (tab === 'cicd') {
      setSelectedCICD(item)
      setCurrentView('cicd')
    }
  }

  // Build the breadcrumb label
  function breadcrumb() {
    if (currentView === 'triage' && selectedAlert)
      return `Incident #${selectedAlert.id}`
    if (currentView === 'infra' && selectedInfra)
      return `Infra Record #${selectedInfra.id}`
    if (currentView === 'cicd' && selectedCICD)
      return `Pipeline #${selectedCICD.id}`
    return VIEW_LABELS[currentView]
  }

  const selectedIds = {
    alerts: selectedAlert?.id ?? null,
    infra:  selectedInfra?.id  ?? null,
    cicd:   selectedCICD?.id   ?? null,
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface text-slate-200">
      {/* Left Sidebar */}
      <Sidebar activeView={currentView} onNavigate={handleNavigate} />

      {/* Main Column */}
      <div className="flex flex-col flex-1 overflow-hidden">

        {/* Top Header Bar */}
        <header className="flex items-center justify-between px-6 py-3.5 border-b border-border bg-sidebar shrink-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-slate-500">Platform Engineering</span>
            <span className="text-slate-700">/</span>
            <span className="text-xs font-semibold text-white">{breadcrumb()}</span>
          </div>

          <div className="flex items-center gap-3">
            <NotificationDropdown
              onSelectIncident={(incidentId) => {
                // Find the incident in history and navigate to it
                fetch(`http://127.0.0.1:8000/api/incidents`)
                  .then((r) => r.json())
                  .then((incidents) => {
                    const found = incidents.find((i) => i.id === incidentId)
                    if (found) { setSelectedAlert(found); setCurrentView('triage') }
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
            <div className="flex items-center gap-2 pl-2 border-l border-border">
              <div className="flex items-center justify-center w-7 h-7 rounded-full bg-accent/20 border border-accent/30">
                <UserCircle2 className="w-4 h-4 text-accent" />
              </div>
              <span className="text-xs font-medium text-slate-300">Ops Engineer</span>
            </div>
          </div>
        </header>

        {/* Content Row */}
        <div className="flex flex-1 overflow-hidden">
          <main className="flex-1 overflow-y-auto px-8 py-8">
            {currentView === 'dashboard' && (
              <DashboardView />
            )}
            {currentView === 'triage' && (
              <TriageView
                selectedIncident={selectedAlert}
                onSelectIncident={setSelectedAlert}
                onAnalysisComplete={handleAnalysisComplete}
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
          </main>

          {/* Universal History Panel — hidden on dashboard */}
          {currentView !== 'dashboard' && (
            <HistoryPanel
              versions={versions}
              onSelect={handleHistorySelect}
              selectedIds={selectedIds}
              activeView={currentView}
            />
          )}
        </div>
      </div>

      {/* Settings Modal */}
      {settingsOpen && <SettingsModal onClose={() => setSettingsOpen(false)} />}
    </div>
  )
}
