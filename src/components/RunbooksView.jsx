import { useState, useEffect, useCallback } from 'react'
import {
  BookOpen, Play, CheckCircle2, Clock, Tag, ChevronDown,
  ChevronUp, Terminal, Loader2, Shield, Server, Database,
  Wifi,   Search,
  AlertTriangle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'
import RelatedAgentsBar from './RelatedAgentsBar'

const CATEGORIES = ['All', 'Application', 'Database', 'Network', 'Security']

function EmptyState({ icon, title, subtitle, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-gray-400">
      <span className="text-5xl mb-4">{icon}</span>
      <p className="text-base font-medium text-gray-300">{title}</p>
      {subtitle && <p className="text-sm mt-1">{subtitle}</p>}
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="mt-4 text-sm bg-indigo-600 hover:bg-indigo-500 text-white px-5 py-2 rounded-lg"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

function mapCategory(cat) {
  const c = (cat || 'General').trim()
  if (CATEGORIES.includes(c)) return c
  if (c === 'General') return 'Application'
  return 'Application'
}

function parseSteps(stepsJson) {
  if (!stepsJson) return []
  try {
    const parsed = typeof stepsJson === 'string' ? JSON.parse(stepsJson) : stepsJson
    if (Array.isArray(parsed)) return parsed.map(String)
    if (parsed && typeof parsed === 'object') {
      return Object.values(parsed).flat().map(String)
    }
  } catch {
    return [String(stepsJson)]
  }
  return []
}

function templateToRunbook(t) {
  const steps = parseSteps(t.steps_json)
  return {
    id: String(t.id),
    title: t.name,
    category: mapCategory(t.category),
    severity: 'Medium',
    estimatedTime: steps.length ? `${Math.max(2, steps.length * 2)} min` : '5 min',
    description: t.description || '',
    tags: [t.slug, t.category].filter(Boolean),
    steps: steps.length ? steps : ['Review runbook steps in the template.'],
  }
}

const CATEGORY_CFG = {
  Application: { icon: Server,   color: 'text-blue-400',   bg: 'bg-blue-500/10  border-blue-500/25'  },
  Database:    { icon: Database, color: 'text-cyan-400',   bg: 'bg-cyan-500/10  border-cyan-500/25'  },
  Network:     { icon: Wifi,     color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/25' },
  Security:    { icon: Shield,   color: 'text-red-400',    bg: 'bg-red-500/10   border-red-500/25'   },
}

const SEV_CFG = {
  Critical: 'text-red-400    bg-red-500/10    border-red-500/25',
  High:     'text-orange-400 bg-orange-500/10 border-orange-500/25',
  Medium:   'text-yellow-400 bg-yellow-500/10 border-yellow-500/25',
  Low:      'text-blue-400   bg-blue-500/10   border-blue-500/25',
}

function RunbookCard({ rb }) {
  const [expanded, setExpanded] = useState(false)
  const [running,  setRunning]  = useState(false)
  const [done,     setDone]     = useState(false)
  const [step,     setStep]     = useState(0)

  const catCfg  = CATEGORY_CFG[rb.category]
  const CatIcon = catCfg.icon

  function handleRun() {
    setRunning(true)
    setStep(0)
    setDone(false)
    const interval = setInterval(() => {
      setStep(prev => {
        if (prev >= rb.steps.length - 1) {
          clearInterval(interval)
          setRunning(false)
          setDone(true)
          return prev
        }
        return prev + 1
      })
    }, 900)
  }

  return (
    <div className={`flex flex-col rounded-2xl border overflow-hidden transition-all
      ${done ? 'border-green-500/25' : 'border-border'} bg-card`}>

      {/* Header */}
      <div className="flex items-start gap-3 p-4">
        <div className={`flex items-center justify-center w-9 h-9 rounded-xl border shrink-0 ${catCfg.bg}`}>
          <CatIcon className={`w-4 h-4 ${catCfg.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-bold text-white">{rb.title}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${SEV_CFG[rb.severity]}`}>
              {rb.severity}
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{rb.description}</p>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="flex items-center gap-1 text-[10px] text-slate-500">
              <Clock className="w-2.5 h-2.5" /> ~{rb.estimatedTime}
            </span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${catCfg.bg} ${catCfg.color}`}>
              {rb.category}
            </span>
            {rb.tags.map(t => (
              <span key={t} className="flex items-center gap-1 text-[10px] text-slate-600 border border-slate-700 rounded-md px-1.5 py-0.5">
                <Tag className="w-2 h-2" />{t}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!done && (
            <button
              onClick={handleRun}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-accent/15 border border-accent/35
                text-accent text-xs font-bold hover:bg-accent/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {running
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Running…</>
                : <><Play className="w-3 h-3" /> Run</>
              }
            </button>
          )}
          {done && (
            <span className="flex items-center gap-1 text-[11px] text-green-400 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" /> Complete
            </span>
          )}
          <button
            onClick={() => setExpanded(v => !v)}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-white transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Steps */}
      {(expanded || running || done) && (
        <div className="border-t border-border px-4 pb-4 pt-3 flex flex-col gap-2">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Execution Steps</p>
          <ol className="flex flex-col gap-1.5">
            {rb.steps.map((s, i) => {
              const isCurrent = running && i === step
              const isDone    = done || (running && i < step)
              return (
                <li key={i} className={`flex items-start gap-2 text-xs transition-all
                  ${isCurrent ? 'text-accent' : isDone ? 'text-green-400' : 'text-slate-500'}`}>
                  <span className={`shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold border
                    ${isCurrent ? 'border-accent/50 bg-accent/15' : isDone ? 'border-green-500/40 bg-green-500/10' : 'border-slate-700 bg-transparent'}`}>
                    {isDone ? '✓' : i + 1}
                  </span>
                  <span className={`font-mono leading-relaxed ${s.startsWith('SELECT') || s.startsWith('kubectl') || s.startsWith('psql') || s.startsWith('kafka') || s.startsWith('openssl') || s.startsWith('iptables')
                    ? 'text-[10px] bg-black/40 border border-slate-700/60 rounded px-2 py-0.5 w-full' : ''}`}>
                    {s}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </div>
  )
}

export default function RunbooksView() {
  const { authFetch } = useAuth()
  const [category, setCategory] = useState('All')
  const [search, setSearch] = useState('')
  const [runbooks, setRunbooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchRunbooks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch(`${API_BASE}/api/golden-paths`)
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      setRunbooks(list.map(templateToRunbook))
    } catch (e) {
      setError(e.message || 'Failed to load runbooks')
      setRunbooks([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void fetchRunbooks()
  }, [fetchRunbooks])

  const filtered = runbooks.filter((rb) => {
    const matchCat    = category === 'All' || rb.category === category
    const matchSearch = !search || rb.title.toLowerCase().includes(search.toLowerCase()) ||
      rb.tags.some(t => t.includes(search.toLowerCase()))
    return matchCat && matchSearch
  })

  return (
    <div className="flex flex-col gap-6 max-w-5xl mx-auto pb-16 animate-fade-in">

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <div>
          <h1 className="text-xl font-bold text-white tracking-tight flex items-center gap-2">
            <BookOpen className="w-5 h-5 text-blue-400" />
            Runbooks
          </h1>
          <p className="text-sm text-slate-500 mt-0.5">Executable step-by-step remediation playbooks</p>
        </div>
        <span className="text-[10px] text-slate-600 border border-slate-700 rounded-lg px-2.5 py-1 font-semibold">
          {filtered.length} runbooks
        </span>
      </div>

      <RelatedAgentsBar surface="runbooks" />

      {/* Filter bar */}
      <div className="flex items-center gap-3 flex-wrap">
        {/* Search */}
        <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 flex-1 min-w-48">
          <Search className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by title or tag…"
            className="bg-transparent text-xs text-slate-200 placeholder-slate-600 outline-none w-full"
          />
        </div>
        {/* Category pills */}
        <div className="flex items-center gap-2 flex-wrap">
          {CATEGORIES.map(cat => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                category === cat
                  ? 'bg-accent/15 border-accent/40 text-accent'
                  : 'border-slate-700 text-slate-500 hover:text-white hover:border-slate-600'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      {/* Runbook cards */}
      <div className="flex flex-col gap-4">
        {loading ? (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-slate-800 rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center py-12 text-gray-400">
            <AlertTriangle className="w-8 h-8 text-amber-400 mb-2" />
            <p className="text-sm">{error}</p>
            <button
              type="button"
              onClick={() => void fetchRunbooks()}
              className="mt-3 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
            >
              Retry
            </button>
          </div>
        ) : runbooks.length === 0 ? (
          <EmptyState
            icon="📖"
            title="No runbooks found."
            action={{
              label: 'Create Runbook',
              onClick: () => {
                window.location.href = '/golden-paths'
              },
            }}
          />
        ) : filtered.length === 0 ? (
          <p className="text-center py-12 text-slate-600 text-sm">No runbooks match your filter.</p>
        ) : (
          filtered.map((rb) => <RunbookCard key={rb.id} rb={rb} />)
        )}
      </div>
    </div>
  )
}
