import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Bot, ChevronDown, ChevronRight, Eye, Loader2, X,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import { useToast } from './ToastNotification'
import { GroundingBadge } from './agent/AgentRunBadges'
import { parseApiError } from '../utils/parseApiError'

const PAGE_SIZE = 20

const AI_STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending_approval', label: 'pending_approval' },
  { value: 'executing', label: 'executing' },
  { value: 'completed', label: 'completed' },
  { value: 'error', label: 'error' },
]

const AGENT_STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'pending_approval', label: 'pending_approval' },
  { value: 'running', label: 'running' },
  { value: 'success', label: 'success' },
  { value: 'failed', label: 'failed' },
]

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

function EmptyState({ icon, title, action }) {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <span className="text-3xl mb-3" aria-hidden>{icon}</span>
      <p className="text-sm text-neutral-400 mb-3">{title}</p>
      {action && (
        <button
          type="button"
          onClick={action.onClick}
          className="text-sm text-indigo-400 hover:text-indigo-300 font-semibold"
        >
          {action.label}
        </button>
      )}
    </div>
  )
}

function StatusBadge({ status }) {
  const s = (status || '').toLowerCase()
  if (s === 'success' || s === 'completed') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
        {s}
      </span>
    )
  }
  if (s === 'failed' || s === 'error') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
        <span className="w-1.5 h-1.5 rounded-full bg-red-400" />
        {s}
      </span>
    )
  }
  if (s === 'skipped') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-neutral-700/50 text-neutral-300 border border-neutral-600">
        skipped
      </span>
    )
  }
  if (s === 'pending_approval') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30 animate-pulse">
        <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />
        pending_approval
      </span>
    )
  }
  if (s === 'running' || s === 'executing') {
    return (
      <span className="inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
        <Loader2 className="w-3 h-3 animate-spin text-blue-400" />
        {s}
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

function executionSummary(ex) {
  const result = ex.result || {}
  if (typeof result.output === 'string' && result.output.trim()) return result.output
  if (result.output != null) {
    try {
      return JSON.stringify(result.output)
    } catch {
      return String(result.output)
    }
  }
  if (result.error) return String(result.error)
  if (result.message) return String(result.message)
  return `${ex.tool_id || 'tool'} → ${ex.action || 'action'}`
}

function RunDetailDrawer({ run, onClose, mode }) {
  if (!run) return null
  const isAi = mode === 'ai'

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/50">
      <div className="w-full max-w-lg bg-neutral-900 border-l border-neutral-800 h-full flex flex-col shadow-2xl">
        <div className="flex items-center justify-between px-5 py-4 border-b border-neutral-800">
          <div className="flex items-center gap-2 min-w-0">
            <Bot className="w-5 h-5 text-indigo-400 shrink-0" />
            <div className="min-w-0">
              <h3 className="font-semibold text-white truncate">
                {isAi ? `${run.tool_id} → ${run.action}` : run.agent}
              </h3>
              <p className="text-[11px] text-neutral-500 truncate">
                {isAi ? run.id : run.run_id}
              </p>
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
            {!isAi && <GroundingBadge grounding={run.details?.grounding || run.grounding} />}
            <span className="text-[11px] text-neutral-500">
              {isAi
                ? (run.environment || run.conversation_context?.environment || '—')
                : run.environment}
            </span>
            {isAi && run.requires_hitl && (
              <span className="text-[10px] px-2 py-0.5 rounded-md border border-amber-500/40 text-amber-200">
                HITL
              </span>
            )}
          </div>

          {!isAi && (run.details?.grounding || run.grounding) === 'none' && (
            <p className="text-[11px] text-amber-300/90">
              No live connector data.{' '}
              <a href="/tools" className="underline hover:text-amber-200">Open Tool Registry</a>
            </p>
          )}

          {!isAi && (run.status === 'failed' || run.status === 'error') && (
            <p className="text-[11px] text-red-300/90 border border-red-500/20 bg-red-500/10 rounded-lg px-2 py-1.5">
              {run.summary || run.details?.error || 'Run failed'}
            </p>
          )}

          {!isAi && Array.isArray(run.details?.evidence) && run.details.evidence.length > 0 && (
            <CollapsibleJson label={`evidence (${run.details.evidence.length})`} data={run.details.evidence} />
          )}
          {!isAi && run.details?.policy && (
            <CollapsibleJson label="policy summary" data={run.details.policy} />
          )}

          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">
              {isAi ? 'Summary (result.output)' : 'Task'}
            </p>
            <p className="text-sm text-neutral-200 leading-relaxed">
              {isAi ? executionSummary(run) : (run.task || '—')}
            </p>
          </div>

          {!isAi && (
            <div>
              <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">Summary</p>
              <p className="text-sm text-neutral-300 leading-relaxed">{run.summary || '—'}</p>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <p className="text-neutral-500 mb-0.5">{isAi ? 'Conversation' : 'Triggered by'}</p>
              <p className="text-neutral-300">
                {isAi
                  ? (run.conversation_context?.title || run.conversation_id || '—')
                  : (run.triggered_by || '—')}
              </p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">Workspace</p>
              <p className="text-neutral-300">
                {isAi
                  ? (run.conversation_context?.workspace_id || '—')
                  : (run.workspace || '—')}
              </p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">Created</p>
              <p className="text-neutral-300">
                {run.created_at || run.timestamp
                  ? new Date(run.created_at || run.timestamp).toLocaleString()
                  : '—'}
              </p>
            </div>
            <div>
              <p className="text-neutral-500 mb-0.5">{isAi ? 'Executed' : 'Duration'}</p>
              <p className="text-neutral-300">
                {isAi
                  ? (run.executed_at ? new Date(run.executed_at).toLocaleString() : '—')
                  : formatDuration(run)}
              </p>
            </div>
          </div>

          {isAi ? (
            <CollapsibleJson label="result JSON" data={run.result} />
          ) : (
            <>
              {run.execution_log && (
                <div>
                  <p className="text-[10px] font-bold uppercase tracking-wider text-neutral-500 mb-1">
                    Execution log
                  </p>
                  <pre className="text-[11px] font-mono text-emerald-400/90 bg-black/50 border border-neutral-800 rounded-lg p-3 overflow-x-auto max-h-40 whitespace-pre-wrap">
                    {run.execution_log}
                  </pre>
                </div>
              )}
              <CollapsibleJson label="details JSON" data={run.details} />
              <CollapsibleJson label="approval_payload JSON" data={run.approval_payload} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function AgentRunHistory() {
  const navigate = useNavigate()
  const { authFetch, role } = useAuth()
  const { activeWorkspace } = usePortalContext()
  const { toast } = useToast()
  const isAdmin = role === 'Admin'

  const [source, setSource] = useState(isAdmin ? 'ai' : 'agents')
  const [statusFilter, setStatusFilter] = useState('')
  const [workspaceFilter, setWorkspaceFilter] = useState(
    () => activeWorkspace?.id || ''
  )
  const [runs, setRuns] = useState([])
  const [aiExecutions, setAiExecutions] = useState([])
  const [page, setPage] = useState(1)
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [drawerItem, setDrawerItem] = useState(null)

  useEffect(() => {
    if (activeWorkspace?.id && !workspaceFilter) {
      setWorkspaceFilter(activeWorkspace.id)
    }
  }, [activeWorkspace?.id, workspaceFilter])

  const fetchAiExecutions = useCallback(async () => {
    if (!isAdmin) {
      setAiExecutions([])
      return
    }
    setLoading(true)
    try {
      const params = new URLSearchParams({ limit: '100' })
      if (statusFilter) params.set('status', statusFilter)
      if (workspaceFilter) params.set('workspace_id', workspaceFilter)
      const res = await authFetch(`/api/ai/executions?${params}`)
      if (!res.ok) {
        setAiExecutions([])
        if (res.status !== 403) {
          toast.error(await parseApiError(res, 'Failed to load AI executions'))
        }
        return
      }
      setAiExecutions(await res.json())
    } catch {
      setAiExecutions([])
      toast.error('Failed to load AI executions')
    } finally {
      setLoading(false)
    }
  }, [authFetch, isAdmin, statusFilter, workspaceFilter, toast])

  const fetchAgentPage = useCallback(
    async (pageNum, append = false) => {
      if (append) setLoadingMore(true)
      else setLoading(true)

      try {
        const params = new URLSearchParams({
          page: String(pageNum),
          page_size: String(PAGE_SIZE),
        })
        if (statusFilter) params.set('status', statusFilter)
        if (workspaceFilter) params.set('workspace_id', workspaceFilter)
        const res = await authFetch(`/api/agents/runs?${params}`)
        if (!res.ok) {
          if (!append) setRuns([])
          if (res.status !== 404) {
            toast.error(await parseApiError(res, 'Failed to load agent run history'))
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
    [authFetch, statusFilter, workspaceFilter, toast]
  )

  useEffect(() => {
    if (source === 'ai') void fetchAiExecutions()
    else void fetchAgentPage(1, false)
  }, [source, fetchAiExecutions, fetchAgentPage])

  const statusOptions = source === 'ai' ? AI_STATUS_OPTIONS : AGENT_STATUS_OPTIONS
  const hasMore = source === 'agents' && runs.length < total

  const workspaceOptions = useMemo(() => {
    const ids = new Set()
    if (activeWorkspace?.id) ids.add(activeWorkspace.id)
    for (const ex of aiExecutions) {
      const wid = ex.conversation_context?.workspace_id
      if (wid) ids.add(wid)
    }
    for (const run of runs) {
      if (run.workspace) ids.add(run.workspace)
    }
    return Array.from(ids)
  }, [activeWorkspace?.id, aiExecutions, runs])

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-2">
        <div className="inline-flex rounded-lg border border-neutral-700 overflow-hidden">
          <button
            type="button"
            onClick={() => setSource('ai')}
            disabled={!isAdmin}
            className={`px-3 py-1.5 text-xs font-semibold ${
              source === 'ai'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-900 text-neutral-400 hover:text-white'
            } disabled:opacity-40`}
          >
            AI executions
          </button>
          <button
            type="button"
            onClick={() => setSource('agents')}
            className={`px-3 py-1.5 text-xs font-semibold ${
              source === 'agents'
                ? 'bg-indigo-600 text-white'
                : 'bg-neutral-900 text-neutral-400 hover:text-white'
            }`}
          >
            Agent pipeline
          </button>
        </div>

        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="text-xs px-2 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-neutral-200"
        >
          {statusOptions.map((o) => (
            <option key={o.value || 'all'} value={o.value}>{o.label}</option>
          ))}
        </select>

        <select
          value={workspaceFilter}
          onChange={(e) => setWorkspaceFilter(e.target.value)}
          className="text-xs px-2 py-1.5 rounded-lg bg-neutral-900 border border-neutral-700 text-neutral-200 max-w-[200px]"
        >
          <option value="">All workspaces</option>
          {workspaceOptions.map((id) => (
            <option key={id} value={id}>{id}</option>
          ))}
        </select>
      </div>

      <div className="rounded-xl border border-neutral-800 overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-neutral-800 bg-neutral-950/80 text-left">
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Time</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
                  {source === 'ai' ? 'Tool / Action' : 'Agent'}
                </th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
                  Summary
                </th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">Status</th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
                  {source === 'ai' ? 'Env' : 'Grounding'}
                </th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500">
                  {source === 'ai' ? 'HITL' : 'Duration'}
                </th>
                <th className="px-4 py-3 text-[11px] font-semibold uppercase tracking-wider text-neutral-500 w-16">Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading && (source === 'ai' ? aiExecutions : runs).length === 0 ? (
                <tr>
                  <td colSpan={7} className="px-4 py-10 text-center text-neutral-500">
                    <Loader2 className="w-5 h-5 animate-spin inline-block mr-2 text-indigo-400" />
                    Loading history…
                  </td>
                </tr>
              ) : source === 'ai' && aiExecutions.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-0">
                    <EmptyState
                      icon="🤖"
                      title={isAdmin ? 'No AI tool executions yet.' : 'AI execution history requires Admin.'}
                      action={
                        isAdmin
                          ? {
                              label: 'Open AI Assistant →',
                              onClick: () => navigate('/ai-assistant'),
                            }
                          : undefined
                      }
                    />
                  </td>
                </tr>
              ) : source === 'agents' && runs.length === 0 ? (
                <tr>
                  <td colSpan={7} className="p-0">
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
              ) : source === 'ai' ? (
                aiExecutions.map((ex) => (
                  <tr
                    key={ex.id}
                    className="border-b border-neutral-800/80 hover:bg-neutral-900/50 transition-colors"
                  >
                    <td className="px-4 py-3 text-xs text-neutral-400 whitespace-nowrap">
                      {ex.created_at ? new Date(ex.created_at).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-200 font-medium whitespace-nowrap">
                      {ex.tool_id} → {ex.action}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400 max-w-[240px]" title={executionSummary(ex)}>
                      {truncate(executionSummary(ex), 60)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={ex.status} />
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400 whitespace-nowrap">
                      {ex.environment || ex.conversation_context?.environment || '—'}
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400">
                      {ex.requires_hitl ? 'yes' : '—'}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setDrawerItem({ mode: 'ai', item: ex })}
                        className="p-1.5 rounded-lg text-neutral-500 hover:text-indigo-400 hover:bg-neutral-800 transition-colors"
                        title="View details"
                      >
                        <Eye className="w-4 h-4" />
                      </button>
                    </td>
                  </tr>
                ))
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
                    <td className="px-4 py-3 text-xs text-neutral-400 max-w-[240px]" title={run.summary || run.task}>
                      {truncate(run.summary || run.task, 60)}
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={run.status} />
                    </td>
                    <td className="px-4 py-3">
                      <GroundingBadge grounding={run.details?.grounding || run.grounding} />
                    </td>
                    <td className="px-4 py-3 text-xs text-neutral-400 whitespace-nowrap">
                      {formatDuration(run)}
                    </td>
                    <td className="px-4 py-3">
                      <button
                        type="button"
                        onClick={() => setDrawerItem({ mode: 'agents', item: run })}
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
          onClick={() => void fetchAgentPage(page + 1, true)}
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

      {drawerItem && (
        <RunDetailDrawer
          run={drawerItem.item}
          mode={drawerItem.mode}
          onClose={() => setDrawerItem(null)}
        />
      )}
    </div>
  )
}
