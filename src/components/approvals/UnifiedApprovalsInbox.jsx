import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import {
  CheckCircle2, XCircle, Clock, AlertTriangle, ChevronDown, ChevronUp,
  Keyboard, Loader2, RefreshCw, ShieldAlert, Users,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../ToastNotification'
import { Badge, EmptyState, PageHeader } from '../ui'

const RISK_TONE = { low: 'success', medium: 'warning', high: 'danger' }
const SOURCE_LABEL = {
  agent: 'Agent run',
  workflow: 'Workflow',
  mcp: 'MCP tool',
  entity_action: 'Entity action',
  access: 'Access request',
  change: 'Change record',
}

function GroundingBadge({ grounding }) {
  if (!grounding) return null
  const g = String(grounding).toLowerCase()
  const tone = g === 'live' ? 'success' : g === 'partial' ? 'warning' : g === 'demo' ? 'accent' : 'neutral'
  return <Badge tone={tone}>{g}</Badge>
}

function ageLabel(seconds) {
  if (seconds < 60) return `${seconds}s ago`
  const m = Math.floor(seconds / 60)
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ${m % 60}m ago`
  const d = Math.floor(h / 24)
  return `${d}d ago`
}

function DetailBlock({ detail, source }) {
  if (!detail) return null
  const commands = Array.isArray(detail.commands) ? detail.commands : null
  const bigText =
    detail.forward_sql || detail.plan_text || (detail.params && detail.params.plan_text) || null

  return (
    <div className="mt-3 space-y-2 text-xs">
      {commands && commands.length > 0 && (
        <div>
          <div className="mb-1 font-semibold text-slate-400">Commands</div>
          <pre className="max-h-48 overflow-auto rounded-lg bg-slate-950/60 p-2 text-slate-300">
            {commands.join('\n')}
          </pre>
        </div>
      )}
      {bigText && (
        <div>
          <div className="mb-1 font-semibold text-slate-400">Plan / SQL</div>
          <pre className="max-h-64 overflow-auto rounded-lg bg-slate-950/60 p-2 text-slate-300 whitespace-pre-wrap">
            {String(bigText)}
          </pre>
        </div>
      )}
      {source === 'change' && detail.blast_radius && (
        <div>
          <div className="mb-1 font-semibold text-slate-400">Blast radius</div>
          <div className="text-slate-300">
            {detail.blast_radius.dependent_count ?? 0} dependent service(s), root tier{' '}
            {detail.blast_radius.root_tier || 'unknown'}
          </div>
        </div>
      )}
      {source === 'access' && (
        <div className="text-slate-300">
          Owner: {detail.owner_username}
          {detail.owner_missing ? ' (no registered owner — routed to admin)' : ''}
        </div>
      )}
      <div>
        <div className="mb-1 font-semibold text-slate-400">Raw detail</div>
        <pre className="max-h-48 overflow-auto rounded-lg bg-slate-950/60 p-2 text-slate-400">
          {JSON.stringify(detail, null, 2)}
        </pre>
      </div>
    </div>
  )
}

function ShortcutsOverlay({ onClose }) {
  const rows = [
    ['j / k', 'Move down / up'],
    ['a', 'Approve focused item'],
    ['r', 'Reject focused item'],
    ['Enter', 'Expand / collapse focused item'],
    ['?', 'Toggle this help'],
  ]
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="w-80 rounded-2xl border border-border bg-card p-5"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="mb-3 text-sm font-bold text-white">Keyboard shortcuts</h3>
        <div className="space-y-2 text-sm">
          {rows.map(([key, desc]) => (
            <div key={key} className="flex items-center justify-between">
              <kbd className="rounded border border-slate-600 bg-slate-800 px-1.5 py-0.5 text-xs">{key}</kbd>
              <span className="text-slate-400">{desc}</span>
            </div>
          ))}
        </div>
        <button
          className="mt-4 w-full rounded-lg border border-border py-1.5 text-sm text-slate-300 hover:bg-white/5"
          onClick={onClose}
        >
          Close
        </button>
      </div>
    </div>
  )
}

export default function UnifiedApprovalsInbox() {
  const { authFetch } = useAuth()
  const { toast } = useToast()

  const [items, setItems] = useState([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [pageSize] = useState(25)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const [risk, setRisk] = useState('')
  const [source, setSource] = useState('')
  const [service, setService] = useState('')
  const [sort, setSort] = useState('age')
  const [sortDir, setSortDir] = useState('desc')
  const [slaMinutes, setSlaMinutes] = useState(() => {
    const saved = Number(window.localStorage.getItem('approvals_sla_minutes'))
    return Number.isFinite(saved) && saved > 0 ? saved : 30
  })

  const [focusedIndex, setFocusedIndex] = useState(0)
  const [expanded, setExpanded] = useState(() => new Set())
  const [selected, setSelected] = useState(() => new Set())
  const [busyIds, setBusyIds] = useState(() => new Set())
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [showBulkConfirm, setShowBulkConfirm] = useState(false)
  const [bulkBusy, setBulkBusy] = useState(false)

  const cardRefs = useRef([])

  const fetchInbox = useCallback(async () => {
    setLoading(true)
    setError('')
    const params = new URLSearchParams({
      page: String(page),
      page_size: String(pageSize),
      sort,
      sort_dir: sortDir,
      sla_minutes: String(slaMinutes),
    })
    if (risk) params.set('risk', risk)
    if (source) params.set('source', source)
    if (service) params.set('service', service)
    try {
      const res = await authFetch(`/api/approvals/inbox?${params.toString()}`)
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setItems(Array.isArray(data.items) ? data.items : [])
      setTotal(data.total || 0)
      setFocusedIndex((i) => Math.min(i, Math.max(0, (data.items || []).length - 1)))
    } catch (err) {
      setError(err.message || 'Failed to load approvals')
    } finally {
      setLoading(false)
    }
  }, [authFetch, page, pageSize, sort, sortDir, risk, source, service, slaMinutes])

  useEffect(() => {
    void fetchInbox()
  }, [fetchInbox])

  useEffect(() => {
    window.localStorage.setItem('approvals_sla_minutes', String(slaMinutes))
  }, [slaMinutes])

  const isEligibleForBulk = useCallback(
    (item) => item.risk === 'low' && !item.needs_typed_confirmation && !item.needs_second_approver,
    []
  )

  const setBusy = (id, busy) => {
    setBusyIds((prev) => {
      const next = new Set(prev)
      if (busy) next.add(id)
      else next.delete(id)
      return next
    })
  }

  const approveOne = useCallback(
    async (id) => {
      setBusy(id, true)
      try {
        const res = await authFetch(`/api/approvals/${encodeURIComponent(id)}/approve`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        })
        if (!res.ok) throw new Error(await res.text())
        toast?.success?.('Approved')
        setItems((prev) => prev.filter((it) => it.id !== id))
        setTotal((t) => Math.max(0, t - 1))
      } catch (err) {
        toast?.error?.(err.message || 'Approve failed')
      } finally {
        setBusy(id, false)
      }
    },
    [authFetch, toast]
  )

  const rejectOne = useCallback(
    async (id) => {
      setBusy(id, true)
      try {
        const res = await authFetch(`/api/approvals/${encodeURIComponent(id)}/reject`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ reason: 'Rejected via approvals inbox' }),
        })
        if (!res.ok) throw new Error(await res.text())
        toast?.success?.('Rejected')
        setItems((prev) => prev.filter((it) => it.id !== id))
        setTotal((t) => Math.max(0, t - 1))
      } catch (err) {
        toast?.error?.(err.message || 'Reject failed')
      } finally {
        setBusy(id, false)
      }
    },
    [authFetch, toast]
  )

  const toggleExpand = useCallback((id) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const toggleSelect = useCallback((id) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  // Keyboard navigation: j/k move, a/r approve/reject focused, Enter expand, ? help.
  useEffect(() => {
    function onKeyDown(e) {
      const tag = (document.activeElement?.tagName || '').toLowerCase()
      if (tag === 'input' || tag === 'textarea' || tag === 'select') return
      if (showShortcuts && e.key === 'Escape') {
        setShowShortcuts(false)
        return
      }
      if (e.key === '?') {
        e.preventDefault()
        setShowShortcuts((v) => !v)
        return
      }
      if (!items.length) return
      if (e.key === 'j') {
        e.preventDefault()
        setFocusedIndex((i) => Math.min(items.length - 1, i + 1))
        return
      }
      if (e.key === 'k') {
        e.preventDefault()
        setFocusedIndex((i) => Math.max(0, i - 1))
        return
      }
      const focused = items[focusedIndex]
      if (!focused) return
      if (e.key === 'a') {
        e.preventDefault()
        void approveOne(focused.id)
        return
      }
      if (e.key === 'r') {
        e.preventDefault()
        void rejectOne(focused.id)
        return
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        toggleExpand(focused.id)
      }
    }
    window.addEventListener('keydown', onKeyDown)
    return () => window.removeEventListener('keydown', onKeyDown)
  }, [items, focusedIndex, showShortcuts, approveOne, rejectOne, toggleExpand])

  useEffect(() => {
    const el = cardRefs.current[focusedIndex]
    if (el && typeof el.scrollIntoView === 'function') {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, [focusedIndex])

  const selectedEligible = useMemo(
    () => items.filter((it) => selected.has(it.id) && isEligibleForBulk(it)),
    [items, selected, isEligibleForBulk]
  )

  const runBulkApprove = async () => {
    setBulkBusy(true)
    try {
      const res = await authFetch('/api/approvals/bulk-approve', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ids: selectedEligible.map((it) => it.id) }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const okIds = new Set((data.results || []).filter((r) => r.ok).map((r) => r.id))
      const failed = (data.results || []).filter((r) => !r.ok)
      setItems((prev) => prev.filter((it) => !okIds.has(it.id)))
      setTotal((t) => Math.max(0, t - okIds.size))
      setSelected(new Set())
      setShowBulkConfirm(false)
      if (failed.length) {
        toast?.error?.(`${okIds.size} approved, ${failed.length} could not be bulk-approved`)
      } else {
        toast?.success?.(`Approved ${okIds.size} item(s)`)
      }
    } catch (err) {
      toast?.error?.(err.message || 'Bulk approve failed')
    } finally {
      setBulkBusy(false)
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize))

  return (
    <div className="mx-auto max-w-4xl px-4 py-6">
      <PageHeader
        title="Approvals inbox"
        subtitle={`${total} pending across every agent, workflow, and integration`}
        actions={
          <div className="flex items-center gap-2">
            <button
              className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5"
              onClick={() => setShowShortcuts(true)}
            >
              <Keyboard className="h-3.5 w-3.5" /> Shortcuts
            </button>
            <button
              className="flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs text-slate-300 hover:bg-white/5"
              onClick={() => void fetchInbox()}
            >
              <RefreshCw className={`h-3.5 w-3.5 ${loading ? 'animate-spin' : ''}`} /> Refresh
            </button>
          </div>
        }
      />

      <div className="mb-4 flex flex-wrap items-center gap-2 text-xs">
        <select
          className="rounded-lg border border-border bg-slate-900 px-2 py-1.5 text-slate-200"
          value={risk}
          onChange={(e) => { setPage(1); setRisk(e.target.value) }}
        >
          <option value="">All risk</option>
          <option value="low">Low</option>
          <option value="medium">Medium</option>
          <option value="high">High</option>
        </select>
        <select
          className="rounded-lg border border-border bg-slate-900 px-2 py-1.5 text-slate-200"
          value={source}
          onChange={(e) => { setPage(1); setSource(e.target.value) }}
        >
          <option value="">All sources</option>
          {Object.entries(SOURCE_LABEL).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
        <input
          className="rounded-lg border border-border bg-slate-900 px-2 py-1.5 text-slate-200 placeholder:text-slate-500"
          placeholder="Filter by service…"
          value={service}
          onChange={(e) => { setPage(1); setService(e.target.value) }}
        />
        <select
          className="rounded-lg border border-border bg-slate-900 px-2 py-1.5 text-slate-200"
          value={`${sort}:${sortDir}`}
          onChange={(e) => {
            const [s, d] = e.target.value.split(':')
            setSort(s)
            setSortDir(d)
          }}
        >
          <option value="age:desc">Oldest first</option>
          <option value="age:asc">Newest first</option>
          <option value="risk:desc">Highest risk first</option>
          <option value="risk:asc">Lowest risk first</option>
        </select>
        <label className="flex items-center gap-1 text-slate-400">
          SLA
          <input
            type="number"
            min={1}
            className="w-14 rounded-lg border border-border bg-slate-900 px-2 py-1.5 text-slate-200"
            value={slaMinutes}
            onChange={(e) => setSlaMinutes(Math.max(1, Number(e.target.value) || 30))}
          />
          min
        </label>
        {selectedEligible.length > 0 && (
          <button
            className="ml-auto flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 font-semibold text-white hover:bg-emerald-500"
            onClick={() => setShowBulkConfirm(true)}
          >
            <CheckCircle2 className="h-3.5 w-3.5" /> Approve {selectedEligible.length} selected
          </button>
        )}
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-danger/40 bg-danger/10 px-3 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {loading && items.length === 0 ? (
        <div className="flex items-center justify-center py-16 text-slate-500">
          <Loader2 className="h-6 w-6 animate-spin" />
        </div>
      ) : items.length === 0 ? (
        <EmptyState title="Inbox zero" hint="No pending approvals match these filters." />
      ) : (
        <div className="space-y-3">
          {items.map((item, idx) => {
            const isFocused = idx === focusedIndex
            const isExpanded = expanded.has(item.id)
            const eligible = isEligibleForBulk(item)
            const busy = busyIds.has(item.id)
            return (
              <div
                key={item.id}
                ref={(el) => { cardRefs.current[idx] = el }}
                className={`rounded-2xl border bg-card p-4 transition ${
                  isFocused ? 'border-accent shadow-lg shadow-accent/10' : 'border-border'
                }`}
                onMouseEnter={() => setFocusedIndex(idx)}
              >
                <div className="flex items-start gap-3">
                  <input
                    type="checkbox"
                    className="mt-1"
                    disabled={!eligible}
                    title={eligible ? 'Select for bulk approve' : 'Needs individual review'}
                    checked={selected.has(item.id)}
                    onChange={() => toggleSelect(item.id)}
                  />
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={RISK_TONE[item.risk] || 'neutral'}>{item.risk}</Badge>
                      <Badge tone="neutral">{SOURCE_LABEL[item.source] || item.source}</Badge>
                      <GroundingBadge grounding={item.grounding} />
                      {item.needs_typed_confirmation && (
                        <Badge tone="danger" icon={ShieldAlert}>typed confirm required</Badge>
                      )}
                      {item.needs_second_approver && (
                        <Badge tone="warning" icon={Users}>
                          {(item.approvers || []).length}/{item.approvals_required} approvers
                        </Badge>
                      )}
                      {item.sla_breached && (
                        <Badge tone="danger" icon={AlertTriangle}>SLA breached</Badge>
                      )}
                    </div>
                    <h3 className="mt-1.5 truncate text-sm font-bold text-white">{item.title}</h3>
                    <p className="mt-0.5 line-clamp-2 text-xs text-slate-400">{item.description}</p>
                    <div className="mt-1.5 flex items-center gap-2 text-[11px] text-slate-500">
                      <span>{item.requester}</span>
                      <span>·</span>
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" /> {ageLabel(item.age_seconds)}
                      </span>
                      {item.service && (
                        <>
                          <span>·</span>
                          <span>{item.service}</span>
                        </>
                      )}
                    </div>
                    {isExpanded && <DetailBlock detail={item.detail} source={item.source} />}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1.5">
                    <div className="flex items-center gap-1.5">
                      <button
                        className="flex items-center gap-1 rounded-lg bg-emerald-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void approveOne(item.id)}
                      >
                        {busy ? <Loader2 className="h-3 w-3 animate-spin" /> : <CheckCircle2 className="h-3 w-3" />}
                        Approve
                      </button>
                      <button
                        className="flex items-center gap-1 rounded-lg bg-rose-600 px-2.5 py-1 text-xs font-semibold text-white hover:bg-rose-500 disabled:opacity-50"
                        disabled={busy}
                        onClick={() => void rejectOne(item.id)}
                      >
                        <XCircle className="h-3 w-3" /> Reject
                      </button>
                    </div>
                    <button
                      className="flex items-center gap-0.5 text-[11px] text-slate-500 hover:text-slate-300"
                      onClick={() => toggleExpand(item.id)}
                    >
                      {isExpanded ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                      {isExpanded ? 'Less' : 'Details'}
                    </button>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3 text-xs text-slate-400">
          <button
            className="rounded-lg border border-border px-3 py-1 disabled:opacity-40"
            disabled={page <= 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            Prev
          </button>
          <span>Page {page} of {totalPages}</span>
          <button
            className="rounded-lg border border-border px-3 py-1 disabled:opacity-40"
            disabled={page >= totalPages}
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          >
            Next
          </button>
        </div>
      )}

      {showShortcuts && <ShortcutsOverlay onClose={() => setShowShortcuts(false)} />}

      {showBulkConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
          onClick={() => !bulkBusy && setShowBulkConfirm(false)}
        >
          <div
            className="w-96 max-w-[90vw] rounded-2xl border border-border bg-card p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <h3 className="mb-2 text-sm font-bold text-white">
              Approve {selectedEligible.length} item(s)?
            </h3>
            <ul className="mb-4 max-h-56 space-y-1 overflow-auto text-xs text-slate-300">
              {selectedEligible.map((it) => (
                <li key={it.id} className="truncate">• {it.title}</li>
              ))}
            </ul>
            <div className="flex justify-end gap-2">
              <button
                className="rounded-lg border border-border px-3 py-1.5 text-sm text-slate-300 hover:bg-white/5"
                disabled={bulkBusy}
                onClick={() => setShowBulkConfirm(false)}
              >
                Cancel
              </button>
              <button
                className="flex items-center gap-1 rounded-lg bg-emerald-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-emerald-500 disabled:opacity-50"
                disabled={bulkBusy}
                onClick={() => void runBulkApprove()}
              >
                {bulkBusy && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
                Approve all
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
