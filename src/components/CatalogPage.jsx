import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Plus,
  Search,
  Users,
  Code,
  ExternalLink,
  X,
  Loader2,
  Pencil,
  Trash2,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  XCircle,
  Zap,
  History,
} from 'lucide-react'
import * as LucideIcons from 'lucide-react'
import { useLocation } from 'react-router-dom'
import { useAuth } from '../contexts/AuthContext'
import { RunActionModal, LogsDrawer } from './entityActionsShared'

const KIND_TABS = ['All', 'Service', 'API', 'Library', 'Website']

const KIND_BADGE = {
  Service: 'bg-blue-600',
  API: 'bg-green-600',
  Library: 'bg-yellow-600',
  Website: 'bg-purple-600',
}

const LIFECYCLE_DOT = {
  production: 'bg-emerald-500',
  experimental: 'bg-amber-400',
  deprecated: 'bg-red-500',
}

const HEALTH_DOT = {
  healthy: 'bg-emerald-500',
  degraded: 'bg-amber-400',
  unknown: 'bg-slate-500',
}

function emptyForm() {
  return {
    name: '',
    kind: 'Service',
    lifecycle: 'production',
    owner_team: '',
    language: '',
    repo_url: '',
    description: '',
    tags: '',
    health_status: 'unknown',
  }
}

function tagsToStorage(commaStr) {
  const list = (commaStr || '')
    .split(',')
    .map((t) => t.trim())
    .filter(Boolean)
  return list.length ? JSON.stringify(list) : null
}

function tagsToDisplay(tags) {
  if (Array.isArray(tags)) return tags.join(', ')
  if (typeof tags === 'string') {
    try {
      const p = JSON.parse(tags)
      return Array.isArray(p) ? p.join(', ') : tags
    } catch {
      return tags
    }
  }
  return ''
}

export default function CatalogPage() {
  const location = useLocation()
  const { authFetch } = useAuth()

  const [entities, setEntities] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedEntity, setSelectedEntity] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [saving, setSaving] = useState(false)
  const [filterKind, setFilterKind] = useState('All')
  const [searchQuery, setSearchQuery] = useState('')
  const [scorecard, setScorecard] = useState(null)
  const [scorecardLoading, setScorecardLoading] = useState(false)
  const [scorecardEvaluating, setScorecardEvaluating] = useState(false)
  const [drawerTab, setDrawerTab] = useState('overview')
  const [entityActions, setEntityActions] = useState([])
  const [actionsLoading, setActionsLoading] = useState(false)
  const [actionRuns, setActionRuns] = useState([])
  const [runsLoading, setRunsLoading] = useState(false)
  const [runningAction, setRunningAction] = useState(null)
  const [runMessage, setRunMessage] = useState(null)
  const [logsModal, setLogsModal] = useState(null)

  const loadScorecard = useCallback(
    async (entityId) => {
      if (!entityId) return
      setScorecardLoading(true)
      try {
        const res = await authFetch(`/api/catalog/${encodeURIComponent(entityId)}/scorecard`)
        if (!res.ok) throw new Error(await res.text())
        setScorecard(await res.json())
      } catch {
        setScorecard({ overall_score: 0, checks: [], by_category: [] })
      } finally {
        setScorecardLoading(false)
      }
    },
    [authFetch]
  )

  const evaluateScorecard = useCallback(
    async (entityId) => {
      if (!entityId) return
      setScorecardEvaluating(true)
      try {
        const res = await authFetch(
          `/api/catalog/${encodeURIComponent(entityId)}/scorecard/evaluate`,
          { method: 'POST' }
        )
        if (!res.ok) throw new Error(await res.text())
        setScorecard(await res.json())
      } catch (e) {
        setError(e.message || 'Scorecard evaluation failed')
      } finally {
        setScorecardEvaluating(false)
      }
    },
    [authFetch]
  )

  useEffect(() => {
    if (!selectedEntity?.id) {
      setScorecard(null)
      return
    }
    void loadScorecard(selectedEntity.id)
  }, [selectedEntity?.id, loadScorecard])

  const loadEntities = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/catalog')
      if (!res.ok) throw new Error(await res.text())
      setEntities(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load catalog')
      setEntities([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void loadEntities()
  }, [loadEntities])

  useEffect(() => {
    const q = location.state?.catalogSearch
    if (typeof q === 'string' && q.trim()) setSearchQuery(q.trim())
  }, [location.state])

  useEffect(() => {
    const tab = new URLSearchParams(location.search).get('tab')
    if (tab === 'runs') setDrawerTab('runs')
  }, [location.search])

  const loadEntityActions = useCallback(
    async (entityId) => {
      if (!entityId) return
      setActionsLoading(true)
      try {
        const res = await authFetch(`/api/catalog/${encodeURIComponent(entityId)}/actions`)
        if (!res.ok) throw new Error(await res.text())
        setEntityActions(await res.json())
      } catch (e) {
        setError(e.message || 'Failed to load actions')
        setEntityActions([])
      } finally {
        setActionsLoading(false)
      }
    },
    [authFetch]
  )

  const loadActionRuns = useCallback(
    async (entityId) => {
      if (!entityId) return
      setRunsLoading(true)
      try {
        const res = await authFetch(
          `/api/entity-action-runs?entity_id=${encodeURIComponent(entityId)}`
        )
        if (!res.ok) throw new Error(await res.text())
        setActionRuns(await res.json())
      } catch (e) {
        setError(e.message || 'Failed to load action runs')
        setActionRuns([])
      } finally {
        setRunsLoading(false)
      }
    },
    [authFetch]
  )

  useEffect(() => {
    if (!selectedEntity?.id) {
      setDrawerTab('overview')
      setEntityActions([])
      setActionRuns([])
      return
    }
    const tab = new URLSearchParams(location.search).get('tab')
    if (tab === 'runs') setDrawerTab('runs')
  }, [selectedEntity?.id, location.search])

  useEffect(() => {
    if (!selectedEntity?.id) return
    if (drawerTab === 'actions') void loadEntityActions(selectedEntity.id)
    if (drawerTab === 'runs') void loadActionRuns(selectedEntity.id)
  }, [selectedEntity?.id, drawerTab, loadEntityActions, loadActionRuns])

  const filtered = useMemo(() => {
    const q = searchQuery.trim().toLowerCase()
    return entities.filter((e) => {
      if (filterKind !== 'All' && e.kind !== filterKind) return false
      if (!q) return true
      const tagStr = tagsToDisplay(e.tags).toLowerCase()
      return (
        (e.name || '').toLowerCase().includes(q) ||
        (e.owner_team || '').toLowerCase().includes(q) ||
        tagStr.includes(q)
      )
    })
  }, [entities, filterKind, searchQuery])

  const openCreate = () => {
    setEditingId(null)
    setForm(emptyForm())
    setShowForm(true)
  }

  const openEdit = (entity) => {
    setEditingId(entity.id)
    setForm({
      name: entity.name || '',
      kind: entity.kind || 'Service',
      lifecycle: entity.lifecycle || 'production',
      owner_team: entity.owner_team || '',
      language: entity.language || '',
      repo_url: entity.repo_url || '',
      description: entity.description || '',
      tags: tagsToDisplay(entity.tags),
      health_status: entity.health_status || 'unknown',
    })
    setShowForm(true)
  }

  const submitForm = async (e) => {
    e.preventDefault()
    if (!form.name.trim() || !form.owner_team.trim()) return
    setSaving(true)
    const body = {
      name: form.name.trim(),
      kind: form.kind,
      lifecycle: form.lifecycle,
      owner_team: form.owner_team.trim(),
      language: form.language.trim() || null,
      repo_url: form.repo_url.trim() || null,
      description: form.description.trim() || null,
      tags: tagsToStorage(form.tags),
      health_status: form.health_status,
    }
    try {
      const res = editingId
        ? await authFetch(`/api/catalog/${encodeURIComponent(editingId)}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
        : await authFetch('/api/catalog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          })
      if (!res.ok) throw new Error(await res.text())
      const saved = await res.json()
      setShowForm(false)
      setEditingId(null)
      await loadEntities()
      if (selectedEntity?.id === saved.id) setSelectedEntity(saved)
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  const deleteEntity = async (id) => {
    if (!window.confirm('Remove this catalog entry?')) return
    try {
      const res = await authFetch(`/api/catalog/${encodeURIComponent(id)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      setSelectedEntity(null)
      await loadEntities()
    } catch (err) {
      setError(err.message || 'Delete failed')
    }
  }

  return (
    <div className="max-w-7xl mx-auto w-full space-y-6 pb-16">
      <div>
        <h1 className="text-2xl font-bold text-white tracking-tight">Software Catalog</h1>
        <p className="text-sm text-slate-400 mt-1">Services, APIs, libraries, and websites across the platform</p>
      </div>

      <div className="flex flex-col lg:flex-row lg:items-center gap-3 flex-wrap">
        <div className="flex flex-wrap gap-2">
          {KIND_TABS.map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setFilterKind(k)}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                filterKind === k
                  ? 'bg-blue-600 border-blue-500 text-white'
                  : 'border-border text-slate-400 hover:bg-slate-800 hover:text-white'
              }`}
            >
              {k}
            </button>
          ))}
        </div>
        <div className="flex flex-1 gap-2 min-w-[200px]">
          <div className="relative flex-1 max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={searchQuery}
              onChange={(ev) => setSearchQuery(ev.target.value)}
              placeholder="Search name, team, tags…"
              className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
            />
          </div>
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shrink-0"
          >
            <Plus className="w-4 h-4" /> Add
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-500/40 bg-red-950/30 px-4 py-3 text-sm text-red-200">{error}</div>
      )}

      {loading ? (
        <div className="flex items-center justify-center py-20 text-slate-400 gap-2">
          <Loader2 className="w-5 h-5 animate-spin" /> Loading catalog…
        </div>
      ) : filtered.length === 0 ? (
        <div className="rounded-xl border border-dashed border-border py-16 text-center text-slate-500">
          No catalog entries match your filters.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {filtered.map((entity) => (
            <button
              key={entity.id}
              type="button"
              onClick={() => setSelectedEntity(entity)}
              className="relative text-left rounded-xl border border-border bg-slate-900/50 p-4 hover:border-blue-500/40 hover:bg-slate-900/80 transition-colors min-h-[140px] flex flex-col"
            >
              <div className="flex items-start justify-between gap-2 mb-2">
                <span
                  className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase text-white ${
                    KIND_BADGE[entity.kind] || 'bg-slate-600'
                  }`}
                >
                  {entity.kind}
                </span>
                <span className="inline-flex items-center gap-1.5 text-[10px] text-slate-400 capitalize shrink-0">
                  <span
                    className={`w-2 h-2 rounded-full ${LIFECYCLE_DOT[entity.lifecycle] || 'bg-slate-500'}`}
                  />
                  {entity.lifecycle}
                </span>
              </div>
              <p className="text-white font-semibold text-base mb-2 line-clamp-2">{entity.name}</p>
              <p className="text-gray-400 text-sm flex items-center gap-1.5 mb-1">
                <Users className="w-3.5 h-3.5 shrink-0" />
                <span className="truncate">{entity.owner_team}</span>
              </p>
              {entity.language ? (
                <p className="text-gray-500 text-xs flex items-center gap-1.5 mb-1">
                  <Code className="w-3.5 h-3.5 shrink-0" />
                  {entity.language}
                </p>
              ) : null}
              {entity.repo_url ? (
                <a
                  href={entity.repo_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={(ev) => ev.stopPropagation()}
                  className="text-blue-400 text-xs inline-flex items-center gap-1 hover:text-blue-300 mt-auto"
                >
                  <ExternalLink className="w-3.5 h-3.5" /> Repository
                </a>
              ) : (
                <span className="flex-1" />
              )}
              <span
                className={`absolute bottom-3 right-3 w-2.5 h-2.5 rounded-full ring-2 ring-slate-900 ${
                  HEALTH_DOT[entity.health_status] || HEALTH_DOT.unknown
                }`}
                title={`Health: ${entity.health_status}`}
              />
            </button>
          ))}
        </div>
      )}

      {selectedEntity && (
        <>
          <button
            type="button"
            aria-label="Close drawer"
            className="fixed inset-0 z-[70] bg-black/60"
            onClick={() => setSelectedEntity(null)}
          />
          <aside className="fixed top-0 right-0 z-[80] h-full w-full max-w-md bg-slate-950 border-l border-border shadow-2xl flex flex-col overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border">
              <h2 className="text-lg font-bold text-white pr-8">{selectedEntity.name}</h2>
              <button
                type="button"
                onClick={() => setSelectedEntity(null)}
                className="p-2 rounded-lg hover:bg-slate-800 text-slate-400"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex gap-1 px-3 border-b border-border shrink-0 overflow-x-auto">
              {[
                { id: 'overview', label: 'Overview' },
                { id: 'scorecard', label: 'Scorecard' },
                { id: 'actions', label: 'Actions' },
                { id: 'runs', label: 'Runs' },
              ].map((tab) => (
                <button
                  key={tab.id}
                  type="button"
                  onClick={() => setDrawerTab(tab.id)}
                  className={`px-3 py-2.5 text-xs font-semibold border-b-2 transition-colors whitespace-nowrap ${
                    drawerTab === tab.id
                      ? 'border-blue-500 text-white'
                      : 'border-transparent text-slate-500 hover:text-slate-300'
                  }`}
                >
                  {tab.label}
                </button>
              ))}
            </div>
            <div className="flex-1 overflow-y-auto px-5 py-4 text-sm">
              {drawerTab === 'overview' && (
                <div className="space-y-4">
                  <DetailRow label="Kind" value={selectedEntity.kind} />
                  <DetailRow label="Lifecycle" value={selectedEntity.lifecycle} />
                  <DetailRow label="Owner team" value={selectedEntity.owner_team} />
                  <DetailRow label="Language" value={selectedEntity.language || '—'} />
                  <DetailRow label="Health" value={selectedEntity.health_status} />
                  <DetailRow label="Repository" value={selectedEntity.repo_url || '—'} link={selectedEntity.repo_url} />
                  <DetailRow label="Tags" value={tagsToDisplay(selectedEntity.tags) || '—'} />
                  <div>
                    <p className="text-xs font-semibold text-slate-500 uppercase mb-1">Description</p>
                    <p className="text-slate-300 whitespace-pre-wrap">{selectedEntity.description || '—'}</p>
                  </div>
                  <DetailRow label="Created" value={selectedEntity.created_at ? new Date(selectedEntity.created_at).toLocaleString() : '—'} />
                </div>
              )}

              {drawerTab === 'scorecard' && (
                <ScoreSection
                  embedded
                  scorecard={scorecard}
                  loading={scorecardLoading}
                  evaluating={scorecardEvaluating}
                  onReevaluate={() => void evaluateScorecard(selectedEntity.id)}
                />
              )}

              {drawerTab === 'actions' && (
                <ActionsTab
                  actions={entityActions}
                  loading={actionsLoading}
                  runMessage={runMessage}
                  onRun={(action) => setRunningAction(action)}
                />
              )}

              {drawerTab === 'runs' && (
                <RunsTab runs={actionRuns} loading={runsLoading} onViewLogs={setLogsModal} />
              )}
            </div>
            <div className="px-5 py-4 border-t border-border flex gap-2">
              <button
                type="button"
                onClick={() => {
                  openEdit(selectedEntity)
                }}
                className="flex-1 inline-flex items-center justify-center gap-2 py-2.5 rounded-lg bg-slate-800 border border-border text-white text-sm font-semibold hover:bg-slate-700"
              >
                <Pencil className="w-4 h-4" /> Edit
              </button>
              <button
                type="button"
                onClick={() => void deleteEntity(selectedEntity.id)}
                className="flex-1 inline-flex items-center justify-center gap-2 py-2.5 rounded-lg bg-red-950/50 border border-red-800 text-red-200 text-sm font-semibold hover:bg-red-900/50"
              >
                <Trash2 className="w-4 h-4" /> Delete
              </button>
            </div>
          </aside>

          {runningAction && (
            <RunActionModal
              action={runningAction}
              defaultEntityId={selectedEntity.id}
              lockEntityId
              onClose={() => setRunningAction(null)}
              onSuccess={(data) => {
                const slug = runningAction.slug
                setRunningAction(null)
                setRunMessage(data.result?.message || `Action ${data.status}`)
                if (drawerTab === 'runs') void loadActionRuns(selectedEntity.id)
                if (slug === 're-eval-scorecard') void loadScorecard(selectedEntity.id)
              }}
            />
          )}

          {logsModal && <LogsDrawer run={logsModal} onClose={() => setLogsModal(null)} />}

        </>
      )}

      {showForm && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/70">
          <div
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-slate-950 shadow-2xl"
            onClick={(ev) => ev.stopPropagation()}
          >
            <form onSubmit={(ev) => void submitForm(ev)} className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-bold text-white">{editingId ? 'Edit entity' : 'Add entity'}</h3>
                <button type="button" onClick={() => setShowForm(false)} className="text-slate-400 hover:text-white">
                  <X className="w-5 h-5" />
                </button>
              </div>
              <FormField label="Name *">
                <input
                  required
                  value={form.name}
                  onChange={(ev) => setForm({ ...form, name: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                />
              </FormField>
              <div className="grid grid-cols-2 gap-3">
                <FormField label="Kind *">
                  <select
                    required
                    value={form.kind}
                    onChange={(ev) => setForm({ ...form, kind: ev.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  >
                    {KIND_TABS.filter((k) => k !== 'All').map((k) => (
                      <option key={k} value={k}>
                        {k}
                      </option>
                    ))}
                  </select>
                </FormField>
                <FormField label="Lifecycle *">
                  <select
                    required
                    value={form.lifecycle}
                    onChange={(ev) => setForm({ ...form, lifecycle: ev.target.value })}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  >
                    <option value="experimental">experimental</option>
                    <option value="production">production</option>
                    <option value="deprecated">deprecated</option>
                  </select>
                </FormField>
              </div>
              <FormField label="Owner team *">
                <input
                  required
                  value={form.owner_team}
                  onChange={(ev) => setForm({ ...form, owner_team: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                />
              </FormField>
              <FormField label="Language">
                <input
                  value={form.language}
                  onChange={(ev) => setForm({ ...form, language: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                />
              </FormField>
              <FormField label="Repository URL">
                <input
                  value={form.repo_url}
                  onChange={(ev) => setForm({ ...form, repo_url: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  placeholder="https://github.com/org/repo"
                />
              </FormField>
              <FormField label="Description">
                <textarea
                  rows={3}
                  value={form.description}
                  onChange={(ev) => setForm({ ...form, description: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm resize-none"
                />
              </FormField>
              <FormField label="Tags (comma-separated)">
                <input
                  value={form.tags}
                  onChange={(ev) => setForm({ ...form, tags: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  placeholder="platform, sre, api"
                />
              </FormField>
              <FormField label="Health status">
                <select
                  value={form.health_status}
                  onChange={(ev) => setForm({ ...form, health_status: ev.target.value })}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                >
                  <option value="healthy">healthy</option>
                  <option value="degraded">degraded</option>
                  <option value="unknown">unknown</option>
                </select>
              </FormField>
              <div className="flex gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="flex-1 py-2.5 rounded-lg border border-border text-slate-300 text-sm font-semibold hover:bg-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="flex-1 py-2.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold disabled:opacity-50"
                >
                  {saving ? 'Saving…' : editingId ? 'Save' : 'Create'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}

function scoreRingColor(score) {
  if (score >= 80) return { stroke: '#22c55e', text: 'text-emerald-400' }
  if (score >= 60) return { stroke: '#eab308', text: 'text-amber-400' }
  return { stroke: '#ef4444', text: 'text-red-400' }
}

function ScoreRing({ score }) {
  const size = 96
  const stroke = 8
  const radius = (size - stroke) / 2
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (score / 100) * circumference
  const { stroke: ringStroke, text } = scoreRingColor(score)

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-slate-700"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={ringStroke}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
        />
      </svg>
      <div className={`absolute inset-0 flex flex-col items-center justify-center ${text}`}>
        <span className="text-2xl font-bold text-white leading-none">{score}</span>
        <span className="text-[10px] text-slate-500 mt-0.5">/ 100</span>
      </div>
    </div>
  )
}

function CheckStatusIcon({ status }) {
  if (status === 'pass') return <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
  if (status === 'fail') return <XCircle className="w-4 h-4 text-red-400 flex-shrink-0" />
  return <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
}

function scoreBarColor(score) {
  if (score >= 80) return 'bg-emerald-500'
  if (score >= 60) return 'bg-amber-500'
  return 'bg-red-500'
}

function CheckRow({ check }) {
  return (
    <div className="flex items-center gap-2 text-sm py-1">
      <CheckStatusIcon status={check.status} />
      <span className="flex-1 min-w-0 text-slate-300 truncate">{check.check_name}</span>
      <span className="text-slate-400 tabular-nums w-8 text-right">{check.score}</span>
      <div className="w-20 h-1.5 rounded-full bg-gray-700 overflow-hidden flex-shrink-0">
        <div className={`h-full rounded-full ${scoreBarColor(check.score)}`} style={{ width: `${check.score}%` }} />
      </div>
    </div>
  )
}

function ActionIcon({ name, className }) {
  const Icon = LucideIcons[name] || Zap
  return <Icon className={className} />
}

function runStatusPill(status) {
  if (status === 'completed') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
        completed
      </span>
    )
  }
  if (status === 'running') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-500/15 text-blue-400 border border-blue-500/30">
        running
      </span>
    )
  }
  if (status === 'pending') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-400 border border-amber-500/30">
        pending
      </span>
    )
  }
  if (status === 'failed') {
    return (
      <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-red-500/15 text-red-400 border border-red-500/30">
        failed
      </span>
    )
  }
  return (
    <span className="inline-flex px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-700 text-slate-400">
      {status || 'unknown'}
    </span>
  )
}

function ActionsTab({ actions, loading, runMessage, onRun }) {
  if (loading) {
    return (
      <div className="flex justify-center py-12 text-slate-400 gap-2">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading actions…
      </div>
    )
  }
  if (!actions.length) {
    return <p className="text-center text-slate-500 py-8">No actions available for this entity.</p>
  }
  return (
    <div className="space-y-3">
      {runMessage && (
        <div className="rounded-lg border border-blue-500/30 bg-blue-500/10 px-3 py-2 text-sm text-blue-200">
          {runMessage}
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {actions.map((action) => (
          <div
            key={action.id}
            className="rounded-xl border border-border bg-slate-900/50 p-3 flex flex-col gap-2"
          >
            <div className="flex items-start gap-2">
              <ActionIcon name={action.icon} className="w-5 h-5 text-blue-400 shrink-0 mt-0.5" />
              <div className="min-w-0">
                <p className="font-semibold text-white text-sm">{action.name}</p>
                <p className="text-xs text-slate-500 line-clamp-2">{action.description || '—'}</p>
              </div>
            </div>
            {action.requires_approval && (
              <span className="text-[10px] font-semibold uppercase text-amber-400 bg-amber-500/10 border border-amber-500/25 px-1.5 py-0.5 rounded w-fit">
                Requires approval
              </span>
            )}
            <button
              type="button"
              onClick={() => onRun(action)}
              className="mt-auto w-full py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
            >
              Run
            </button>
          </div>
        ))}
      </div>
    </div>
  )
}

function RunsTab({ runs, loading, onViewLogs }) {
  if (loading) {
    return (
      <div className="flex justify-center py-12 text-slate-400 gap-2">
        <Loader2 className="w-5 h-5 animate-spin" /> Loading runs…
      </div>
    )
  }
  if (!runs.length) {
    return <p className="text-center text-slate-500 py-8">No action runs yet for this entity.</p>
  }
  return (
    <div className="rounded-xl border border-border overflow-hidden">
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-border bg-slate-900/80 text-slate-500 uppercase tracking-wider">
            <th className="px-3 py-2 text-left font-semibold">Action</th>
            <th className="px-3 py-2 text-left font-semibold">Status</th>
            <th className="px-3 py-2 text-left font-semibold">By</th>
            <th className="px-3 py-2 text-left font-semibold">Started</th>
            <th className="px-3 py-2 text-right font-semibold">Logs</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b border-border/60 hover:bg-slate-900/40">
              <td className="px-3 py-2 text-white">{run.action_name || run.action_id}</td>
              <td className="px-3 py-2">{runStatusPill(run.status)}</td>
              <td className="px-3 py-2 text-slate-400">{run.requested_by}</td>
              <td className="px-3 py-2 text-slate-400">
                {run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
              </td>
              <td className="px-3 py-2 text-right">
                <button
                  type="button"
                  onClick={() => onViewLogs(run)}
                  className="text-blue-400 hover:text-blue-300 font-semibold"
                >
                  Logs
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function ScoreSection({ scorecard, loading, evaluating, onReevaluate, embedded = false }) {
  const overall = scorecard?.overall_score ?? 0
  let grouped = scorecard?.by_category ?? []
  if (!grouped.length && scorecard?.checks?.length) {
    const byCat = {}
    for (const c of scorecard.checks) {
      if (!byCat[c.category]) byCat[c.category] = []
      byCat[c.category].push(c)
    }
    grouped = Object.entries(byCat).map(([category, checks]) => ({ category, checks }))
  }
  const hasChecks = (scorecard?.checks?.length ?? 0) > 0

  return (
    <div className={embedded ? '' : 'pt-4 mt-4 border-t border-border'}>
      <div className="flex items-center justify-between mb-4">
        <h4 className="text-xs font-bold text-slate-500 uppercase tracking-wider">Scorecard</h4>
        <button
          type="button"
          onClick={onReevaluate}
          disabled={evaluating || loading}
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-blue-400 hover:text-blue-300 disabled:opacity-50"
        >
          {evaluating ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : (
            <RefreshCw className="w-3.5 h-3.5" />
          )}
          Re-evaluate
        </button>
      </div>

      {loading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
        </div>
      ) : (
        <>
          <div className="flex justify-center mb-5">
            <ScoreRing score={overall} />
          </div>
          {!hasChecks ? (
            <p className="text-center text-sm text-slate-500 pb-2">
              No scorecard yet — click Re-evaluate
            </p>
          ) : (
            <div className="space-y-4">
              {grouped.map(({ category, checks }) => (
                <div key={category}>
                  <p className="text-xs font-semibold text-slate-400 mb-2 border-b border-border/60 pb-1">
                    {category}
                  </p>
                  <div className="space-y-0.5">
                    {checks.map((c) => (
                      <CheckRow key={`${category}-${c.check_name}`} check={c} />
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function DetailRow({ label, value, link }) {
  return (
    <div>
      <p className="text-xs font-semibold text-slate-500 uppercase mb-0.5">{label}</p>
      {link ? (
        <a href={link} target="_blank" rel="noopener noreferrer" className="text-blue-400 hover:underline break-all">
          {value}
        </a>
      ) : (
        <p className="text-slate-200">{value}</p>
      )}
    </div>
  )
}

function FormField({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-semibold text-slate-400 uppercase mb-1.5">{label}</span>
      {children}
    </label>
  )
}
