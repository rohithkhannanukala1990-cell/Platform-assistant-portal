import { useState } from 'react'
import { ScanEye, Loader2, CheckCircle2, AlertTriangle, X } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { API_BASE } from '../../config/apiBase'

const SCAN_API = `${API_BASE}/api/logs/scan-anomalies`

/**
 * Compact one-line scanner card that only expands while a scan is
 * running or after a result arrives.
 */
export default function LogScannerCard({ onIncidentCreated }) {
  const { authFetch } = useAuth()
  const [scanning, setScanning] = useState(false)
  const [result, setResult] = useState(null)
  const [dismissed, setDismissed] = useState(false)

  async function runScan() {
    setScanning(true)
    setResult(null)
    setDismissed(false)
    try {
      const res = await authFetch(SCAN_API, { method: 'POST' })
      if (!res.ok) throw new Error(`Scan failed: ${res.status}`)
      const incident = await res.json()
      setResult(incident)
      onIncidentCreated?.()
    } catch (e) {
      setResult({ error: e.message })
    } finally {
      setScanning(false)
    }
  }

  return (
    <div className="flex flex-col gap-3 p-4 rounded-2xl border border-border bg-card">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-amber-500/15 shrink-0">
            <ScanEye className="w-4 h-4 text-amber-400" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-bold text-white truncate">Log Scanner</p>
            <p className="text-[10px] text-slate-500 truncate">AI anomaly detection</p>
          </div>
        </div>
        <button
          type="button"
          onClick={runScan}
          disabled={scanning}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors shrink-0
            disabled:opacity-50 disabled:cursor-not-allowed
            bg-amber-500/15 border border-amber-500/30 text-amber-300
            hover:bg-amber-500/25 hover:text-amber-200"
        >
          {scanning
            ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> Scanning…</>
            : <><ScanEye className="w-3.5 h-3.5" /> Run Scan</>}
        </button>
      </div>

      {scanning && (
        <div className="w-full h-1.5 bg-border/60 rounded-full overflow-hidden">
          <div className="h-full bg-amber-400 rounded-full animate-pulse" style={{ width: '60%' }} />
        </div>
      )}

      {result && !dismissed && (
        <div className={`relative flex flex-col gap-2 p-3 rounded-xl border text-sm ${
          result.error ? 'border-red-500/30 bg-red-500/10' : 'border-amber-500/30 bg-amber-500/10'
        }`}>
          <button
            type="button"
            onClick={() => setDismissed(true)}
            className="absolute top-2.5 right-2.5 text-slate-600 hover:text-slate-300 transition-colors"
            aria-label="Dismiss scan result"
          >
            <X className="w-4 h-4" />
          </button>

          {result.error ? (
            <p className="text-red-400 flex items-center gap-2 text-xs">
              <AlertTriangle className="w-4 h-4 shrink-0" />
              {result.error}
            </p>
          ) : (
            <>
              <div className="flex items-center gap-2 font-semibold text-amber-300 text-xs pr-6">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                Anomaly detected — Incident #{result.id} created
              </div>
              <p className="text-slate-300 text-xs leading-relaxed">{result.summary}</p>
              {result.root_cause && (
                <p className="text-slate-500 text-[11px]">{result.root_cause}</p>
              )}
              <p className="text-[10px] text-slate-600">
                via Anomaly Scanner · see Alert Triage for the full report
              </p>
            </>
          )}
        </div>
      )}
    </div>
  )
}
