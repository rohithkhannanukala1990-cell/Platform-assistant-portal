import { useState, useCallback } from 'react'
import { Link } from 'react-router-dom'
import { Sparkles, AlertTriangle, ChevronRight, Loader2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'

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

export default function CatalogCopilotPanel({
  entity,
  entityActions = [],
  goldenPaths = [],
}) {
  const { authFetch } = useAuth()
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)

  const submit = useCallback(
    async (q) => {
      const text = (typeof q === 'string' ? q : question).trim()
      if (!text) return
      setLoading(true)
      setError(null)
      setResponse(null)
      try {
        const res = await authFetch(COPILOT_API, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: text,
            entity_id: entity?.id ?? null,
            team: entity?.owner_team ?? null,
          }),
        })
        if (!res.ok) throw new Error(`Error ${res.status}`)
        setResponse(await res.json())
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
