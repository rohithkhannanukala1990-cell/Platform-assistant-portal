import { useState, useCallback, useEffect } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Sparkles, AlertTriangle, ChevronRight, Loader2, Route, Play } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'
import { API_BASE } from '../config/apiBase'

const CATALOG_API = `${API_BASE}/api/catalog`
const COPILOT_API = `${API_BASE}/api/catalog-copilot/copilot`

const QUICK_PROMPTS = [
  'Why is this service not production ready?',
  'What should this team fix first?',
  'What dependencies make this service risky?',
  'Show me the top 3 action recommendations',
]

function healthBadgeClass(status) {
  if (status === 'healthy') return 'bg-green-500/15 text-green-300 border-green-500/20'
  if (status === 'degraded') return 'bg-yellow-500/15 text-yellow-300 border-yellow-500/20'
  return 'bg-red-500/15 text-red-300 border-red-500/20'
}

function riskBadgeClass(level) {
  const l = (level || 'low').toLowerCase()
  if (l === 'high') return 'bg-red-500/15 text-red-300 border-red-500/25'
  if (l === 'medium') return 'bg-amber-500/15 text-amber-300 border-amber-500/25'
  return 'bg-emerald-500/15 text-emerald-300 border-emerald-500/25'
}

function GoldenPathCard({ path, onStart, startingId }) {
  const busy = startingId === path.id
  return (
    <div className="rounded-xl border border-violet-500/20 bg-violet-500/5 p-3 flex flex-col gap-2">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-white truncate">{path.name}</p>
          {path.estimated_duration && (
            <p className="text-[11px] text-slate-500 mt-0.5">⏱ {path.estimated_duration}</p>
          )}
        </div>
        <span
          className={`shrink-0 text-[10px] px-2 py-0.5 rounded-md border font-semibold uppercase ${riskBadgeClass(path.risk_level)}`}
        >
          {path.risk_level || 'low'}
        </span>
      </div>
      {path.reason_for_recommendation && (
        <p className="text-xs text-slate-400 leading-relaxed">{path.reason_for_recommendation}</p>
      )}
      <button
        type="button"
        disabled={busy}
        onClick={() => onStart(path)}
        className="mt-1 inline-flex items-center justify-center gap-1.5 self-start px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold disabled:opacity-50"
      >
        {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
        Start
      </button>
    </div>
  )
}

export default function CatalogCopilotPanel({
  entity,
  entityActions = [],
  goldenPaths = [],
}) {
  const { authFetch } = useAuth()
  const { toast } = useToast()
  const navigate = useNavigate()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)
  const [entities, setEntities] = useState([])
  const [entitiesLoading, setEntitiesLoading] = useState(true)
  const [entitiesError, setEntitiesError] = useState(null)
  const [recommendedPaths, setRecommendedPaths] = useState([])
  const [pathsLoading, setPathsLoading] = useState(false)
  const [startingId, setStartingId] = useState(null)

  const fetchEntities = useCallback(async () => {
    setEntitiesLoading(true)
    setEntitiesError(null)
    try {
      const res = await authFetch(CATALOG_API)
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      setEntities(Array.isArray(data) ? data : (data.entities || []))
    } catch (e) {
      setEntitiesError(e.message || 'Failed to load catalog')
      setEntities([])
    } finally {
      setEntitiesLoading(false)
    }
  }, [authFetch])

  const loadRecommendedPaths = useCallback(async () => {
    if (!entity?.id) {
      setRecommendedPaths([])
      return
    }
    setPathsLoading(true)
    try {
      const res = await authFetch(
        `/api/golden-paths/applicable?entity_id=${encodeURIComponent(entity.id)}`
      )
      if (!res.ok) {
        setRecommendedPaths([])
        return
      }
      const data = await res.json()
      const items = Array.isArray(data) ? data : (data.items || [])
      setRecommendedPaths(items)
    } catch {
      setRecommendedPaths([])
    } finally {
      setPathsLoading(false)
    }
  }, [authFetch, entity?.id])

  useEffect(() => {
    void fetchEntities()
  }, [fetchEntities])

  useEffect(() => {
    void loadRecommendedPaths()
  }, [loadRecommendedPaths])

  const startPath = useCallback(
    async (path) => {
      if (!path?.id || !entity?.id) return
      setStartingId(path.id)
      try {
        const res = await authFetch(`/api/golden-paths/${encodeURIComponent(path.id)}/run`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            entity_id: entity.id,
            inputs: { entity_id: entity.id, entity_name: entity.name },
          }),
        })
        if (!res.ok) throw new Error(await res.text())
        toast.success(`Started “${path.name}”`)
        navigate('/agents', { state: { goldenPathRun: await res.json() } })
      } catch (e) {
        toast.error(e.message || 'Failed to start golden path')
      } finally {
        setStartingId(null)
      }
    },
    [authFetch, entity, navigate, toast]
  )

  const submit = useCallback(
    async (q) => {
      const text = (typeof q === 'string' ? q : question).trim()
      if (!text) return
      setLoading(true)
      setError(null)
      setResponse(null)
      try {
        const [copilotRes, aiRes] = await Promise.all([
          authFetch(COPILOT_API, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              question: text,
              entity_id: entity?.id ?? null,
              team: entity?.owner_team ?? null,
            }),
          }),
          entity?.name
            ? authFetch('/api/ai/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  message: `For catalog entity "${entity.name}" (${entity.kind}): ${text}`,
                  environment: 'development',
                }),
              })
            : Promise.resolve(null),
        ])

        if (!copilotRes.ok) throw new Error(`Error ${copilotRes.status}`)
        const copilotData = await copilotRes.json()
        setResponse(copilotData)

        if (aiRes?.ok) {
          const aiData = await aiRes.json()
          if (Array.isArray(aiData.golden_paths) && aiData.golden_paths.length > 0) {
            setRecommendedPaths(aiData.golden_paths)
          }
        }
      } catch (e) {
        setError(e.message || 'AI unavailable. Please try again.')
      } finally {
        setLoading(false)
      }
    },
    [question, entity, authFetch]
  )

  const handleKey = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void submit()
    }
  }

  const matchAction = (name) =>
    entityActions.find(
      (a) =>
        a.name?.toLowerCase().includes(name.toLowerCase()) ||
        name.toLowerCase().includes(a.name?.toLowerCase() || '')
    )

  const matchPath = (name) =>
    goldenPaths.find(
      (p) =>
        p.name?.toLowerCase().includes(name.toLowerCase()) ||
        name.toLowerCase().includes(p.name?.toLowerCase() || '')
    )

  if (entitiesLoading) {
    return (
      <div className="space-y-3 p-4">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-12 bg-gray-700 rounded animate-pulse" />
        ))}
      </div>
    )
  }

  if (entitiesError) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-12 text-gray-400">
        <span className="text-4xl mb-3">⚠️</span>
        <p className="text-sm">Failed to load catalog</p>
        <button
          type="button"
          onClick={() => {
            setEntitiesError(null)
            void fetchEntities()
          }}
          className="mt-3 text-xs bg-indigo-600 hover:bg-indigo-500 text-white px-4 py-2 rounded"
        >
          Retry
        </button>
      </div>
    )
  }

  if (!entitiesLoading && entities.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-full py-12 text-gray-400">
        <span className="text-4xl mb-3">🗂</span>
        <p className="text-sm font-medium">No catalog entities found</p>
        <p className="text-xs mt-1">Register a service to get started</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 h-full overflow-y-auto -mx-1">
      {entity && (
        <div className="flex items-start gap-3 p-3 rounded-xl border border-border bg-card">
          <Sparkles className="w-4 h-4 text-indigo-400 mt-0.5 shrink-0" />
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="text-sm font-semibold text-white truncate">{entity.name}</span>
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/15 text-blue-300 border border-blue-500/20">
                {entity.kind}
              </span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded border ${healthBadgeClass(entity.health_status)}`}
              >
                {entity.health_status || 'unknown'}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 mt-1">
              {entity.owner_team && `Owner: ${entity.owner_team}`}
              {entity.lifecycle && ` · ${entity.lifecycle}`}
            </p>
          </div>
        </div>
      )}

      {(pathsLoading || recommendedPaths.length > 0) && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold flex items-center gap-1.5">
            <Route className="w-3 h-3" /> Recommended golden paths
          </p>
          {pathsLoading && recommendedPaths.length === 0 ? (
            <div className="flex items-center gap-2 text-xs text-slate-500 py-2">
              <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading recommendations…
            </div>
          ) : (
            <div className="flex flex-col gap-2">
              {recommendedPaths.map((path) => (
                <GoldenPathCard
                  key={path.id || path.key}
                  path={path}
                  onStart={startPath}
                  startingId={startingId}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {!loading && !response && (
        <div className="flex flex-col gap-2">
          <p className="text-[10px] text-slate-600 uppercase tracking-wider font-semibold">
            Quick questions
          </p>
          <div className="flex flex-col gap-1">
            {QUICK_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setQuestion(p)
                  void submit(p)
                }}
                className="flex items-center gap-2 text-xs text-left px-3 py-2 rounded-lg border border-border text-slate-400 hover:bg-neutral-800 hover:text-white transition-colors"
              >
                <ChevronRight className="w-3 h-3 shrink-0 text-slate-600" />
                {p}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="flex gap-2">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={handleKey}
          placeholder="Ask anything about this service..."
          rows={2}
          disabled={loading}
          className="flex-1 bg-neutral-800 border border-border rounded-xl text-sm text-white placeholder-neutral-600 px-3 py-2 resize-none focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500/30 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={loading || !question.trim()}
          className="px-4 py-2 bg-indigo-600 text-white text-sm rounded-xl hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors self-end"
        >
          {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : 'Ask'}
        </button>
      </div>

      {loading && (
        <div className="flex flex-col items-center gap-3 py-8 text-slate-500">
          <Loader2 className="w-6 h-6 animate-spin text-indigo-400" />
          <span className="text-xs">Analyzing service data…</span>
        </div>
      )}

      {error && !loading && (
        <div className="flex items-start gap-2 p-3 rounded-xl border border-red-500/30 bg-red-500/10">
          <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          <div>
            <p className="text-xs text-red-400">{error}</p>
            <button
              type="button"
              onClick={() => void submit()}
              className="mt-1 text-[10px] text-red-500 underline hover:text-red-300"
            >
              Retry
            </button>
          </div>
        </div>
      )}

      {response && !loading && (
        <div className="flex flex-col gap-3">
          {response.answer && (
            <div className="p-3 rounded-xl border border-border bg-card">
              <p className="text-[10px] font-semibold text-indigo-400 uppercase tracking-wider mb-2">
                Answer
              </p>
              <p className="text-sm text-slate-200 leading-relaxed">{response.answer}</p>
            </div>
          )}

          {response.risks?.length > 0 && (
            <div className="p-3 rounded-xl border border-yellow-500/20 bg-yellow-500/5">
              <p className="text-[10px] font-semibold text-yellow-400 uppercase tracking-wider mb-2">
                ⚠ Risks
              </p>
              <ul className="flex flex-col gap-1.5">
                {response.risks.map((r, i) => (
                  <li key={i} className="flex gap-2 text-xs text-slate-300">
                    <span className="text-yellow-500 shrink-0">•</span>
                    {r}
                  </li>
                ))}
              </ul>
            </div>
          )}

          {response.recommended_actions?.length > 0 && (
            <div className="p-3 rounded-xl border border-green-500/20 bg-green-500/5">
              <p className="text-[10px] font-semibold text-green-400 uppercase tracking-wider mb-2">
                Recommended Actions
              </p>
              <ul className="flex flex-col gap-2">
                {response.recommended_actions.map((a, i) => {
                  const match = matchAction(a)
                  return (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className="flex gap-2 text-xs text-slate-300">
                        <span className="text-green-500 shrink-0">→</span>
                        {a}
                      </span>
                      {match && (
                        <Link
                          to="/entity-actions"
                          className="shrink-0 text-[10px] px-2 py-1 rounded bg-green-600/30 border border-green-500/30 text-green-300 hover:bg-green-600/50 transition-colors"
                        >
                          Run
                        </Link>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {response.suggested_workflows?.length > 0 && (
            <div className="p-3 rounded-xl border border-violet-500/20 bg-violet-500/5">
              <p className="text-[10px] font-semibold text-violet-400 uppercase tracking-wider mb-2">
                Suggested Workflows
              </p>
              <ul className="flex flex-col gap-2">
                {response.suggested_workflows.map((w, i) => {
                  const match = matchPath(w)
                  return (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className="flex gap-2 text-xs text-slate-300">
                        <span className="text-violet-500 shrink-0">⚡</span>
                        {w}
                      </span>
                      {match && (
                        <Link
                          to="/golden-paths"
                          className="shrink-0 text-[10px] px-2 py-1 rounded bg-violet-600/30 border border-violet-500/30 text-violet-300 hover:bg-violet-600/50 transition-colors"
                        >
                          Launch
                        </Link>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {response.data_sources_used?.length > 0 && (
            <p className="text-[10px] text-slate-600">
              Sources: {response.data_sources_used.join(', ')}
            </p>
          )}

          <button
            type="button"
            onClick={() => {
              setResponse(null)
              setQuestion('')
            }}
            className="text-[10px] text-slate-600 hover:text-slate-400 underline self-start transition-colors"
          >
            Ask another question
          </button>
        </div>
      )}
    </div>
  )
}
