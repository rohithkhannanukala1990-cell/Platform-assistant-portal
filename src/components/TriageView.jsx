import { useState, useEffect } from 'react'
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

const PLACEHOLDER = `Paste raw Kubernetes, DB, or system logs here...

Example:
[2024-06-10 03:41:22] ERROR  pq: sorry, too many clients already
[2024-06-10 03:41:22] FATAL  connection to server failed: FATAL: remaining connection slots reserved
[2024-06-10 03:41:25] WARN   pod/api-gateway-7d9f8b: CrashLoopBackOff — exit code 1`

const API_URL = 'http://127.0.0.1:8000/api/triage'

export default function TriageView({ selectedIncident, onSelectIncident, onAnalysisComplete }) {
  const [logs, setLogs]     = useState('')
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError]   = useState(null)

  // When user selects a history incident, clear the live result
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
    onSelectIncident?.(null)

    try {
      const res = await fetch(API_URL, {
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
    onSelectIncident?.(null)
  }

  // What to show in the result area
  const displayResult = selectedIncident ?? result

  return (
    <div className="flex flex-col gap-6 max-w-4xl w-full mx-auto">

      {/* ── Page Header ───────────────────────────────────────────────────── */}
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
          <div className="w-1.5 h-1.5 rounded-full bg-accent" />
        </div>
      </div>

      {/* ── Viewing a history incident banner ─────────────────────────────── */}
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
            onClick={handleClear}
            className="flex items-center gap-1.5 text-xs text-accent hover:text-white transition-colors"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            Back to Triage
          </button>
        </div>
      )}

      {/* ── Log Input (hidden when viewing history) ────────────────────────── */}
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

      {/* ── Error Banner ──────────────────────────────────────────────────── */}
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

      {/* ── Result / History View ─────────────────────────────────────────── */}
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
    </div>
  )
}
