import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot, ChevronDown, ChevronRight, Eye, Loader2, X,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const PAGE_SIZE = 20

function truncate(str, max = 60) {
  const s = String(str || '')
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

function formatDuration(run) {
  if (run.duration_ms != null) {
    const sec = Math.round(Number(run.duration_ms) / 1000)
    if (sec < 60) return `${sec}s`
    return `${Math.floor(sec / 60)}m ${sec % 60}s`
  }
  const start = run.timestamp ? new Date(run.timestamp).getTime() : NaN
  const end = run.updated_at ? new Date(run.updated_at).getTime() : NaN
  if (!Number.isNaN(start) && !Number.isNaN(end) && end >= start) {
    const sec = Math.round((end - start) / 1000)
    if (sec < 60) return `${sec}s`
    return `${Math.floor(sec / 60)}m ${sec % 60}s`
  }
  return '—'
}

function StatusBadge({ status }) {
  const s = (status || '').toLowerCase()
  if (s === 'success') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        success
      </span>
    )
  }
  if (s === 'failed') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
        failed
      </span>
    )
  }
  if (s === 'pending_approval') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 animate-pulse">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        pending
      </span>
    )
  }
  if (s === 'running') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
        <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
        running
      </span>
    )
  }
  return (
    <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-neutral-700/50 text-neutral-400 border border-neutral-600">
      {status || '—'}
    </span>
  )
}

function CollapsibleJson({ label, data }) {
  const [open, setOpen] = useState(false)
  const text = data == null ? '{}' : JSON.stringify(data, null, 2)

  return (
    <div className="rounded-lg border border-neutral-800 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 w-full px-3 py-2 text-left text-xs font-semibold text-neutral-300 bg-neutral-950 hover:bg-neutral-900 transition-colors"
      >
        {open ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
        {label}
      </button>
      {open && (
        <pre className="px-3 py-2 text-[11px] font-mono text-neutral-400 bg-black/40 overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap">
          {text}
        </pre>
      )}
    </div>
  )
}

function RunDetailDrawer({ run, onClose }) {
  if (!run) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="w-full max-w-lg bg-neutral-900 border-l border-neutral-800 h-full flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800">
          <div className="flex items-center gap-2 min-w-0">
            <Bot className="w-5 h-5 text-indigo-400 shrink-0" />
            <div className="min-w-0">
              <h3 className="font-semibold text-white truncate">{run.agent}</h3>
              <p className="text-[11px] text-neutral-500 truncate">{run.run_id}</p>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg text-neutral-500 hover:text-white hover:bg-neutral-800"
            aria-label="Close drawer"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5 flex flex-col gap-4">
          <div className="flex flex-wrap gap-2 items-center">
            <StatusBadge status={run.status} />
            <span className="text-[11px] text-neutral-500">{run.environment}</span>
          </div>

          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">Task</p>
            <p className="text-sm text-neutral-200 leading-relaxed">{run.task || '—'}</p>
          </div>

          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">Summary</p>
            <p className="text-sm text-neutral-300 leading-relaxed">{run.summary || '—'}</p>
          </div>

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-neutral-500 mb-0.5">Triggered by</p>
              <p className="text-neutral-300">{run.triggered_by || '—'}</p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">Workspace</p>
              <p className="text-neutral-300">{run.workspace || '—'}</p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">Started</p>
              <p className="text-neutral-300">
                {run.timestamp ? new Date(run.timestamp).toLocaleString() : '—'}
              </p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">Duration</p>
              <p className="text-neutral-300">{formatDuration(run)}</p>
            </div>
          </div>

          {run.execution_log && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">Execution log</p>
              <pre className="text-[11px] font-mono text-emerald-400/90 bg-black/50 border border-neutral-800 rounded-lg p-3 overflow-x-auto max-h-40 whitespace-pre-wrap">
                {run.execution_log}
              </pre>
            </div>
          )}

          <CollapsibleJson label="details JSON" data={run.details} />
          <CollapsibleJson label="approval_payload JSON" data={run.approval_payload} />
        </div>
      </div>
    </div>
  )
}

export default function AgentRunHistory() {
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { toast } = useToast()
  const [runs, setRuns] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [drawerRun, setDrawerRun] = useState(null)

  const fetchPage = useCallback(
    async (pageNum, append = false) => {
      if (append) setLoadingMore(true)
      else setLoading(true)

      try {
        const res = await authFetch(
          `/api/agents/runs?page=${pageNum}&page_size=${PAGE_SIZE}`
        )
        if (!res.ok) {
          if (!append) setRuns([])
          if (res.status !== 404) {
            toast.error('Failed to load agent run history')
          }
          return
        }
        const data = await res.json()
        const items = Array.isArray(data) ? data : (data.items || data.runs || [])
        const count = data.total ?? items.length

        setRuns((prev) => (append ? [...prev, ...items] : items))
        setTotal(count)
        setPage(pageNum)
      } catch {
        if (!append) setRuns([])
        toast.error('Failed to load agent run history')
      } finally {
        setLoading(false)
        setLoadingMore(false)
      }
    },
    [authFetch, toast]
  )

  useEffect(() => {
    void fetchPage(1, false)
  }, [fetchPage])

  const hasMore = runs.length < total

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-xl border border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 bg-neutral-950/80 text-left">
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Time</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Agent</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Task</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Status</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Duration</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500 w-16">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-4 py-10 text-center text-neutral-500">
                    <Loader2 className="w-5 h-5 animate-spin inline-block mr-2 text-indigo-400" />
                    Loading history…
                  </td>
                </tr>
              ) : runs.length === 0 ? (
                <tr>
                  <td colSpan={6} className="p-0">
                    <EmptyState
                      icon="🤖"
                      title="No agent runs yet."
                      action={{
                        label: 'Run your first agent →',
                        onClick: () => navigate('/agents'),
                      }}
                    />
                  </td>
                </tr>
              ) : (
                runs.map((run) => (
                  <tr
                    key={run.run_id || `${run.agent}-${run.timestamp}`}
                    className="border-b border-neutral-800/80 hover:bg-neutral-900/50 transition-colors"
                  >
                    <td className="px-4 py-3 text-xs text-neutral-400 whitespace-nowrap">
                      {run.timestamp ? new Date(run.timestamp).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-200 font-medium whitespace-nowrap">
                      {run.agent}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400 max-w-[240px]" title={run.task}>
                      {truncate(run.task, 60)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400 whitespace-nowrap">
                      {formatDuration(run)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setDrawerRun(run)}
                        className="p-1.5 rounded-lg text-neutral-500 hover:text-indigo-400 hover:bg-neutral-800 transition-colors"
                        title="View details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {hasMore && (
        <button
          type="button"
          disabled={loadingMore}
          onClick={() => void fetchPage(page + 1, true)}
          className="self-center px-4 py-2 rounded-lg border border-neutral-700 text-sm text-neutral-300 hover:bg-neutral-800 disabled:opacity-50 transition-colors"
        >
          {loadingMore ? (
            <span className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin" /> Loading…
            </span>
          ) : (
            'Load More'
          )}
        </button>
      )}

      {drawerRun && (
        <RunDetailDrawer run={drawerRun} onClose={() => setDrawerRun(null)} />
      )}
    </div>
  )
}
