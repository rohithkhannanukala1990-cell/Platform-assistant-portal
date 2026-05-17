import { useState, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const QUICK_PROMPTS = [
  'Why is this service not production ready?',
  'What should this team fix first?',
  'What dependencies make this service risky?',
  'Show me the top 3 action recommendations',
]

function healthBadgeClass(status) {
  if (status === 'healthy') return 'bg-green-900 text-green-300'
  if (status === 'degraded') return 'bg-yellow-900 text-yellow-300'
  return 'bg-red-900 text-red-300'
}

export default function CatalogCopilotPanel({
  entity,
  entityActions = [],
  goldenPaths = [],
}) {
  const navigate = useNavigate()
  const { authFetch } = useAuth()

  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)

  const submit = useCallback(
    async (q) => {
      const text = (typeof q === 'string' ? q : question).trim()
      if (!text) return
      setQuestion(text)
      setLoading(true)
      setError(null)
      setResponse(null)
      try {
        const res = await authFetch('/api/catalog-copilot/copilot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: text,
            entity_id: entity?.id || null,
            team: entity?.owner_team || null,
          }),
        })
        if (!res.ok) throw new Error(`Error ${res.status}`)
        setResponse(await res.json())
      } catch (e) {
        setError(e.message || 'Failed to reach AI. Please try again.')
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
    <div className="flex flex-col gap-4 h-full overflow-y-auto -mx-1 px-1">
      {entity && (
        <div className="flex items-start gap-3 p-3 bg-slate-900 rounded-lg border border-border">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-white text-sm truncate">{entity.name}</span>
              <span className="px-1.5 py-0.5 text-xs rounded bg-blue-900 text-blue-300">
                {entity.kind}
              </span>
              <span className={`px-1.5 py-0.5 text-xs rounded ${healthBadgeClass(entity.health_status)}`}>
                {entity.health_status || 'unknown'}
              </span>
            </div>
            <div className="text-xs text-slate-400 mt-1">
              {entity.owner_team && `Owner: ${entity.owner_team}`}
              {entity.lifecycle && ` · ${entity.lifecycle}`}
            </div>
          </div>
        </div>
      )}

      {!loading && !response && (
        <div>
          <p className="text-xs text-slate-500 mb-2">Quick questions:</p>
          <div className="flex flex-wrap gap-2">
            {QUICK_PROMPTS.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => {
                  setQuestion(p)
                  void submit(p)
                }}
                disabled={loading}
                className="text-xs px-3 py-1.5 rounded-full border border-border bg-slate-900 text-slate-300 hover:bg-slate-800 hover:text-white transition-colors disabled:opacity-50"
              >
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
          className="flex-1 bg-slate-900 border border-border rounded-lg text-sm text-white placeholder-slate-500 px-3 py-2 resize-none focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void submit()}
          disabled={loading || !question.trim()}
          className="px-4 py-2 bg-blue-600 text-white text-sm rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors self-end"
        >
          {loading ? '...' : 'Ask'}
        </button>
      </div>

      {loading && (
        <div className="flex flex-col items-center gap-3 py-8 text-slate-400">
          <Loader2 className="w-6 h-6 text-blue-500 animate-spin" />
          <span className="text-sm">Analyzing service data...</span>
        </div>
      )}

      {error && !loading && (
        <div className="p-3 bg-red-950/50 border border-red-800 rounded-lg text-sm">
          <p className="text-red-400">{error}</p>
          <button
            type="button"
            onClick={() => void submit()}
            className="mt-2 text-xs text-red-300 underline hover:text-red-200"
          >
            Retry
          </button>
        </div>
      )}

      {response && !loading && (
        <div className="flex flex-col gap-4">
          {response.answer && (
            <div className="p-3 bg-slate-900 rounded-lg border border-border">
              <h4 className="text-xs font-semibold text-blue-400 uppercase tracking-wider mb-2">
                Answer
              </h4>
              <p className="text-sm text-slate-200 leading-relaxed">{response.answer}</p>
            </div>
          )}

          {response.risks?.length > 0 && (
            <div className="p-3 bg-slate-900 rounded-lg border border-border">
              <h4 className="text-xs font-semibold text-yellow-400 uppercase tracking-wider mb-2">
                Risks
              </h4>
              <ul className="flex flex-col gap-1.5">
                {response.risks.map((r, i) => (
                  <li key={i} className="flex gap-2 text-sm text-slate-300">
                    <span className="text-yellow-500 mt-0.5 shrink-0">•</span>
                    <span>{r}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {response.recommended_actions?.length > 0 && (
            <div className="p-3 bg-slate-900 rounded-lg border border-border">
              <h4 className="text-xs font-semibold text-green-400 uppercase tracking-wider mb-2">
                Recommended Actions
              </h4>
              <ul className="flex flex-col gap-2">
                {response.recommended_actions.map((a, i) => {
                  const match = matchAction(a)
                  return (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className="text-sm text-slate-300 flex gap-2">
                        <span className="text-green-500 mt-0.5 shrink-0">→</span>
                        {a}
                      </span>
                      {match && (
                        <button
                          type="button"
                          onClick={() => navigate('/entity-actions')}
                          className="shrink-0 text-xs px-2 py-1 bg-green-800 text-green-100 rounded hover:bg-green-700 transition-colors"
                        >
                          Run
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {response.suggested_workflows?.length > 0 && (
            <div className="p-3 bg-slate-900 rounded-lg border border-border">
              <h4 className="text-xs font-semibold text-purple-400 uppercase tracking-wider mb-2">
                Suggested Workflows
              </h4>
              <ul className="flex flex-col gap-2">
                {response.suggested_workflows.map((w, i) => {
                  const match = matchPath(w)
                  return (
                    <li key={i} className="flex items-center justify-between gap-2">
                      <span className="text-sm text-slate-300 flex gap-2">
                        <span className="text-purple-400 mt-0.5 shrink-0">⚡</span>
                        {w}
                      </span>
                      {match && (
                        <button
                          type="button"
                          onClick={() => navigate('/golden-paths')}
                          className="shrink-0 text-xs px-2 py-1 bg-purple-800 text-purple-100 rounded hover:bg-purple-700 transition-colors"
                        >
                          Launch
                        </button>
                      )}
                    </li>
                  )
                })}
              </ul>
            </div>
          )}

          {response.data_sources_used?.length > 0 && (
            <p className="text-xs text-slate-600">
              Sources: {response.data_sources_used.join(', ')}
            </p>
          )}

          <button
            type="button"
            onClick={() => {
              setResponse(null)
              setQuestion('')
            }}
            className="text-xs text-slate-500 hover:text-slate-300 underline self-start"
          >
            Ask another question
          </button>
        </div>
      )}
    </div>
  )
}
