import { useCallback, useEffect, useState } from 'react'
import { Link2, Loader2, RefreshCw, Slack } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function SlackAccountLinkPanel() {
  const { authFetch } = useAuth()
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)
  const [generating, setGenerating] = useState(false)
  const [code, setCode] = useState(null)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await authFetch('/api/integrations/slack/link/status')
      if (!res.ok) throw new Error('Failed to load Slack link status')
      setStatus(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load Slack link status')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  async function generateCode() {
    setGenerating(true)
    setError(null)
    try {
      const res = await authFetch('/api/integrations/slack/link/start', { method: 'POST' })
      if (!res.ok) throw new Error('Failed to generate code')
      setCode(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to generate code')
    } finally {
      setGenerating(false)
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2">
        <Slack className="w-4 h-4 text-violet-400" />
        <h3 className="text-xs font-bold text-white uppercase tracking-wide">
          Slack account linking
        </h3>
        <span className="text-[10px] text-slate-500">Required to approve from Slack</span>
      </div>

      {error && <p className="text-xs text-red-400">{error}</p>}

      {loading ? (
        <div className="flex items-center gap-2 text-xs text-slate-500">
          <Loader2 className="w-3.5 h-3.5 animate-spin" /> Loading…
        </div>
      ) : status?.linked ? (
        <div className="flex items-center justify-between rounded-lg border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-300">
          <span>Linked to Slack user {status.slack_user_id}</span>
          <button
            className="flex items-center gap-1 text-slate-400 hover:text-white"
            onClick={() => void load()}
          >
            <RefreshCw className="h-3 w-3" />
          </button>
        </div>
      ) : (
        <div className="space-y-2 text-xs text-slate-400">
          <p>
            Link your Slack account to approve HITL requests directly from Slack messages.
          </p>
          {code ? (
            <div className="rounded-lg border border-border bg-slate-950/60 p-3">
              <p className="text-slate-300">In Slack, send:</p>
              <code className="mt-1 block rounded bg-slate-900 px-2 py-1 text-violet-300">
                /portal-link {code.code}
              </code>
              <p className="mt-1 text-[10px] text-slate-500">
                Expires {new Date(code.expires_at).toLocaleTimeString()}
              </p>
            </div>
          ) : (
            <button
              className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1.5 font-semibold text-slate-200 hover:bg-white/5 disabled:opacity-50"
              disabled={generating}
              onClick={() => void generateCode()}
            >
              {generating ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Link2 className="h-3.5 w-3.5" />}
              Generate linking code
            </button>
          )}
        </div>
      )}
    </div>
  )
}
