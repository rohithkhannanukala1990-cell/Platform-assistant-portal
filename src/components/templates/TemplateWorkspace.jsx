import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Plus,
  Edit2,
  Trash2,
  Copy,
  Zap,
  Eye,
  CheckCircle,
  Package,
  ChevronRight,
  Settings,
  Users,
  Tag,
  Search,
  ArrowRight,
  Layers,
  BookOpen,
  RefreshCw,
  X,
  ChevronDown,
  ChevronUp,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../ToastNotification'
import { PermissionGate } from '../PermissionGate'

const ENV_OPTIONS = [
  { id: 'local', label: 'Local' },
  { id: 'development', label: 'Development' },
  { id: 'test', label: 'Test' },
  { id: 'staging', label: 'Staging' },
  { id: 'production', label: 'Production' },
  { id: 'dr', label: 'DR' },
]

const ICON_EMOJI_OPTIONS = ['📋', '🗂️', '🚨', '🚀', '💰', '👥', '🛠️', '🔒', '📊', '🔍', '⚡', '🌐', '🎯', '🔧']

const COLOR_SWATCHES = [
  '#6366f1',
  '#ef4444',
  '#8b5cf6',
  '#f59e0b',
  '#10b981',
  '#06b6d4',
  '#f43f5e',
  '#84cc16',
]

const CATEGORY_SELECT = [
  'general',
  'operations',
  'engineering',
  'onboarding',
  'finops',
  'security',
  'custom',
]

function emptyTemplateForm() {
  return {
    name: '',
    description: '',
    category: 'general',
    icon: '📋',
    color: '#6366f1',
    environment: 'production',
    tags: [],
    is_published: false,
  }
}

function flattenGroupedTools(grouped) {
  const out = []
  if (!grouped || typeof grouped !== 'object') return out
  for (const [, list] of Object.entries(grouped)) {
    if (Array.isArray(list)) {
      for (const t of list) out.push({ ...t })
    }
  }
  return out.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
}

function envBadgeClass(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production' || e === 'dr') return 'bg-rose-500/15 text-rose-200 border-rose-500/30'
  if (e === 'staging') return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
  return 'bg-slate-500/15 text-slate-200 border-slate-500/30'
}

function formatHints(hints) {
  if (hints == null) return null
  if (typeof hints === 'string') {
    try {
      return formatHints(JSON.parse(hints))
    } catch {
      return null
    }
  }
  if (typeof hints !== 'object') return null
  const keys = Object.keys(hints)
  return keys.length ? hints : null
}

/**
 * Create / edit / detail / apply flows for templates.
 * Renders `children({ openApply, openPreview, openCreate, openEdit, duplicateTemplate })`
 * when view is gallery; otherwise renders the active non-gallery screen.
 */
export default function TemplateWorkspace({ loadTemplates, isAdmin, children }) {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const navigate = useNavigate()

  const [view, setView] = useState('gallery')
  const [selectedTemplate, setSelectedTemplate] = useState(null)
  const [applyModal, setApplyModal] = useState({ open: false, template: null })
  const [applyForm, setApplyForm] = useState({ workspace_name: '', environment: '', description: '' })
  const [applyResult, setApplyResult] = useState(null)
  const [applySubmitting, setApplySubmitting] = useState(false)

  const [createForm, setCreateForm] = useState(emptyTemplateForm)
  const [editForm, setEditForm] = useState(emptyTemplateForm)
  const [tagDraft, setTagDraft] = useState('')
  const [editTagDraft, setEditTagDraft] = useState('')

  const [toolPickerOpen, setToolPickerOpen] = useState(false)
  const [availableTools, setAvailableTools] = useState([])
  const [toolSearchQuery, setToolSearchQuery] = useState('')
  const [pickerLoading, setPickerLoading] = useState(false)
  const [accountPick, setAccountPick] = useState({})
  const [pickerRequired, setPickerRequired] = useState(true)
  const [hintsExpanded, setHintsExpanded] = useState({})
  const [applications, setApplications] = useState([])
  const [showAddToolsPrompt, setShowAddToolsPrompt] = useState(false)

  const loadTemplateDetail = useCallback(
    async (id) => {
      try {
        const res = await authFetch(`/api/templates/${id}`)
        if (!res.ok) throw new Error(await res.text())
        const detail = await res.json()
        setSelectedTemplate(detail)
        return detail
      } catch (e) {
        showToast(e.message || 'Failed to load template', 'error')
        return null
      }
    },
    [authFetch, showToast]
  )

  const loadApplications = useCallback(
    async (templateId) => {
      if (!isAdmin) {
        setApplications([])
        return
      }
      try {
        const res = await authFetch(`/api/templates/${templateId}/applications`)
        if (!res.ok) {
          setApplications([])
          return
        }
        setApplications(await res.json())
      } catch {
        setApplications([])
      }
    },
    [authFetch, isAdmin]
  )

  useEffect(() => {
    if (view === 'detail' && selectedTemplate?.id) {
      void loadApplications(selectedTemplate.id)
    } else {
      setApplications([])
    }
  }, [view, selectedTemplate?.id, loadApplications])

  const openApply = (t) => {
    setApplyResult(null)
    setApplyForm({
      workspace_name: `${t.name} Workspace`,
      environment: t.environment || 'production',
      description: '',
    })
    setApplyModal({ open: true, template: t })
  }

  const submitApply = async () => {
    const t = applyModal.template
    if (!t?.id) return
    setApplySubmitting(true)
    try {
      const res = await authFetch(`/api/templates/${t.id}/apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          workspace_name: applyForm.workspace_name.trim() || undefined,
          environment: applyForm.environment.trim() || undefined,
          description: applyForm.description.trim() || undefined,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setApplyResult(data)
      showToast('Workspace created from template', 'success')
      void loadTemplates()
      if (view === 'detail' && selectedTemplate?.id === t.id) void loadTemplateDetail(t.id)
    } catch (e) {
      showToast(e.message || 'Apply failed', 'error')
    } finally {
      setApplySubmitting(false)
    }
  }

  const saveCreate = async () => {
    if (!createForm.name.trim()) {
      showToast('Template name is required', 'warning')
      return
    }
    try {
      const res = await authFetch('/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createForm.name.trim(),
          description: createForm.description || '',
          icon: createForm.icon,
          color: createForm.color,
          category: createForm.category,
          environment: createForm.environment,
          tags: createForm.tags,
          is_published: createForm.is_published,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const created = await res.json()
      showToast('Template created', 'success')
      await loadTemplates()
      const full = await loadTemplateDetail(created.id)
      if (full) {
        setView('detail')
        setShowAddToolsPrompt(true)
      }
    } catch (e) {
      showToast(e.message || 'Save failed', 'error')
    }
  }

  const saveEdit = async () => {
    if (!selectedTemplate?.id || !editForm.name.trim()) {
      showToast('Template name is required', 'warning')
      return
    }
    try {
      const res = await authFetch(`/api/templates/${selectedTemplate.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editForm.name.trim(),
          description: editForm.description || '',
          icon: editForm.icon,
          color: editForm.color,
          category: editForm.category,
          environment: editForm.environment,
          tags: editForm.tags,
          is_published: editForm.is_published,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Template updated', 'success')
      await loadTemplates()
      await loadTemplateDetail(selectedTemplate.id)
      setView('detail')
    } catch (e) {
      showToast(e.message || 'Update failed', 'error')
    }
  }

  const duplicateTemplate = async (t) => {
    if (!isAdmin) return
    try {
      const res = await authFetch(`/api/templates/${t.id}/duplicate`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      const dup = await res.json()
      showToast('Template duplicated', 'success')
      await loadTemplates()
      const full = await loadTemplateDetail(dup.id)
      if (full) setView('detail')
    } catch (e) {
      showToast(e.message || 'Duplicate failed', 'error')
    }
  }

  const deleteTemplate = async (t) => {
    if (!isAdmin) return
    if (!window.confirm(`Delete template "${t.name}"? It will be hidden from the gallery.`)) return
    try {
      const res = await authFetch(`/api/templates/${t.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      showToast('Template deleted', 'success')
      setSelectedTemplate(null)
      setView('gallery')
      await loadTemplates()
    } catch (e) {
      showToast(e.message || 'Delete failed', 'error')
    }
  }

  const openToolPicker = async () => {
    setToolPickerOpen(true)
    setToolSearchQuery('')
    setAccountPick({})
    setPickerRequired(true)
    setPickerLoading(true)
    try {
      const res = await authFetch('/api/tools')
      if (!res.ok) throw new Error(await res.text())
      const grouped = await res.json()
      const flat = flattenGroupedTools(grouped)
      const enriched = await Promise.all(
        flat.map(async (tool) => {
          const ar = await authFetch(`/api/tools/${tool.id}/accounts`)
          const list = ar.ok ? await ar.json() : []
          const accounts = list.filter((a) => a.is_active)
          return { ...tool, accounts }
        })
      )
      setAvailableTools(enriched)
    } catch (e) {
      showToast(e.message || 'Failed to load tools', 'error')
      setAvailableTools([])
    } finally {
      setPickerLoading(false)
    }
  }

  const templateHasTool = (toolId) =>
    (selectedTemplate?.tools || []).some((row) => row.tool_id === toolId)

  const addToolToTemplate = async (toolId, accountId) => {
    if (!selectedTemplate?.id) return
    const aid = accountId || null
    try {
      const res = await authFetch(`/api/templates/${selectedTemplate.id}/tools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_id: toolId,
          account_id: aid || undefined,
          display_order: (selectedTemplate.tools || []).length,
          is_required: pickerRequired,
          config_hints: {},
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const body = await res.json()
      if (body.already_exists) {
        showToast('Tool already on template', 'warning')
      } else {
        showToast('Tool added to template', 'success')
      }
      await loadTemplateDetail(selectedTemplate.id)
    } catch (e) {
      showToast(e.message || 'Add failed', 'error')
    }
  }

  const removeToolFromTemplate = async (toolId) => {
    if (!selectedTemplate?.id) return
    try {
      const res = await authFetch(`/api/templates/${selectedTemplate.id}/tools/${toolId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Tool removed', 'success')
      await loadTemplateDetail(selectedTemplate.id)
    } catch (e) {
      showToast(e.message || 'Remove failed', 'error')
    }
  }

  const filteredPickerTools = useMemo(() => {
    const q = toolSearchQuery.toLowerCase().trim()
    if (!q) return availableTools
    return availableTools.filter(
      (t) =>
        (t.name || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
    )
  }, [availableTools, toolSearchQuery])

  const populateEditFromTemplate = (d) => {
    setEditForm({
      name: d.name,
      description: d.description || '',
      category: d.category || 'general',
      icon: d.icon || '📋',
      color: d.color || '#6366f1',
      environment: d.environment || 'production',
      tags: Array.isArray(d.tags) ? [...d.tags] : [],
      is_published: !!d.is_published,
    })
    setEditTagDraft('')
  }

  const renderTagInput = (form, setForm, draft, setDraft) => (
    <div>
      <label className="block text-xs font-semibold text-slate-400 uppercase mb-2 flex items-center gap-1">
        <Tag className="w-3.5 h-3.5" aria-hidden />
        Tags
      </label>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            const v = draft.trim()
            if (v && !form.tags.includes(v)) {
              setForm({ ...form, tags: [...form.tags, v] })
              setDraft('')
            }
          }
        }}
        placeholder="Type a tag and press Enter"
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
      />
      <div className="flex flex-wrap gap-2 mt-2">
        {form.tags.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => setForm({ ...form, tags: form.tags.filter((x) => x !== tag) })}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-800 text-xs text-slate-200 border border-border"
          >
            {tag}
            <X className="w-3 h-3" />
          </button>
        ))}
      </div>
    </div>
  )

  const renderForm = (isEdit) => {
    const form = isEdit ? editForm : createForm
    const setForm = isEdit ? setEditForm : setCreateForm
    const draft = isEdit ? editTagDraft : tagDraft
    const setDraft = isEdit ? setEditTagDraft : setTagDraft

    return (
      <div className="max-w-2xl mx-auto space-y-6 pb-16">
        <div className="flex items-center gap-2 text-slate-400">
          <Settings className="w-5 h-5 text-indigo-400" aria-hidden />
          <h2 className="text-xl font-bold text-white">
            {isEdit ? 'Edit Template' : 'Create Template'}
          </h2>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">
            Template Name *
          </label>
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white"
            placeholder="e.g. Incident Response Team"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Description</label>
          <textarea
            rows={3}
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white resize-none"
          />
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Category</label>
          <select
            value={form.category}
            onChange={(e) => setForm({ ...form, category: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white"
          >
            {CATEGORY_SELECT.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Icon</label>
          <div className="flex flex-wrap gap-2">
            {ICON_EMOJI_OPTIONS.map((ic) => (
              <button
                key={ic}
                type="button"
                onClick={() => setForm({ ...form, icon: ic })}
                className={`text-xl w-11 h-11 rounded-lg border flex items-center justify-center transition-colors ${
                  form.icon === ic ? 'border-blue-500 bg-blue-500/20' : 'border-border bg-slate-900 hover:border-slate-500'
                }`}
              >
                {ic}
              </button>
            ))}
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Color</label>
          <div className="flex flex-wrap gap-2">
            {COLOR_SWATCHES.map((c) => (
              <button
                key={c}
                type="button"
                aria-label={c}
                onClick={() => setForm({ ...form, color: c })}
                className={`w-10 h-10 rounded-full border-2 shrink-0 transition-transform ${
                  form.color === c ? 'border-white scale-110' : 'border-transparent'
                }`}
                style={{ backgroundColor: c }}
              />
            ))}
          </div>
        </div>
        <div>
          <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Environment</label>
          <select
            value={form.environment}
            onChange={(e) => setForm({ ...form, environment: e.target.value })}
            className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white"
          >
            {ENV_OPTIONS.map((e) => (
              <option key={e.id} value={e.id}>
                {e.label}
              </option>
            ))}
          </select>
        </div>
        {renderTagInput(form, setForm, draft, setDraft)}
        <label className="flex items-center gap-3 cursor-pointer">
          <input
            type="checkbox"
            checked={form.is_published}
            onChange={(e) => setForm({ ...form, is_published: e.target.checked })}
            className="rounded border-slate-500"
          />
          <span className="text-sm text-slate-300">Published (live in gallery for all users)</span>
        </label>
        <div className="flex justify-between gap-3 pt-4">
          <button
            type="button"
            onClick={() => {
              if (isEdit && selectedTemplate) {
                setView('detail')
              } else {
                setView('gallery')
              }
            }}
            className="px-4 py-2 rounded-lg border border-border text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void (isEdit ? saveEdit() : saveCreate())}
            className="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
          >
            {isEdit ? 'Save Template' : 'Create Template'}
          </button>
        </div>
      </div>
    )
  }

  function renderApplyModal() {
    const mt = applyModal.template
    const previewRows =
      Array.isArray(mt?.tools_preview) && mt.tools_preview.length
        ? mt.tools_preview
        : Array.isArray(mt?.tools)
          ? mt.tools.map((r) => ({
              tool_id: r.tool_id,
              name: r.tool_name,
              icon: r.tool_icon,
            }))
          : []
    const previewCount =
      mt?.tool_count ??
      (Array.isArray(mt?.tools) ? mt.tools.length : previewRows.length)

    return (
      <div
        className="fixed inset-0 z-[90] flex items-center justify-center p-4 bg-black/70"
        role="dialog"
        aria-modal="true"
        onClick={() => {
          setApplyModal({ open: false, template: null })
          setApplyResult(null)
        }}
      >
        <div
          className="w-full max-w-md rounded-xl border border-border bg-slate-950 shadow-2xl p-6"
          onClick={(e) => e.stopPropagation()}
        >
          {applyResult?.workspace ? (
            <>
              <div className="flex items-center gap-2 text-emerald-400 mb-2">
                <CheckCircle className="w-6 h-6" />
                <span className="font-bold text-lg text-white">Workspace Created!</span>
              </div>
              <p className="text-slate-300 text-sm mt-2">
                &quot;{applyResult.workspace.name}&quot; is ready with {applyResult.tools_added} tools
              </p>
              <button
                type="button"
                className="mt-6 w-full inline-flex items-center justify-center gap-2 py-3 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                onClick={() => {
                  const wid = applyResult.workspace?.id
                  setApplyModal({ open: false, template: null })
                  setApplyResult(null)
                  if (wid) navigate(`/ops?view=workspaces&ws=${encodeURIComponent(wid)}`)
                }}
              >
                Open Workspace
                <ArrowRight className="w-4 h-4" />
              </button>
              <button
                type="button"
                className="mt-3 w-full py-2 text-sm text-slate-400 hover:text-white"
                onClick={() => {
                  setApplyModal({ open: false, template: null })
                  setApplyResult(null)
                }}
              >
                Close
              </button>
            </>
          ) : (
            <>
              <h3 className="text-lg font-bold text-white">Apply Template: {mt?.name}</h3>
              <p className="text-sm text-slate-400 mt-1">
                This will create a new workspace with {previewCount} pre-configured tools
              </p>
              <div className="flex flex-wrap gap-2 mt-4">
                {previewRows.map((p) => (
                  <span key={p.tool_id} className="text-sm text-slate-300 inline-flex items-center gap-1">
                    <span>{p.icon || '🔧'}</span>
                    {p.name}
                  </span>
                ))}
              </div>
              <p className="text-xs text-slate-500 mt-2">{previewCount} tools will be added automatically</p>
              <div className="mt-4 space-y-3">
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Workspace Name</label>
                  <input
                    value={applyForm.workspace_name}
                    onChange={(e) => setApplyForm((f) => ({ ...f, workspace_name: e.target.value }))}
                    placeholder={`${mt?.name || 'Template'} Workspace`}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Description (optional)</label>
                  <input
                    value={applyForm.description}
                    onChange={(e) => setApplyForm((f) => ({ ...f, description: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  />
                </div>
                <div>
                  <label className="block text-xs text-slate-400 mb-1">Environment</label>
                  <select
                    value={applyForm.environment}
                    onChange={(e) => setApplyForm((f) => ({ ...f, environment: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  >
                    {ENV_OPTIONS.map((e) => (
                      <option key={e.id} value={e.id}>
                        {e.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <div className="flex flex-col gap-2 mt-6">
                <button
                  type="button"
                  disabled={applySubmitting}
                  onClick={() => void submitApply()}
                  className="w-full inline-flex items-center justify-center gap-2 py-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-semibold"
                >
                  <Zap className="w-4 h-4" />
                  Create Workspace from Template
                </button>
                <button
                  type="button"
                  className="w-full py-2 rounded-lg border border-border text-slate-300 hover:bg-slate-800 text-sm"
                  onClick={() => {
                    setApplyModal({ open: false, template: null })
                    setApplyResult(null)
                  }}
                >
                  Cancel
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    )
  }

  if (view === 'create') {
    return (
      <div className="max-w-5xl mx-auto w-full">
        <nav className="text-xs text-slate-500 mb-6 flex items-center gap-1">
          <button type="button" className="hover:text-blue-400 flex items-center gap-1" onClick={() => setView('gallery')}>
            <BookOpen className="w-3.5 h-3.5" />
            Templates
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300">Create</span>
        </nav>
        {renderForm(false)}
      </div>
    )
  }

  if (view === 'edit' && selectedTemplate) {
    return (
      <div className="max-w-5xl mx-auto w-full">
        <nav className="text-xs text-slate-500 mb-6 flex items-center gap-1 flex-wrap">
          <button type="button" className="hover:text-blue-400" onClick={() => setView('gallery')}>
            Templates
          </button>
          <ChevronRight className="w-3 h-3" />
          <button
            type="button"
            className="hover:text-blue-400 truncate max-w-[200px]"
            onClick={() => setView('detail')}
          >
            {selectedTemplate.name}
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300">Edit</span>
        </nav>
        {renderForm(true)}
      </div>
    )
  }

  if (view === 'detail' && selectedTemplate) {
    const t = selectedTemplate
    const tools = t.tools || []

    return (
      <div className="max-w-5xl mx-auto w-full space-y-8 pb-16">
        <nav className="text-xs text-slate-500 flex items-center gap-1 flex-wrap">
          <button type="button" className="hover:text-blue-400" onClick={() => setView('gallery')}>
            Templates
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300 font-medium">{t.name}</span>
        </nav>

        {showAddToolsPrompt ? (
          <div className="rounded-xl border border-blue-500/40 bg-blue-500/10 px-4 py-3 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <p className="text-sm text-blue-100">Now add tools to this template →</p>
            <button
              type="button"
              onClick={() => {
                setShowAddToolsPrompt(false)
                void openToolPicker()
              }}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white text-sm font-semibold shrink-0"
            >
              <Plus className="w-4 h-4" />
              Add Tool
            </button>
          </div>
        ) : null}

        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
          <div className="flex gap-4 min-w-0">
            <span className="text-5xl shrink-0">{t.icon}</span>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold text-white">{t.name}</h1>
              <p className="text-slate-400 mt-1">{t.description || '—'}</p>
              <div className="flex flex-wrap gap-2 mt-3 items-center">
                <Layers className="w-4 h-4 text-slate-500 shrink-0" aria-hidden />
                <span className="px-2 py-0.5 rounded-md bg-slate-800 text-xs capitalize text-slate-200">{t.category}</span>
                <span className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase ${envBadgeClass(t.environment)}`}>
                  {t.environment}
                </span>
                <span className="text-xs text-slate-500">{t.use_count ?? 0} uses</span>
              </div>
              <div className="flex flex-wrap gap-2 mt-3">
                {(t.tags || []).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 rounded-md text-xs font-medium border"
                    style={{
                      borderColor: `${t.color}55`,
                      backgroundColor: `${t.color}18`,
                      color: '#e2e8f0',
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={() => openApply(t)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-sm font-semibold"
            >
              <Zap className="w-4 h-4" />
              Apply
            </button>
            {isAdmin ? (
              <>
                <PermissionGate resource="templates" action="update">
                  <button
                    type="button"
                    onClick={() => {
                      populateEditFromTemplate(t)
                      setView('edit')
                    }}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 border border-border text-sm text-white"
                  >
                    <Edit2 className="w-4 h-4" />
                    Edit
                  </button>
                </PermissionGate>
                <PermissionGate resource="templates" action="create">
                  <button
                    type="button"
                    onClick={() => void duplicateTemplate(t)}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 border border-border text-sm text-white"
                  >
                    <Copy className="w-4 h-4" />
                    Duplicate
                  </button>
                </PermissionGate>
                <PermissionGate resource="templates" action="delete">
                  <button
                    type="button"
                    onClick={() => void deleteTemplate(t)}
                    className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-900/50 border border-red-800 text-sm text-red-100"
                  >
                    <Trash2 className="w-4 h-4" />
                    Delete
                  </button>
                </PermissionGate>
              </>
            ) : null}
          </div>
        </div>

        <section>
          <div className="flex items-center justify-between gap-4 mb-4">
            <h2 className="text-lg font-semibold text-white">Included Tools ({tools.length})</h2>
            {isAdmin ? (
              <button
                type="button"
                onClick={() => void openToolPicker()}
                className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
              >
                <Plus className="w-4 h-4" /> Add Tool
              </button>
            ) : null}
          </div>
          {tools.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-10 text-center text-slate-400">
              No tools on this template yet.
            </div>
          ) : (
            <ul className="space-y-2">
              {tools.map((row) => {
                const hints = formatHints(row.config_hints)
                const exp = hintsExpanded[row.id]
                return (
                  <li
                    key={row.id}
                    className="rounded-xl border border-border bg-card/30 px-4 py-3 flex flex-col gap-2"
                  >
                    <div className="flex items-start gap-3">
                      <span className="text-xl shrink-0">{row.tool_icon || '🔧'}</span>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-white">{row.tool_name}</div>
                        {row.account_id ? (
                          <div className="text-xs text-slate-500 mt-0.5">Linked account: {row.account_id}</div>
                        ) : null}
                        {hints ? (
                          <button
                            type="button"
                            className="mt-2 text-xs text-blue-400 inline-flex items-center gap-1"
                            onClick={() => setHintsExpanded((prev) => ({ ...prev, [row.id]: !prev[row.id] }))}
                          >
                            {exp ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
                            Config hints
                          </button>
                        ) : null}
                        {exp && hints ? (
                          <pre className="mt-2 text-[10px] bg-slate-950 p-2 rounded-lg overflow-x-auto text-slate-300">
                            {JSON.stringify(hints, null, 2)}
                          </pre>
                        ) : null}
                      </div>
                      <div className="flex flex-col items-end gap-2 shrink-0">
                        <span
                          className={`text-[10px] px-2 py-0.5 rounded-md border font-semibold uppercase ${
                            row.is_required ? 'border-amber-500/50 text-amber-200' : 'border-slate-500 text-slate-400'
                          }`}
                        >
                          {row.is_required ? 'Required' : 'Optional'}
                        </span>
                        {isAdmin ? (
                          <PermissionGate resource="templates" action="update">
                            <button
                              type="button"
                              onClick={() => void removeToolFromTemplate(row.tool_id)}
                              className="p-1.5 rounded-lg hover:bg-red-950/50 text-red-400"
                              aria-label="Remove tool"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </PermissionGate>
                        ) : null}
                      </div>
                    </div>
                  </li>
                )
              })}
            </ul>
          )}
        </section>

        <section>
          <h2 className="text-lg font-semibold text-white mb-4 flex items-center gap-2">
            <Users className="w-5 h-5 text-slate-400" aria-hidden />
            Applied {t.use_count ?? 0} times
          </h2>
          {!isAdmin ? (
            <p className="text-sm text-slate-500">Application history is visible to admins.</p>
          ) : applications.length === 0 ? (
            <p className="text-sm text-slate-500">Not applied yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-sm text-left">
                <thead className="bg-slate-900/80 text-slate-400 text-xs uppercase">
                  <tr>
                    <th className="px-4 py-2">Workspace</th>
                    <th className="px-4 py-2">Applied by</th>
                    <th className="px-4 py-2">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {applications.map((a) => (
                    <tr key={`${a.workspace_id}-${a.applied_at}`} className="border-t border-border">
                      <td className="px-4 py-2 text-white">{a.workspace_name}</td>
                      <td className="px-4 py-2 text-slate-400">{a.applied_by}</td>
                      <td className="px-4 py-2 text-slate-400">
                        {a.applied_at ? new Date(a.applied_at).toLocaleString() : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        {toolPickerOpen && (
          <div
            className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tmpl-tool-picker-title"
            onClick={() => setToolPickerOpen(false)}
          >
            <div
              className="w-full max-w-lg max-h-[85vh] flex flex-col rounded-xl border border-border bg-slate-950 shadow-2xl"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex items-center justify-between px-4 py-3 border-b border-border">
                <h3 id="tmpl-tool-picker-title" className="font-semibold text-white">
                  Add Tool to Template
                </h3>
                <button
                  type="button"
                  className="p-2 rounded-lg hover:bg-slate-800 text-slate-400"
                  onClick={() => setToolPickerOpen(false)}
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="px-4 py-2 border-b border-border flex items-center justify-between gap-3 flex-wrap">
                <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={pickerRequired}
                    onChange={(e) => setPickerRequired(e.target.checked)}
                    className="rounded border-slate-500"
                  />
                  Required on workspace
                </label>
              </div>
              <div className="px-4 py-3 border-b border-border">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input
                    value={toolSearchQuery}
                    onChange={(e) => setToolSearchQuery(e.target.value)}
                    placeholder="Search tools…"
                    className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                </div>
              </div>
              <div className="overflow-y-auto flex-1 p-2">
                {pickerLoading ? (
                  <p className="text-center text-slate-400 py-8">Loading tools…</p>
                ) : (
                  filteredPickerTools.map((tool) => {
                    const pickKey = tool.id
                    const selAcc =
                      accountPick[pickKey] !== undefined
                        ? accountPick[pickKey]
                        : tool.accounts?.length === 1
                          ? tool.accounts[0].id
                          : ''
                    const added = templateHasTool(tool.id)
                    return (
                      <div
                        key={tool.id}
                        className="flex flex-col gap-2 rounded-lg border border-border/60 p-3 mb-2 bg-slate-900/40"
                      >
                        <div className="flex items-center gap-2">
                          <span className="text-lg">{tool.icon || '🔧'}</span>
                          <div className="flex-1 min-w-0">
                            <div className="font-medium text-white truncate">{tool.name}</div>
                            <div className="text-[10px] text-slate-500 uppercase">{tool.category}</div>
                          </div>
                        </div>
                        {tool.accounts?.length > 0 ? (
                          <select
                            value={selAcc}
                            onChange={(e) =>
                              setAccountPick((prev) => ({ ...prev, [pickKey]: e.target.value }))
                            }
                            className="w-full text-sm px-2 py-1.5 rounded-lg bg-slate-900 border border-border text-white"
                          >
                            <option value="">No specific account</option>
                            {tool.accounts.map((a) => (
                              <option key={a.id} value={a.id}>
                                {a.account_name} ({a.environment})
                              </option>
                            ))}
                          </select>
                        ) : null}
                        <button
                          type="button"
                          disabled={added}
                          onClick={() => void addToolToTemplate(tool.id, selAcc || null)}
                          className={`w-full py-2 rounded-lg text-xs font-semibold ${
                            added
                              ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                              : 'bg-blue-600 hover:bg-blue-500 text-white'
                          }`}
                        >
                          <Plus className="w-3.5 h-3.5 inline mr-1 align-text-bottom" />
                          {added ? 'On template' : 'Add to Template'}
                        </button>
                      </div>
                    )
                  })
                )}
              </div>
            </div>
          </div>
        )}

        {applyModal.open ? renderApplyModal() : null}
      </div>
    )
  }


  // Gallery composition is owned by TemplateGallery; expose actions via children.
  return (
    <>
      {children({
        openApply,
        openPreview: (t) => {
          void loadTemplateDetail(t.id).then((d) => {
            if (d) {
              setView('detail')
              setShowAddToolsPrompt(false)
            }
          })
        },
        openCreate: () => {
          setCreateForm(emptyTemplateForm())
          setTagDraft('')
          setView('create')
        },
        openEdit: (t) => {
          void loadTemplateDetail(t.id).then((d) => {
            if (!d) return
            populateEditFromTemplate(d)
            setView('edit')
          })
        },
        duplicateTemplate,
        applyModalNode: applyModal.open ? renderApplyModal() : null,
      })}
    </>
  )
}
