import { useState, useEffect, useCallback } from 'react'
import {
  ScanSearch,
  Sparkles,
  ClipboardPaste,
  ChevronDown,
  Terminal,
  AlertOctagon,
  ArrowLeft,
} from 'lucide-react'
import IncidentReportCard from './IncidentReportCard'
import IncidentHistory from './IncidentHistory'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'

const TRIAGE_TABS = [
  { id: 'logs', label: 'Log Triage' },
  { id: 'noise', label: 'Noise Analysis' },
]

const ACTIVE_STATUSES = new Set(['OPEN', 'AWAITING_APPROVAL', 'open', 'awaiting_approval'])

function EmptyState({ icon, title }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <span className="text-5xl mb-4">{icon}</span>
      <p className="text-base font-medium text-gray-300">{title}</p>
    </div>
  )
}

function agentRunPayload(task, workspaceId) {
  return {
    task,
    context: { workspace_id: workspaceId || '' },
  }
}

function NoiseAnalysisTab({ workspaceId, authFetch }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const runAnalysis = async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/agents/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(agentRunPayload('analyze alert noise last 7 days', workspaceId)),
      })
      if (!res.ok) throw new Error('Request failed')
      const data = await res.json()
      setResult(data)
    } catch {
      setError('Failed to run noise analysis.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h3 className="text-white font-semibold text-lg">Alert Noise Analysis</h3>
          <p className="text-gray-400 text-sm mt-0.5">
            Identify and suppress noisy, low-signal alerts
          </p>
        </div>
        <button
          type="button"
          onClick={() => void runAnalysis()}
          disabled={loading}
          className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-sm px-4 py-2 rounded-lg flex items-center gap-2"
        >
          {loading ? (
            <>
              <span className="animate-spin">⟳</span>
              Analyzing…
            </>
          ) : (
            'Analyze Noise (7d)'
          )}
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700 rounded-lg p-4 text-red-300 text-sm">
          {error}
        </div>
      )}

      {result && (
        <>
          <div className="bg-gray-800 rounded-xl p-4 mb-4">
            <p className="text-white text-sm">{result.summary}</p>
            <p className="text-gray-400 text-xs mt-1">
              Status:{' '}
              <span
                className={
                  result.status === 'success' ? 'text-green-400' : 'text-yellow-400'
                }
              >
                {result.status}
              </span>
            </p>
          </div>

          {Array.isArray(result.details?.noisy_alerts) &&
            result.details.noisy_alerts.length > 0 && (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left">
                  <thead>
                    <tr className="text-gray-400 border-b border-gray-700">
                      <th className="py-2 pr-4">Alert Name</th>
                      <th className="py-2 pr-4">Fires (7d)</th>
                      <th className="py-2 pr-4">Signal Score</th>
                      <th className="py-2">Recommendation</th>
                    </tr>
                  </thead>
                  <tbody>
                    {result.details.noisy_alerts.map((alert, i) => (
                      <tr key={i} className="border-b border-gray-800 hover:bg-gray-800/50">
                        <td className="py-2 pr-4 text-white">{alert.name}</td>
                        <td className="py-2 pr-4 text-gray-300">{alert.fire_count}</td>
                        <td className="py-2 pr-4">
                          <span
                            className={
                              (alert.signal_score || 0) < 0.3
                                ? 'text-red-400'
                                : 'text-yellow-400'
                            }
                          >
                            {((alert.signal_score || 0) * 100).toFixed(0)}%
                          </span>
                        </td>
                        <td className="py-2 text-gray-400 text-xs">
                          {alert.recommendation || 'Review'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

          {result.details?.noisy_alerts?.length === 0 && (
            <div className="text-center py-8 text-gray-400">
              <span className="text-3xl block mb-2">✅</span>
              No noisy alerts detected in the last 7 days.
            </div>
          )}
        </>
      )}

      {!loading && !result && !error && (
        <div className="text-center py-12 text-gray-400">
          <span className="text-4xl block mb-3">🔔</span>
          <p>Click &quot;Analyze Noise&quot; to scan your alerts.</p>
        </div>
      )}
    </div>
  )
}

const PLACEHOLDER = `Paste raw Kubernetes, DB, or system logs here...

Example:
[2024-06-10 03:41:22] ERROR  pq: sorry, too many clients already
[2024-06-10 03:41:22] FATAL  connection to server failed: FATAL: remaining connection slots reserved
[2024-06-10 03:41:25] WARN   pod/api-gateway-7d9f8b: CrashLoopBackOff — exit code 1`

export default function TriageView({
  selectedIncident: selectedIncidentProp,
  onSelectIncident: onSelectIncidentProp,
  onAnalysisComplete,
}) {
  const { authFetch } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const workspaceId = activeWorkspace?.id ?? ''
  const [activeTab, setActiveTab] = useState('logs')
  const controlled = typeof onSelectIncidentProp === 'function'
  const [internalSelected, setInternalSelected] = useState(null)
  const [historyVersion, setHistoryVersion] = useState(0)
  const [logs, setLogs] = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [incidentsLoading, setIncidentsLoading] = useState(true)
  const [hasActiveIncidents, setHasActiveIncidents] = useState(false)

  const selectedIncident = controlled ? selectedIncidentProp : internalSelected
  const selectIncident = controlled ? onSelectIncidentProp : setInternalSelected

  const loadIncidents = useCallback(async () => {
    setIncidentsLoading(true)
    try {
      const res = await authFetch('/api/incidents')
      if (!res.ok) {
        setHasActiveIncidents(false)
        return
      }
      const list = await res.json()
      const active = (Array.isArray(list) ? list : []).some((inc) =>
        ACTIVE_STATUSES.has(inc.status)
      )
      setHasActiveIncidents(active)
    } catch {
      setHasActiveIncidents(false)
    } finally {
      setIncidentsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void loadIncidents()
  }, [loadIncidents, historyVersion])

  useEffect(() => {
    if (selectedIncident) {
      setError(null)
    }
  }, [selectedIncident])

  async function handleAnalyze() {
    if (!logs.trim()) return
    setLoading(true)
    setError(null)
    setResult(null)
    selectIncident(null)

    try {
      const res = await authFetch('/api/triage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ logs }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ?? `Server error ${res.status}`)
      }
      const data = await res.json()
      setResult(data)
      setHistoryVersion((v) => v + 1)
      onAnalysisComplete?.()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function handleClear() {
    setLogs('')
    setResult(null)
    setError(null)
    selectIncident(null)
  }

  function handleHistorySelect(inc) {
    selectIncident(inc)
    setResult(null)
    setError(null)
  }

  const displayResult = selectedIncident ?? result

  return (
    <div className="flex flex-1 min-h-0 -m-6 overflow-hidden">
      <div className="flex-1 overflow-y-auto p-6">
        <div className="flex flex-col gap-6 max-w-4xl w-full mx-auto">
          <div className="flex items-start justify-between">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <ScanSearch className="w-5 h-5 text-accent" strokeWidth={2} />
                <h1 className="text-xl font-bold text-white tracking-tight">Triage Mode</h1>
              </div>
              <p className="text-sm text-slate-400">
                Paste raw logs and let AI surface the root cause and a step-by-step fix.
              </p>
            </div>

            <div className="flex items-center gap-2 text-xs text-slate-500 border border-border rounded-lg px-3 py-2 bg-card">
              <Sparkles className="w-3.5 h-3.5 text-accent" />
              <span>{displayResult?.model_used ?? 'Ollama / Gemma 3 4B (Local)'}</span>
              <span className="w-1.5 h-1.5 rounded-full bg-accent inline-block" />
            </div>
          </div>

          <div className="flex gap-1 mt-2">
            {TRIAGE_TABS.map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  activeTab === tab.id
                    ? 'bg-blue-600 text-white'
                    : 'text-gray-400 hover:text-white hover:bg-white/5'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {activeTab === 'noise' ? (
            <div className="rounded-xl border border-border bg-card overflow-hidden">
              <NoiseAnalysisTab workspaceId={workspaceId} authFetch={authFetch} />
            </div>
          ) : (
            <>
          {selectedIncident && (
            <div className="flex items-center justify-between px-4 py-2.5 rounded-xl border border-accent/30 bg-accent/5">
              <div className="flex items-center gap-2 text-xs text-slate-300">
                <span className="text-accent font-semibold">Viewing Incident #{selectedIncident.id}</span>
                <span className="text-slate-600">—</span>
                <span className="text-slate-500">
                  {new Date(selectedIncident.timestamp).toLocaleString()}
                </span>
              </div>
              <button
                type="button"
                onClick={handleClear}
                className="flex items-center gap-1.5 text-xs text-accent hover:text-white transition-colors"
              >
                <ArrowLeft className="w-3.5 h-3.5" />
                Back to Triage
              </button>
            </div>
          )}

          {!selectedIncident &&
            !result &&
            !logs.trim() &&
            !incidentsLoading &&
            !hasActiveIncidents && (
              <EmptyState icon="✅" title="All clear. No active incidents." />
            )}

          {!selectedIncident && (
            <>
              <div className="flex flex-col rounded-xl border border-border bg-card overflow-hidden">
                <div className="flex items-center justify-between px-4 py-2.5 border-b border-border bg-sidebar">
                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <Terminal className="w-3.5 h-3.5" />
                    <span className="font-mono">log_input.txt</span>
                  </div>
                  {logs && (
                    <button
                      type="button"
                      onClick={handleClear}
                      className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
                    >
                      Clear
                    </button>
                  )}
                </div>

                <textarea
                  className="w-full h-56 bg-transparent px-4 py-3.5 text-sm font-mono text-slate-300 placeholder-slate-600 resize-none outline-none leading-relaxed"
                  placeholder={PLACEHOLDER}
                  value={logs}
                  onChange={(e) => setLogs(e.target.value)}
                  spellCheck={false}
                />

                <div className="flex items-center justify-between px-4 py-2 border-t border-border bg-sidebar">
                  <span className="text-[11px] text-slate-600 font-mono">
                    {logs.length > 0 ? `${logs.length} characters` : 'No input yet'}
                  </span>
                  <div className="flex items-center gap-1.5 text-[11px] text-slate-600">
                    <ClipboardPaste className="w-3 h-3" />
                    Supports K8s, Postgres, Nginx, systemd logs
                  </div>
                </div>
              </div>

              <div className="flex items-center gap-3">
                <button
                  type="button"
                  onClick={handleAnalyze}
                  disabled={!logs.trim() || loading}
                  className="flex items-center justify-center gap-2 px-6 py-3 rounded-xl text-sm font-semibold bg-accent text-black
                hover:bg-green-400 active:scale-95
                disabled:opacity-40 disabled:cursor-not-allowed disabled:scale-100
                transition-all duration-150 glow-green"
                >
                  {loading ? (
                    <>
                      <span className="w-4 h-4 border-2 border-black/30 border-t-black rounded-full animate-spin" />
                      Analyzing…
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      Analyze Logs
                    </>
                  )}
                </button>
                {!logs.trim() && !loading && (
                  <p className="text-xs text-slate-600 italic">Paste logs above to enable analysis</p>
                )}
              </div>
            </>
          )}

          {error && (
            <div className="flex items-start gap-3 p-4 rounded-xl bg-red-500/10 border border-red-500/30 animate-fade-in">
              <AlertOctagon className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
              <div>
                <p className="text-sm font-semibold text-red-400">Analysis Failed</p>
                <p className="text-xs text-slate-400 mt-0.5">{error}</p>
                {error.toLowerCase().includes('fetch') && (
                  <p className="text-xs text-slate-500 mt-1">
                    Make sure the backend is running:{' '}
                    <code className="font-mono bg-slate-800 px-1 rounded text-slate-300">
                      python -m uvicorn main:app --reload
                    </code>
                  </p>
                )}
              </div>
            </div>
          )}

          {displayResult && (
            <div className="flex flex-col gap-4 animate-fade-in">
              {!selectedIncident && (
                <div className="flex items-center gap-3">
                  <div className="flex-1 h-px bg-border" />
                  <div className="flex items-center gap-1.5 text-xs text-slate-500">
                    <ChevronDown className="w-3.5 h-3.5 text-accent" />
                    <span>AI Analysis Complete</span>
                  </div>
                  <div className="flex-1 h-px bg-border" />
                </div>
              )}

              <div className="rounded-xl border border-border bg-surface p-5">
                <IncidentReportCard
                  id={displayResult.id}
                  severity={displayResult.severity}
                  summary={displayResult.summary}
                  rootCause={displayResult.root_cause}
                  evidence={displayResult.evidence}
                  actionPlan={displayResult.action_plan}
                  commands={displayResult.commands}
                  filesToCheck={displayResult.files_to_check}
                  validationSteps={displayResult.validation_steps}
                  modelUsed={displayResult.model_used}
                  status={displayResult.status ?? 'OPEN'}
                  executionLogs={displayResult.execution_logs ?? null}
                />
              </div>
            </div>
          )}
            </>
          )}
        </div>
      </div>

      <IncidentHistory
        version={historyVersion}
        selectedId={selectedIncident?.id}
        onSelectIncident={handleHistorySelect}
      />
    </div>
  )
}
