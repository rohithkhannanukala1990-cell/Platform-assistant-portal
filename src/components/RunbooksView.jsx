import { useState, useEffect, useCallback } from 'react'
import {
  BookOpen, Play, CheckCircle2, Clock, Tag, ChevronDown,
  ChevronUp, Loader2, Shield, Server, Database, Wifi,
  Search, AlertTriangle, Plus, Pencil, Trash2, X,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'
import RelatedAgentsBar from './RelatedAgentsBar'
import { PageHeader, EmptyState } from './ui'

const CATEGORIES = ['All', 'Application', 'Database', 'Network', 'Security']
const SEVERITIES = ['Critical', 'High', 'Medium', 'Low']

function slugify(name) {
  return (name || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '')
    .slice(0, 120) || 'runbook'
}

function mapCategory(cat) {
  const c = (cat || 'General').trim()
  if (CATEGORIES.includes(c)) return c
  return 'Application'
}

function parseSteps(stepsJson) {
  if (!stepsJson) return []
  try {
    const parsed = typeof stepsJson === 'string' ? JSON.parse(stepsJson) : stepsJson
    if (Array.isArray(parsed)) {
      return parsed.map((s) => {
        if (typeof s === 'string') return s
        if (s && typeof s === 'object') return String(s.label || s.name || s.command || JSON.stringify(s))
        return String(s)
      }).filter(Boolean)
    }
    if (parsed && typeof parsed === 'object') {
      return Object.values(parsed).flat().map(String)
    }
  } catch {
    return [String(stepsJson)]
  }
  return []
}

function templateToRunbook(t) {
  const steps = parseSteps(t.steps_json)
  const customTags = Array.isArray(t.tags) ? t.tags.filter(Boolean) : []
  const fallbackTags = [t.slug, t.category].filter(Boolean)
  const tags = customTags.length ? customTags : fallbackTags
  const estimated =
    (t.estimated_time && String(t.estimated_time).trim()) ||
    (steps.length ? `${Math.max(2, steps.length * 2)} min` : '5 min')
  return {
    id: String(t.id),
    title: t.name,
    slug: t.slug || '',
    category: mapCategory(t.category),
    severity: SEVERITIES.includes(t.severity) ? t.severity : 'Medium',
    estimatedTime: estimated.replace(/^~\s*/, ''),
    description: t.description || '',
    tags,
    steps: steps.length ? steps : ['Review runbook steps.'],
    raw: t,
  }
}

const CATEGORY_CFG = {
  Application: { icon: Server,   color: 'text-blue-400',   bg: 'bg-blue-500/10  border-blue-500/25'  },
  Database:    { icon: Database, color: 'text-cyan-400',   bg: 'bg-cyan-500/10  border-cyan-500/25'  },
  Network:     { icon: Wifi,     color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/25' },
  Security:    { icon: Shield,   color: 'text-red-400',    bg: 'bg-red-500/10   border-red-500/25'   },
}

const SEV_CFG = {
  Critical: 'text-red-400    bg-red-500/10    border-red-500/25',
  High:     'text-orange-400 bg-orange-500/10 border-orange-500/25',
  Medium:   'text-yellow-400 bg-yellow-500/10 border-yellow-500/25',
  Low:      'text-blue-400   bg-blue-500/10   border-blue-500/25',
}

function emptyForm() {
  return {
    title: '',
    slug: '',
    description: '',
    category: 'Application',
    severity: 'Medium',
    estimatedTime: '5 min',
    tags: [],
    tagDraft: '',
    steps: [''],
  }
}

function runbookToForm(rb) {
  return {
    title: rb.title || '',
    slug: rb.slug || '',
    description: rb.description || '',
    category: rb.category || 'Application',
    severity: rb.severity || 'Medium',
    estimatedTime: rb.estimatedTime || '5 min',
    tags: [...(rb.tags || [])].filter((t) => t && t !== rb.slug && t !== rb.category),
    tagDraft: '',
    steps: rb.steps?.length ? [...rb.steps] : [''],
  }
}

function RunbookEditorModal({ initial, onClose, onSaved }) {
  const { authFetch } = useAuth()
  const isEdit = Boolean(initial?.id)
  const [form, setForm] = useState(() => (initial ? runbookToForm(initial) : emptyForm()))
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const setField = (key, value) => setForm((f) => ({ ...f, [key]: value }))

  const handleTitle = (title) => {
    setForm((f) => ({
      ...f,
      title,
      slug: isEdit ? f.slug : (f.slug && f.slug !== slugify(f.title) ? f.slug : slugify(title)),
    }))
  }

  const addTag = () => {
    const t = form.tagDraft.trim()
    if (!t) return
    if (form.tags.some((x) => x.toLowerCase() === t.toLowerCase())) {
      setField('tagDraft', '')
      return
    }
    setForm((f) => ({ ...f, tags: [...f.tags, t], tagDraft: '' }))
  }

  const removeTag = (tag) => {
    setForm((f) => ({ ...f, tags: f.tags.filter((t) => t !== tag) }))
  }

  const setStep = (idx, value) => {
    setForm((f) => {
      const steps = [...f.steps]
      steps[idx] = value
      return { ...f, steps }
    })
  }

  const addStep = () => setForm((f) => ({ ...f, steps: [...f.steps, ''] }))
  const removeStep = (idx) => {
    setForm((f) => ({
      ...f,
      steps: f.steps.length <= 1 ? [''] : f.steps.filter((_, i) => i !== idx),
    }))
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!form.title.trim()) {
      setError('Title is required')
      return
    }
    const steps = form.steps.map((s) => s.trim()).filter(Boolean)
    if (!steps.length) {
      setError('Add at least one step')
      return
    }
    setSaving(true)
    setError(null)
    const payload = {
      name: form.title.trim(),
      slug: (form.slug.trim() || slugify(form.title)).trim(),
      description: form.description.trim(),
      category: form.category,
      steps_json: JSON.stringify(steps),
      tags: form.tags,
      severity: form.severity,
      estimated_time: form.estimatedTime.trim() || `${Math.max(2, steps.length * 2)} min`,
      is_active: true,
    }
    try {
      const res = await authFetch(
        isEdit ? `${API_BASE}/api/golden-paths/${initial.id}` : `${API_BASE}/api/golden-paths`,
        {
          method: isEdit ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        }
      )
      if (!res.ok) {
        let detail = `Error ${res.status}`
        try {
          const body = await res.json()
          detail = body.detail || detail
        } catch {
          detail = (await res.text()) || detail
        }
        throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
      }
      const saved = await res.json()
      onSaved(templateToRunbook(saved))
    } catch (err) {
      setError(err.message || 'Failed to save runbook')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <form
        onSubmit={(e) => void submit(e)}
        className="bg-surface border border-border rounded-2xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">
            {isEdit ? 'Edit Runbook' : 'Add Runbook'}
          </h2>
          <button type="button" onClick={onClose} className="text-slate-400 hover:text-white" aria-label="Close">
            <X size={20} />
          </button>
        </div>

        <div className="space-y-4">
          <label className="block">
            <span className="text-xs text-slate-400">Title *</span>
            <input
              value={form.title}
              onChange={(e) => handleTitle(e.target.value)}
              placeholder="e.g. Restart crashed payment pods"
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-400">Slug</span>
            <input
              value={form.slug}
              onChange={(e) => setField('slug', e.target.value)}
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm font-mono"
            />
          </label>

          <label className="block">
            <span className="text-xs text-slate-400">Description</span>
            <textarea
              rows={2}
              value={form.description}
              onChange={(e) => setField('description', e.target.value)}
              placeholder="What this runbook fixes and when to use it"
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm resize-none"
            />
          </label>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <label className="block">
              <span className="text-xs text-slate-400">Category</span>
              <select
                value={form.category}
                onChange={(e) => setField('category', e.target.value)}
                className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              >
                {CATEGORIES.filter((c) => c !== 'All').map((c) => (
                  <option key={c} value={c}>{c}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs text-slate-400">Severity</span>
              <select
                value={form.severity}
                onChange={(e) => setField('severity', e.target.value)}
                className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              >
                {SEVERITIES.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs text-slate-400">Estimated time</span>
              <input
                value={form.estimatedTime}
                onChange={(e) => setField('estimatedTime', e.target.value)}
                placeholder="8 min"
                className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              />
            </label>
          </div>

          <div>
            <span className="text-xs text-slate-400">Tags</span>
            <div className="mt-1 flex flex-wrap gap-1.5 mb-2">
              {form.tags.map((t) => (
                <span
                  key={t}
                  className="inline-flex items-center gap-1 text-[11px] text-slate-300 border border-border rounded-md px-2 py-0.5 bg-card"
                >
                  <Tag className="w-2.5 h-2.5" />
                  {t}
                  <button
                    type="button"
                    onClick={() => removeTag(t)}
                    className="text-slate-500 hover:text-white ml-0.5"
                    aria-label={`Remove tag ${t}`}
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              {!form.tags.length && (
                <span className="text-[11px] text-slate-600">No tags yet — add keywords for search</span>
              )}
            </div>
            <div className="flex gap-2">
              <input
                value={form.tagDraft}
                onChange={(e) => setField('tagDraft', e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') {
                    e.preventDefault()
                    addTag()
                  }
                }}
                placeholder="Type a tag and press Enter"
                className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              />
              <button
                type="button"
                onClick={addTag}
                className="px-3 py-2 rounded-lg border border-border text-xs font-semibold text-slate-300 hover:text-white hover:bg-card"
              >
                Add tag
              </button>
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1">
              <span className="text-xs text-slate-400">Steps *</span>
              <button
                type="button"
                onClick={addStep}
                className="text-[11px] text-accent hover:text-accent-hover font-semibold"
              >
                + Add step
              </button>
            </div>
            <div className="flex flex-col gap-2">
              {form.steps.map((step, idx) => (
                <div key={idx} className="flex items-start gap-2">
                  <span className="mt-2 text-[10px] text-slate-500 font-mono w-5 shrink-0">{idx + 1}.</span>
                  <textarea
                    rows={2}
                    value={step}
                    onChange={(e) => setStep(idx, e.target.value)}
                    placeholder="Command or instruction for this step"
                    className="flex-1 bg-card border border-border rounded-lg px-3 py-2 text-white text-sm font-mono resize-none"
                  />
                  <button
                    type="button"
                    onClick={() => removeStep(idx)}
                    className="mt-1 p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-500/10"
                    aria-label={`Remove step ${idx + 1}`}
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              ))}
            </div>
          </div>

          {error && (
            <p className="text-xs text-red-400 bg-red-500/10 border border-red-500/25 rounded-lg px-3 py-2">
              {error}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg border border-border text-sm text-slate-300 hover:text-white"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="px-4 py-2 rounded-lg bg-accent hover:bg-accent-hover text-white text-sm font-semibold disabled:opacity-50"
          >
            {saving ? 'Saving…' : isEdit ? 'Save changes' : 'Create runbook'}
          </button>
        </div>
      </form>
    </div>
  )
}

function RunbookCard({ rb, canManage, onEdit, onDelete }) {
  const [expanded, setExpanded] = useState(false)
  const [running, setRunning] = useState(false)
  const [done, setDone] = useState(false)
  const [step, setStep] = useState(0)
  const [deleting, setDeleting] = useState(false)

  const catCfg = CATEGORY_CFG[rb.category] || CATEGORY_CFG.Application
  const CatIcon = catCfg.icon

  function handleRun() {
    setRunning(true)
    setStep(0)
    setDone(false)
    const interval = setInterval(() => {
      setStep((prev) => {
        if (prev >= rb.steps.length - 1) {
          clearInterval(interval)
          setRunning(false)
          setDone(true)
          return prev
        }
        return prev + 1
      })
    }, 900)
  }

  async function handleDelete() {
    if (!window.confirm(`Delete runbook “${rb.title}”?`)) return
    setDeleting(true)
    try {
      await onDelete(rb)
    } finally {
      setDeleting(false)
    }
  }

  return (
    <div className={`flex flex-col rounded-2xl border overflow-hidden transition-all
      ${done ? 'border-green-500/25' : 'border-border'} bg-card`}>
      <div className="flex items-start gap-3 p-4">
        <div className={`flex items-center justify-center w-9 h-9 rounded-xl border shrink-0 ${catCfg.bg}`}>
          <CatIcon className={`w-4 h-4 ${catCfg.color}`} />
        </div>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-1">
            <span className="text-sm font-bold text-white">{rb.title}</span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${SEV_CFG[rb.severity]}`}>
              {rb.severity}
            </span>
          </div>
          <p className="text-xs text-slate-400 leading-relaxed">{rb.description}</p>
          <div className="flex items-center gap-3 mt-2 flex-wrap">
            <span className="flex items-center gap-1 text-[10px] text-slate-500">
              <Clock className="w-2.5 h-2.5" /> ~{rb.estimatedTime}
            </span>
            <span className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold ${catCfg.bg} ${catCfg.color}`}>
              {rb.category}
            </span>
            {rb.tags.map((t) => (
              <span key={t} className="flex items-center gap-1 text-[10px] text-slate-600 border border-slate-700 rounded-md px-1.5 py-0.5">
                <Tag className="w-2 h-2" />{t}
              </span>
            ))}
          </div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {canManage && (
            <>
              <button
                type="button"
                onClick={() => onEdit(rb)}
                className="p-1.5 rounded-lg border border-border text-slate-400 hover:text-white hover:bg-slate-800"
                title="Edit runbook"
              >
                <Pencil className="w-3.5 h-3.5" />
              </button>
              <button
                type="button"
                onClick={() => void handleDelete()}
                disabled={deleting}
                className="p-1.5 rounded-lg border border-border text-slate-400 hover:text-red-400 hover:bg-red-500/10 disabled:opacity-40"
                title="Delete runbook"
              >
                {deleting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
              </button>
            </>
          )}
          {!done && (
            <button
              onClick={handleRun}
              disabled={running}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-accent/15 border border-accent/35
                text-accent text-xs font-bold hover:bg-accent/25 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {running
                ? <><Loader2 className="w-3 h-3 animate-spin" /> Running…</>
                : <><Play className="w-3 h-3" /> Run</>
              }
            </button>
          )}
          {done && (
            <span className="flex items-center gap-1 text-[11px] text-green-400 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" /> Complete
            </span>
          )}
          <button
            onClick={() => setExpanded((v) => !v)}
            className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-500 hover:text-white transition-colors"
          >
            {expanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {(expanded || running || done) && (
        <div className="border-t border-border px-4 pb-4 pt-3 flex flex-col gap-2">
          <p className="text-[10px] font-bold text-slate-500 uppercase tracking-widest mb-1">Execution Steps</p>
          <ol className="flex flex-col gap-1.5">
            {rb.steps.map((s, i) => {
              const isCurrent = running && i === step
              const isDone = done || (running && i < step)
              const looksLikeCmd = /^(SELECT|kubectl|psql|kafka|openssl|iptables|curl|aws|helm|terraform)/i.test(s)
              return (
                <li
                  key={i}
                  className={`flex items-start gap-2 text-xs transition-all
                    ${isCurrent ? 'text-accent' : isDone ? 'text-green-400' : 'text-slate-500'}`}
                >
                  <span className={`shrink-0 mt-0.5 w-4 h-4 rounded-full flex items-center justify-center text-[9px] font-bold border
                    ${isCurrent ? 'border-accent/50 bg-accent/15' : isDone ? 'border-green-500/40 bg-green-500/10' : 'border-slate-700 bg-transparent'}`}>
                    {isDone ? '✓' : i + 1}
                  </span>
                  <span className={`font-mono leading-relaxed ${looksLikeCmd
                    ? 'text-[10px] bg-black/40 border border-slate-700/60 rounded px-2 py-0.5 w-full' : ''}`}>
                    {s}
                  </span>
                </li>
              )
            })}
          </ol>
        </div>
      )}
    </div>
  )
}

export default function RunbooksView() {
  const { authFetch, role } = useAuth()
  const canManage = role === 'Admin'
  const [category, setCategory] = useState('All')
  const [search, setSearch] = useState('')
  const [runbooks, setRunbooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [editor, setEditor] = useState(null) // null | 'create' | runbook

  const fetchRunbooks = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch(`${API_BASE}/api/golden-paths`)
      if (!res.ok) throw new Error(`Error ${res.status}`)
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      setRunbooks(list.map(templateToRunbook))
    } catch (e) {
      setError(e.message || 'Failed to load runbooks')
      setRunbooks([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void fetchRunbooks()
  }, [fetchRunbooks])

  const filtered = runbooks.filter((rb) => {
    const q = search.toLowerCase()
    const matchCat = category === 'All' || rb.category === category
    const matchSearch = !q ||
      rb.title.toLowerCase().includes(q) ||
      rb.description.toLowerCase().includes(q) ||
      rb.tags.some((t) => t.toLowerCase().includes(q))
    return matchCat && matchSearch
  })

  const handleSaved = (saved) => {
    setRunbooks((list) => {
      const idx = list.findIndex((r) => r.id === saved.id)
      if (idx >= 0) {
        const next = [...list]
        next[idx] = saved
        return next
      }
      return [saved, ...list]
    })
    setEditor(null)
  }

  const handleDelete = async (rb) => {
    const res = await authFetch(`${API_BASE}/api/golden-paths/${rb.id}`, { method: 'DELETE' })
    if (!res.ok) {
      const text = await res.text()
      throw new Error(text || `Delete failed (${res.status})`)
    }
    setRunbooks((list) => list.filter((r) => r.id !== rb.id))
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Runbooks"
        subtitle="Executable step-by-step remediation playbooks"
        actions={(
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-slate-600 border border-slate-700 rounded-lg px-2.5 py-1 font-semibold">
              {filtered.length} runbooks
            </span>
            {canManage && (
              <button
                type="button"
                onClick={() => setEditor('create')}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-accent hover:bg-accent-hover text-white text-xs font-semibold"
              >
                <Plus className="w-3.5 h-3.5" />
                Add Runbook
              </button>
            )}
          </div>
        )}
      />

      <RelatedAgentsBar surface="runbooks" />

      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2 bg-slate-900 border border-slate-700 rounded-xl px-3 py-2 flex-1 min-w-48">
          <Search className="w-3.5 h-3.5 text-slate-500 shrink-0" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search by title or tag…"
            className="bg-transparent text-xs text-slate-200 placeholder-slate-600 outline-none w-full"
          />
        </div>
        <div className="flex items-center gap-2 flex-wrap">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              onClick={() => setCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold border transition-colors ${
                category === cat
                  ? 'bg-accent/15 border-accent/40 text-accent'
                  : 'border-slate-700 text-slate-500 hover:text-white hover:border-slate-600'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      </div>

      <div className="flex flex-col gap-4">
        {loading ? (
          <div className="flex flex-col gap-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-slate-800 rounded-2xl animate-pulse" />
            ))}
          </div>
        ) : error ? (
          <div className="flex flex-col items-center py-12 text-gray-400">
            <AlertTriangle className="w-8 h-8 text-amber-400 mb-2" />
            <p className="text-sm">{error}</p>
            <button
              type="button"
              onClick={() => void fetchRunbooks()}
              className="mt-3 text-xs bg-accent hover:bg-accent/90 text-white px-4 py-2 rounded"
            >
              Retry
            </button>
          </div>
        ) : runbooks.length === 0 ? (
          <EmptyState
            icon={BookOpen}
            title="No runbooks yet"
            hint="Create your first remediation playbook with steps and tags."
            action={canManage ? (
              <button
                type="button"
                onClick={() => setEditor('create')}
                className="mt-2 text-sm bg-accent hover:bg-accent/90 text-white px-5 py-2 rounded-lg inline-flex items-center gap-1.5"
              >
                <Plus className="w-4 h-4" />
                Add Runbook
              </button>
            ) : null}
          />
        ) : filtered.length === 0 ? (
          <p className="text-center py-12 text-slate-600 text-sm">No runbooks match your filter.</p>
        ) : (
          filtered.map((rb) => (
            <RunbookCard
              key={rb.id}
              rb={rb}
              canManage={canManage}
              onEdit={(item) => setEditor(item)}
              onDelete={handleDelete}
            />
          ))
        )}
      </div>

      {editor && (
        <RunbookEditorModal
          initial={editor === 'create' ? null : editor}
          onClose={() => setEditor(null)}
          onSaved={handleSaved}
        />
      )}
    </div>
  )
}
