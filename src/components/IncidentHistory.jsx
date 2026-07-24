import { useEffect, useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  History,
  AlertTriangle,
  AlertCircle,
  Info,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Inbox,
  ExternalLink,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const SEVERITY_STYLES = {
  Critical: 'bg-red-500/15 border-red-500/40 text-red-400',
  High:     'bg-orange-500/15 border-orange-500/40 text-orange-400',
  Medium:   'bg-yellow-500/15 border-yellow-500/40 text-yellow-400',
  Low:      'bg-blue-500/15 border-blue-500/40 text-blue-400',
  Unknown:  'bg-slate-500/15 border-slate-500/40 text-slate-400',
}

const SEVERITY_ICONS = {
  Critical: AlertTriangle,
  High:     AlertCircle,
  Medium:   AlertCircle,
  Low:      Info,
  Unknown:  Info,
}

function SeverityBadge({ severity }) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.Unknown
  const Icon  = SEVERITY_ICONS[severity]  ?? Info
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold tracking-wider uppercase ${style}`}>
      <Icon className="w-2.5 h-2.5" strokeWidth={2.5} />
      {severity}
    </span>
  )
}

function formatTime(iso) {
  const d = new Date(iso)
  return d.toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

export default function IncidentHistory({ version, onSelectIncident, selectedId }) {
  const { authFetch } = useAuth()
  const navigate = useNavigate()
  const [incidents, setIncidents]   = useState([])
  const [loading, setLoading]       = useState(false)
  const [collapsed, setCollapsed]   = useState(false)

  const fetchIncidents = useCallback(async () => {
    setLoading(true)
    try {
      const res = await authFetch('/api/incidents')
      if (res.ok) setIncidents(await res.json())
    } catch {
      // backend not reachable — fail silently
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  // Re-fetch whenever a new analysis completes (version bumps)
  useEffect(() => { fetchIncidents() }, [fetchIncidents, version])

  // ── Collapsed toggle tab ─────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-9 shrink-0 border-l border-border bg-sidebar py-4 gap-3">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white"
          title="Show incident history"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div
          className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          History
        </div>
        {incidents.length > 0 && (
          <span className="w-5 h-5 rounded-full bg-accent/20 border border-accent/40 text-accent text-[9px] font-bold flex items-center justify-center">
            {incidents.length > 9 ? '9+' : incidents.length}
          </span>
        )}
      </div>
    )
  }

  // ── Expanded panel ───────────────────────────────────────────────────────
  return (
    <aside className="flex flex-col w-72 shrink-0 border-l border-border bg-sidebar overflow-hidden">
      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3.5 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-accent" />
          <span className="text-sm font-semibold text-white">Recent Incidents</span>
          {incidents.length > 0 && (
            <span className="text-[10px] font-bold text-accent bg-accent/10 border border-accent/30 rounded px-1.5 py-0.5">
              {incidents.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            onClick={fetchIncidents}
            className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-500 hover:text-white"
            title="Refresh"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button
            onClick={() => setCollapsed(true)}
            className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-500 hover:text-white"
            title="Collapse"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Incident list */}
      <div className="flex-1 overflow-y-auto">
        {loading && incidents.length === 0 ? (
          <div className="flex items-center justify-center h-32 text-xs text-slate-600">
            Loading…
          </div>
        ) : incidents.length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 h-40 text-slate-600 px-4 text-center">
            <Inbox className="w-6 h-6 opacity-40" />
            <p className="text-xs">No incidents yet. Run an analysis to start building history.</p>
          </div>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {incidents.map((inc) => (
              <li key={inc.id}>
                <div
                  className={`w-full text-left px-4 py-3 hover:bg-card transition-colors ${
                    selectedId === inc.id ? 'bg-card border-l-2 border-accent' : ''
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => onSelectIncident(inc)}
                    className="w-full text-left"
                  >
                    <div className="flex items-center justify-between mb-1.5 gap-2">
                      <SeverityBadge severity={inc.severity} />
                      <span className="text-[10px] text-slate-600 shrink-0">
                        {formatTime(inc.timestamp)}
                      </span>
                    </div>
                    <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">
                      {inc.summary}
                    </p>
                    <p className="text-[10px] text-slate-600 mt-1">{inc.model_used}</p>
                  </button>
                  <button
                    type="button"
                    onClick={() => navigate(`/incidents/${inc.id}`)}
                    className="mt-2 inline-flex items-center gap-1 text-[10px] font-semibold text-accent hover:underline"
                  >
                    Command center <ExternalLink className="w-2.5 h-2.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
