import { useCallback, useEffect, useState } from 'react'
import { AlertCircle, BookOpen, Loader2, RefreshCw, ShieldAlert } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function MCPToolsCatalog() {
  const { authFetch } = useAuth()
  const [tools, setTools] = useState([])
  const [errors, setErrors] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/mcp/tools')
      if (!res.ok) throw new Error('Failed to load MCP tools')
      const data = await res.json()
      setTools(data.tools || [])
      setErrors(data.errors || [])
    } catch (e) {
      setError(e.message || 'Failed to load MCP tools')
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <BookOpen className="w-3.5 h-3.5 text-amber-400" />
          MCP Tools Catalog
        </div>
        <button
          type="button"
          onClick={load}
          disabled={loading}
          className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-white"
        >
          {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />}
          Refresh
        </button>
      </div>
      <p className="text-[11px] text-slate-500">
        Read-only view of tools discovered from enabled MCP servers. Write tools require HITL approval.
      </p>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      {errors.length > 0 && (
        <div className="text-[10px] text-amber-400/90 border border-amber-500/30 rounded-lg p-2 bg-amber-500/5">
          {errors.map((e) => (
            <div key={`${e.server_id}-${e.error}`}>
              {e.server_name}: {e.error}
            </div>
          ))}
        </div>
      )}

      {loading && tools.length === 0 && (
        <p className="text-[11px] text-slate-600">Discovering tools…</p>
      )}
      {!loading && tools.length === 0 && (
        <p className="text-[11px] text-slate-600">No tools discovered. Add and enable an MCP server above.</p>
      )}

      <div className="flex flex-col gap-1.5 max-h-48 overflow-y-auto">
        {tools.map((tool) => (
          <div
            key={`${tool.server_id}:${tool.name}`}
            className="px-3 py-2 rounded-lg border border-border bg-card"
          >
            <div className="flex items-center justify-between gap-2">
              <div className="text-xs font-semibold text-slate-200 truncate">{tool.name}</div>
              <div className="flex items-center gap-1 shrink-0">
                {tool.require_approval ? (
                  <span className="inline-flex items-center gap-0.5 text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-amber-500/15 text-amber-300 border border-amber-500/30">
                    <ShieldAlert className="w-2.5 h-2.5" /> approval
                  </span>
                ) : (
                  <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
                    read-only
                  </span>
                )}
              </div>
            </div>
            <div className="text-[10px] text-slate-500 truncate">
              {tool.server_name}
              {tool.description ? ` · ${tool.description}` : ''}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
