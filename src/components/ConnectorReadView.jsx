import { Link } from 'react-router-dom'
import { Loader2, RefreshCw, Wrench } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

function EmptyConnected({ toolLabel }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-6 text-center border border-dashed border-border rounded-xl bg-card/40">
      <Wrench className="w-8 h-8 text-slate-500 mb-3" />
      <p className="text-sm font-semibold text-slate-200">{toolLabel} not connected</p>
      <p className="text-xs text-slate-500 mt-1 max-w-sm">
        Add credentials in Tool Registry. First-class connectors use scoped accounts — not MCP.
      </p>
      <Link
        to="/tool-registry"
        className="mt-4 px-3 py-1.5 text-xs font-semibold rounded-lg bg-accent/15 border border-accent/40 text-accent hover:bg-accent/25"
      >
        Connect {toolLabel} in Tool Registry
      </Link>
    </div>
  )
}

/**
 * Shared read-first connector panel with Tool Registry empty state.
 * @param {{ title: string, toolLabel: string, endpoint: string, columns: {key:string,label:string}[], icon?: import('lucide-react').LucideIcon }} props
 */
export default function ConnectorReadView({ title, toolLabel, endpoint, columns, icon: Icon }) {
  const { authFetch } = useAuth()
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [notConnected, setNotConnected] = useState(false)
  const [error, setError] = useState(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    setNotConnected(false)
    try {
      const res = await authFetch(endpoint)
      if (res.status === 400) {
        setNotConnected(true)
        setRows([])
        return
      }
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRows(Array.isArray(data) ? data : data?.result || [])
    } catch (e) {
      setError(e.message || `Failed to load ${toolLabel}`)
    } finally {
      setLoading(false)
    }
  }, [authFetch, endpoint, toolLabel])

  useEffect(() => {
    void load()
  }, [load])

  if (loading && !rows.length && !notConnected) {
    return (
      <div className="flex items-center justify-center py-20 text-slate-500 gap-2 text-sm">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading {toolLabel}…
      </div>
    )
  }

  if (notConnected) {
    return (
      <div className="p-4 md:p-6 max-w-5xl mx-auto">
        <h1 className="text-lg font-semibold text-white mb-4">{title}</h1>
        <EmptyConnected toolLabel={toolLabel} />
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-4 p-4 md:p-6 max-w-5xl mx-auto w-full">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-white flex items-center gap-2">
            {Icon ? <Icon className="w-5 h-5 text-accent" /> : null}
            {title}
          </h1>
          <p className="text-xs text-slate-500 mt-0.5">First-class connector · scoped ToolAccount</p>
        </div>
        <button
          type="button"
          onClick={() => load()}
          className="inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border text-xs text-slate-400 hover:text-white"
        >
          <RefreshCw className={`w-3 h-3 ${loading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-card text-slate-500 uppercase tracking-wider">
            <tr>
              {columns.map((c) => (
                <th key={c.key} className="px-3 py-2 font-semibold">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {!rows.length ? (
              <tr>
                <td colSpan={columns.length} className="px-3 py-8 text-center text-slate-500">
                  No data returned.
                </td>
              </tr>
            ) : (
              rows.map((row, i) => (
                <tr key={row.id || row.name || i} className="hover:bg-card/50">
                  {columns.map((c) => (
                    <td key={c.key} className="px-3 py-2 text-slate-300">
                      {String(row[c.key] ?? '—')}
                    </td>
                  ))}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
