import { useEffect, useState, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'
import {
  History,
  AlertTriangle, AlertCircle, Info,
  ChevronLeft, ChevronRight,
  RefreshCw, Inbox,
  Zap, Construction, Rocket,
} from 'lucide-react'
import { API_BASE } from '../config/apiBase'

const ENDPOINTS = {
  alerts: `${API_BASE}/api/incidents`,
  infra:  `${API_BASE}/api/infra/history`,
  cicd:   `${API_BASE}/api/cicd/history`,
}

const TABS = [
  { id: 'alerts', label: 'Alerts',  icon: Zap,          color: 'text-red-400' },
  { id: 'infra',  label: 'Infra',   icon: Construction,  color: 'text-blue-400' },
  { id: 'cicd',   label: 'CI/CD',   icon: Rocket,        color: 'text-purple-400' },
]

const SEVERITY_STYLES = {
  Critical: 'bg-red-500/15 border-red-500/40 text-red-400',
  High:     'bg-orange-500/15 border-orange-500/40 text-orange-400',
  Medium:   'bg-yellow-500/15 border-yellow-500/40 text-yellow-400',
  Warning:  'bg-amber-500/15 border-amber-500/40 text-amber-400',
  Low:      'bg-blue-500/15 border-blue-500/40 text-blue-400',
  Unknown:  'bg-slate-500/15 border-slate-500/40 text-slate-400',
}

const SEVERITY_ICONS = {
  Critical: AlertTriangle,
  High: AlertCircle, Medium: AlertCircle,
  Warning: AlertCircle,
  Low: Info, Unknown: Info,
}

const PROVIDER_COLORS = {
  AWS: 'text-orange-400', GCP: 'text-blue-400',
  Azure: 'text-sky-400', DigitalOcean: 'text-cyan-400',
}

const TOOL_COLORS = {
  'GitHub Actions': 'text-purple-400',
  'GitLab CI':      'text-orange-400',
  Jenkins:          'text-red-400',
}

function Badge({ text, style }) {
  return (
    <span className={`inline-flex items-center px-1.5 py-0.5 rounded border text-[10px] font-bold tracking-wider uppercase ${style}`}>
      {text}
    </span>
  )
}

function SeverityBadge({ severity }) {
  const style = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.Unknown
  const Icon  = SEVERITY_ICONS[severity]  ?? Info
  return (
    <span className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded border text-[10px] font-bold tracking-wider uppercase ${style}`}>
      <Icon className="w-2.5 h-2.5" strokeWidth={2.5} />{severity}
    </span>
  )
}

function formatTime(iso) {
  return new Date(iso).toLocaleString(undefined, {
    month: 'short', day: 'numeric',
    hour: '2-digit', minute: '2-digit',
  })
}

function AlertRow({ item, selected, onClick }) {
  const isWebhook   = item.source && item.source !== 'manual'
  const webhookName = isWebhook ? item.source.replace(/^webhook:/, '') : null

  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 hover:bg-card transition-colors ${selected ? 'bg-card border-l-2 border-accent' : ''}`}
    >
      <div className="flex items-center justify-between mb-1.5 gap-2">
        <div className="flex items-center gap-1.5 flex-wrap">
          <SeverityBadge severity={item.severity} />
          {isWebhook && (
            <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-cyan-500/40 bg-cyan-500/10 text-cyan-400 text-[9px] font-bold uppercase tracking-wider">
              ⚡ {webhookName}
            </span>
          )}
        </div>
        <span className="text-[10px] text-slate-600 shrink-0">{formatTime(item.timestamp)}</span>
      </div>
      <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">{item.summary}</p>
      <p className="text-[10px] text-slate-600 mt-1">{item.model_used}</p>
    </button>
  )
}

function InfraRow({ item, selected, onClick }) {
  const color = PROVIDER_COLORS[item.provider_used] ?? 'text-slate-400'
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 hover:bg-card transition-colors ${selected ? 'bg-card border-l-2 border-accent' : ''}`}
    >
      <div className="flex items-center justify-between mb-1.5 gap-2">
        <span className={`text-[10px] font-bold uppercase tracking-wider ${color}`}>
          {item.provider_used}
        </span>
        <span className="text-[10px] text-slate-600 shrink-0">{formatTime(item.timestamp)}</span>
      </div>
      <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">{item.resource_name}</p>
      <p className="text-[10px] text-slate-600 mt-1 truncate">{item.prompt}</p>
    </button>
  )
}

function CICDRow({ item, selected, onClick }) {
  const color = TOOL_COLORS[item.tool_name] ?? 'text-slate-400'
  return (
    <button
      onClick={onClick}
      className={`w-full text-left px-4 py-3 hover:bg-card transition-colors ${selected ? 'bg-card border-l-2 border-accent' : ''}`}
    >
      <div className="flex items-center justify-between mb-1.5 gap-2">
        <span className={`text-[10px] font-bold uppercase tracking-wider ${color}`}>
          {item.tool_name}
        </span>
        <span className="text-[10px] text-slate-600 shrink-0">{formatTime(item.timestamp)}</span>
      </div>
      <p className="text-xs text-slate-300 leading-relaxed line-clamp-2">{item.prompt}</p>
    </button>
  )
}

export default function HistoryPanel({ versions, onSelect, selectedIds, activeView }) {
  const { role } = useAuth()
  const [activeTab, setActiveTab]   = useState('alerts')
  const [data, setData]             = useState({ alerts: [], infra: [], cicd: [] })
  const [loading, setLoading]       = useState(false)
  const [collapsed, setCollapsed]   = useState(false)

  const fetchTab = useCallback(async (tab) => {
    setLoading(true)
    try {
      // Append ?role= so the backend filters incidents for non-Admin roles
      const url = tab === 'alerts' && role !== 'Admin'
        ? `${ENDPOINTS[tab]}?role=${role}`
        : ENDPOINTS[tab]
      const res = await fetch(url)
      if (res.ok) {
        const json = await res.json()
        setData((prev) => ({ ...prev, [tab]: json }))
      }
    } catch (_err) { /* fail silently */ }
    finally { setLoading(false) }
  }, [role])

  // Re-fetch the active tab whenever its version bumps
  useEffect(() => { fetchTab(activeTab) }, [fetchTab, activeTab, versions[activeTab]])

  // Sync the active tab with which module the user is viewing
  useEffect(() => {
    if (activeView === 'triage') setActiveTab('alerts')
    else if (activeView === 'infra') setActiveTab('infra')
    else if (activeView === 'cicd') setActiveTab('cicd')
  }, [activeView])

  const counts = {
    alerts: data.alerts.length,
    infra:  data.infra.length,
    cicd:   data.cicd.length,
  }

  // ── Collapsed tab ──────────────────────────────────────────────────────────
  if (collapsed) {
    return (
      <div className="flex flex-col items-center w-9 shrink-0 border-l border-border bg-sidebar py-4 gap-3">
        <button
          onClick={() => setCollapsed(false)}
          className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white"
          title="Show history"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
        <div
          className="text-[10px] font-semibold text-slate-600 uppercase tracking-widest"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)' }}
        >
          History
        </div>
        {counts[activeTab] > 0 && (
          <span className="w-5 h-5 rounded-full bg-accent/20 border border-accent/40 text-accent text-[9px] font-bold flex items-center justify-center">
            {counts[activeTab] > 9 ? '9+' : counts[activeTab]}
          </span>
        )}
      </div>
    )
  }

  // ── Expanded panel ─────────────────────────────────────────────────────────
  return (
    <aside className="flex flex-col w-72 shrink-0 border-l border-border bg-sidebar overflow-hidden">

      {/* Panel header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border shrink-0">
        <div className="flex items-center gap-2">
          <History className="w-4 h-4 text-accent" />
          <span className="text-sm font-semibold text-white">History</span>
        </div>
        <div className="flex items-center gap-1">
          <button onClick={() => fetchTab(activeTab)} className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-500 hover:text-white" title="Refresh">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <button onClick={() => setCollapsed(true)} className="p-1.5 rounded-lg hover:bg-card transition-colors text-slate-500 hover:text-white" title="Collapse">
            <ChevronRight className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border shrink-0">
        {TABS.map(({ id, label, icon: Icon, color }) => (
          <button
            key={id}
            onClick={() => { setActiveTab(id); fetchTab(id) }}
            className={`flex-1 flex flex-col items-center gap-0.5 py-2.5 text-[10px] font-bold uppercase tracking-wider transition-colors
              ${activeTab === id
                ? `${color} border-b-2 border-current bg-card/50`
                : 'text-slate-600 hover:text-slate-400'
              }`}
          >
            <Icon className="w-3.5 h-3.5" strokeWidth={2} />
            {label}
            {counts[id] > 0 && (
              <span className="text-[9px] opacity-70">({counts[id]})</span>
            )}
          </button>
        ))}
      </div>

      {/* List */}
      <div className="flex-1 overflow-y-auto">
        {loading && data[activeTab].length === 0 ? (
          <div className="flex items-center justify-center h-32 text-xs text-slate-600">Loading…</div>
        ) : data[activeTab].length === 0 ? (
          <div className="flex flex-col items-center justify-center gap-2 h-40 text-slate-600 px-4 text-center">
            <Inbox className="w-6 h-6 opacity-40" />
            <p className="text-xs">No {activeTab} history yet.</p>
          </div>
        ) : (
          <ul className="flex flex-col divide-y divide-border">
            {activeTab === 'alerts' && data.alerts.map((item) => (
              <li key={item.id}>
                <AlertRow
                  item={item}
                  selected={selectedIds.alerts === item.id}
                  onClick={() => onSelect('alerts', item)}
                />
              </li>
            ))}
            {activeTab === 'infra' && data.infra.map((item) => (
              <li key={item.id}>
                <InfraRow
                  item={item}
                  selected={selectedIds.infra === item.id}
                  onClick={() => onSelect('infra', item)}
                />
              </li>
            ))}
            {activeTab === 'cicd' && data.cicd.map((item) => (
              <li key={item.id}>
                <CICDRow
                  item={item}
                  selected={selectedIds.cicd === item.id}
                  onClick={() => onSelect('cicd', item)}
                />
              </li>
            ))}
          </ul>
        )}
      </div>
    </aside>
  )
}
