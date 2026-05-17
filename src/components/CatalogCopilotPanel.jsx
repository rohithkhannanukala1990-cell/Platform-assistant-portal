import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, AlertTriangle, ChevronRight, Sparkles } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const QUICK_PROMPTS = [
  'Why is this service not production ready?',
  'What should this team fix first?',
  'What dependencies make this service risky?',
  'Which action or workflow should I run next?',
]

function healthDotClass(status) {
  if (status === 'healthy') return 'bg-green-400'
  if (status === 'degraded') return 'bg-yellow-400'
  if (status === 'unhealthy') return 'bg-red-400'
  return 'bg-gray-400'
}

export default function CatalogCopilotPanel({ entity, token: tokenProp }) {
  const navigate = useNavigate()
  const { authFetch, token: contextToken } = useAuth()
  const token = tokenProp || contextToken

  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [response, setResponse] = useState(null)
  const [error, setError] = useState(null)

  const handleSubmit = async (q) => {
    const text = (typeof q === 'string' ? q : question).trim()
    if (!text) return
    setQuestion(text)
    setLoading(true)
    setError(null)
    setResponse(null)
    try {
      const headers = { 'Content-Type': 'application/json' }
      if (token) headers.Authorization = `Bearer ${token}`

      let res
      if (authFetch && !tokenProp) {
        res = await authFetch('/api/catalog-copilot/copilot', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question: text,
            entity_id: entity?.id || null,
          }),
        })
      } else {
        res = await fetch('/api/catalog-copilot/copilot', {
          method: 'POST',
          headers,
          body: JSON.stringify({
            question: text,
            entity_id: entity?.id || null,
          }),
        })
      }
      if (!res.ok) {
        const errText = await res.text()
        throw new Error(errText || `HTTP ${res.status}`)
      }
      setResponse(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to get AI response')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col min-h-[360px]">
      {entity && (
        <div className="flex items-center gap-2 mb-4 pb-4 border-b border-white/5">
          <div className={`w-2 h-2 rounded-full shrink-0 ${healthDotClass(entity.health_status)}`} />
          <span className="text-sm font-medium text-white truncate">{entity.name}</span>
          <span className="text-xs text-gray-500 shrink-0">{entity.kind}</span>
          {entity.owner_team && (
            <span className="ml-auto text-xs text-gray-500 truncate">{entity.owner_team}</span>
          )}
        </div>
      )}

      <div className="mb-4">
        <p className="text-xs text-gray-500 mb-2">Quick questions</p>
        <div className="grid grid-cols-1 gap-2">
          {QUICK_PROMPTS.map((prompt) => (
            <button
              key={prompt}
              type="button"
              onClick={() => void handleSubmit(prompt)}
              disabled={loading}
              className="text-left text-xs px-3 py-2 bg-white/[0.03] hover:bg-white/[0.08] border border-white/[0.08] hover:border-white/15 rounded-lg text-gray-400 hover:text-gray-200 transition-all disabled:opacity-40"
            >
              {prompt}
            </button>
          ))}
        </div>
      </div>

      <div className="flex gap-2 mb-4">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter') void handleSubmit()
          }}
          placeholder="Ask anything about this service..."
          disabled={loading}
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500/50 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => void handleSubmit()}
          disabled={loading || !question.trim()}
          className="px-3 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded-lg text-sm transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
        >
          Ask
        </button>
      </div>

      {loading && (
        <div className="flex flex-col items-center justify-center py-10 flex-1">
          <Loader2 size={28} className="text-blue-400 animate-spin mb-3" />
          <p className="text-sm text-gray-400">Analyzing service data...</p>
          <p className="text-xs text-gray-600 mt-1">Checking scorecards, standards, incidents</p>
        </div>
      )}

      {error && !loading && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-4">
          <p className="text-red-300 text-sm">{error}</p>
        </div>
      )}

      {response && !loading && (
        <div className="space-y-4 overflow-y-auto flex-1 max-h-[50vh]">
          <div className="bg-white/[0.03] border border-white/[0.08] rounded-lg p-4">
            <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Answer</p>
            <p className="text-sm text-gray-200 leading-relaxed">{response.answer}</p>
          </div>

          {response.risks?.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">Identified Risks</p>
              <div className="space-y-1.5">
                {response.risks.map((risk, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-sm text-red-300 bg-red-500/5 border border-red-500/10 rounded-lg px-3 py-2"
                  >
                    <AlertTriangle size={13} className="mt-0.5 shrink-0" />
                    {risk}
                  </div>
                ))}
              </div>
            </div>
          )}

          {response.recommended_actions?.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">
                Recommended Actions
              </p>
              <div className="space-y-1.5">
                {response.recommended_actions.map((action, i) => (
                  <div
                    key={i}
                    className="flex items-start gap-2 text-sm text-blue-300 bg-blue-500/5 border border-blue-500/10 rounded-lg px-3 py-2"
                  >
                    <ChevronRight size={13} className="mt-0.5 shrink-0" />
                    {action}
                  </div>
                ))}
              </div>
            </div>
          )}

          {response.suggested_workflows?.length > 0 && (
            <div>
              <p className="text-xs text-gray-500 mb-2 uppercase tracking-wider">
                Suggested Workflows
              </p>
              <div className="flex flex-wrap gap-2">
                {response.suggested_workflows.map((wf, i) => (
                  <button
                    key={i}
                    type="button"
                    onClick={() => navigate('/golden-paths')}
                    className="px-3 py-1.5 bg-purple-500/10 hover:bg-purple-500/20 border border-purple-500/20 text-purple-300 text-xs rounded-lg transition-colors"
                  >
                    {wf} →
                  </button>
                ))}
              </div>
            </div>
          )}

          {response.data_sources_used?.length > 0 && (
            <p className="text-xs text-gray-600 pt-2">
              Sources: {response.data_sources_used.join(', ')}
            </p>
          )}
        </div>
      )}

      {!loading && !response && !error && (
        <div className="flex flex-col items-center justify-center py-10 flex-1">
          <Sparkles size={32} className="text-gray-600 mb-3" />
          <p className="text-gray-500 text-sm">Ask a question about this service</p>
          <p className="text-gray-600 text-xs mt-1">Uses scorecards, standards, and incident data</p>
        </div>
      )}
    </div>
  )
}
