import { useState, useEffect, useCallback, useMemo, Fragment } from 'react'
import {
  Workflow,
  RefreshCw,
  Loader2,
  CheckCircle,
  X,
  Plus,
  Eye,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalWebSocket } from '../hooks/usePortalWebSocket'
import { parseConfigSchema, STATUS_COLORS } from './entityActionsShared'
import { PageHeader, EmptyState } from './ui'

const CATEGORIES = ['All', 'Onboarding', 'Operations', 'Quality', 'DevOps', 'Platform']

const CATEGORY_BADGE = {
  Onboarding: 'bg-green-500/20 text-green-300 border-green-500/30',
  Operations: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  Quality: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  DevOps: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  Platform: 'bg-teal-500/20 text-teal-300 border-teal-500/30',
  General: 'bg-gray-500/20 text-gray-300 border-gray-500/30',
}

const DEFAULT_STEPS = ['Configure', 'Review', 'Executing', 'Done']

function slugify(name) {
  return (name || '')
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9\s-]/g, '')
    .replace(/[\s_]+/g, '-')
    .replace(/-+/g, '-')
    .replace(/^-|-$/g, '') || 'golden-path'
}

function parseSteps(template) {
  try {
    const raw = template?.steps_json
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed) && parsed.length) {
      return parsed.map((s) => s.label || s.type || 'Step')
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_STEPS
}

function stepCount(template) {
  try {
    const raw = template?.steps_json
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    return Array.isArray(parsed) ? parsed.length : DEFAULT_STEPS.length
  } catch {
    return DEFAULT_STEPS.length
  }
}

function inferEntityId(formValues) {
  for (const key of ['service_id', 'entity_id']) {
    const v = formValues[key]
    if (v !== undefined && v !== '' && /^\d+$/.test(String(v))) {
      return parseInt(String(v), 10)
    }
  }
  return null
}

function GoldenPathFormFields({ schema, formValues, onChange }) {
  const fields = schema.fields || []
  if (!fields.length) {
    return <p className="text-gray-400 text-sm">No configuration required for this path.</p>
  }
  return (
    <div className="space-y-4">
      {fields.map((field) => (
        <label key={field.name} className="block">
          <span className="block text-xs font-medium text-gray-400 mb-1.5">
            {field.label || field.name}
            {field.required ? ' *' : ''}
          </span>
          {field.type === 'boolean' ? (
            <input
              type="checkbox"
              checked={Boolean(formValues[field.name])}
              onChange={(e) => onChange(field.name, 'boolean', e.target.checked)}
              className="rounded border-white/20"
            />
          ) : field.type === 'select' ? (
            <select
              value={formValues[field.name] ?? ''}
              onChange={(e) => onChange(field.name, 'select', e.target.value)}
              className="bg-card border border-border rounded-lg px-3 py-2 text-white w-full focus:outline-none focus:border-accent/50"
            >
              <option value="">Select…</option>
              {(field.options || []).map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : field.type === 'number' ? (
            <input
              type="number"
              value={formValues[field.name] ?? ''}
              onChange={(e) => onChange(field.name, 'number', e.target.value)}
              placeholder={field.placeholder || ''}
              className="bg-card border border-border rounded-lg px-3 py-2 text-white placeholder-gray-500 w-full focus:outline-none focus:border-accent/50"
            />
          ) : (
            <input
              type="text"
              value={formValues[field.name] ?? ''}
              onChange={(e) => onChange(field.name, 'string', e.target.value)}
              placeholder={field.placeholder || ''}
              className="bg-card border border-border rounded-lg px-3 py-2 text-white placeholder-gray-500 w-full focus:outline-none focus:border-accent/50"
            />
          )}
        </label>
      ))}
    </div>
  )
}

function LaunchWizardModal({ template, onClose, onSuccess, authFetch, onRunComplete, wizardRunStatus }) {
  const steps = useMemo(() => parseSteps(template), [template])
  const schema = useMemo(() => parseConfigSchema(template), [template])
  const [step, setStep] = useState(0)
  const [formValues, setFormValues] = useState({})
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)
  const [launching, setLaunching] = useState(false)

  useEffect(() => {
    const initial = {}
    for (const field of schema.fields || []) {
      if (field.default !== undefined) initial[field.name] = field.default
      else if (field.type === 'boolean') initial[field.name] = false
    }
    setFormValues(initial)
    setStep(0)
    setResult(null)
    setError(null)
  }, [template?.id, schema])

  useEffect(() => {
    if (!wizardRunStatus || step < 2) return
    if (wizardRunStatus === 'done') {
      setStep(3)
      setLaunching(false)
    } else if (wizardRunStatus === 'failed') {
      setError('Golden path run failed')
      setLaunching(false)
    }
  }, [wizardRunStatus, step])

  const handleFieldChange = (name, type, value) => {
    setFormValues((prev) => ({
      ...prev,
      [name]: type === 'boolean' ? Boolean(value) : value,
    }))
  }

  const validateForm = () => {
    for (const field of schema.fields || []) {
      if (field.required && (formValues[field.name] === undefined || formValues[field.name] === '')) {
        return `${field.label || field.name} is required.`
      }
    }
    return null
  }

  const handleLaunch = async () => {
    setError(null)
    setLaunching(true)
    setStep(2)
    try {
      const res = await authFetch(`/api/golden-paths/${template.id}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          entity_id: inferEntityId(formValues),
          inputs: formValues,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setResult(data)
      setStep(3)
      onRunComplete?.(data)
    } catch (e) {
      setError(e.message || 'Launch failed')
    } finally {
      setLaunching(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl p-6 w-full max-w-lg shadow-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">{template.name}</h2>
            <p className="text-sm text-gray-400 mt-0.5">{template.description}</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10"
          >
            <X size={20} />
          </button>
        </div>

        <div className="flex items-center gap-2 mb-6">
          {steps.map((stepLabel, i) => (
            <Fragment key={i}>
              <div className={`flex items-center gap-2 ${i <= step ? 'text-accent' : 'text-gray-600'}`}>
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold ${
                    i < step
                      ? 'bg-green-600 text-white'
                      : i === step
                        ? 'bg-accent text-white'
                        : 'bg-white/10 text-gray-500'
                  }`}
                >
                  {i < step ? '✓' : i + 1}
                </div>
                <span className="text-xs hidden sm:block">{stepLabel}</span>
              </div>
              {i < steps.length - 1 && (
                <div className={`flex-1 h-px ${i < step ? 'bg-accent' : 'bg-white/10'}`} />
              )}
            </Fragment>
          ))}
        </div>

        {step === 0 && (
          <>
            <GoldenPathFormFields schema={schema} formValues={formValues} onChange={handleFieldChange} />
            <div className="flex justify-end mt-6">
              <button
                type="button"
                onClick={() => {
                  const err = validateForm()
                  if (err) {
                    setError(err)
                    return
                  }
                  setError(null)
                  setStep(1)
                }}
                className="px-4 py-2 bg-accent hover:bg-accent/90 text-white rounded-lg text-sm font-semibold"
              >
                Next →
              </button>
            </div>
          </>
        )}

        {step === 1 && (
          <>
            <div className="rounded-lg border border-border overflow-hidden mb-4">
              <table className="w-full text-sm">
                <tbody>
                  {Object.entries(formValues).map(([key, val]) => (
                    <tr key={key} className="border-b border-border">
                      <td className="px-3 py-2 text-gray-500 capitalize">{key.replace(/_/g, ' ')}</td>
                      <td className="px-3 py-2 text-white">{String(val)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {error && <p className="text-sm text-red-400 mb-3">{error}</p>}
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setStep(0)}
                className="flex-1 py-2 rounded-lg border border-border text-gray-300 text-sm"
              >
                ← Back
              </button>
              <button
                type="button"
                disabled={launching}
                onClick={() => void handleLaunch()}
                className="flex-1 py-2 rounded-lg bg-accent hover:bg-accent/90 text-white text-sm font-semibold disabled:opacity-50"
              >
                Launch →
              </button>
            </div>
          </>
        )}

        {step === 2 && (
          <div className="flex flex-col items-center py-12">
            <Loader2 size={40} className="text-accent animate-spin mb-4" />
            <p className="text-white font-medium">Executing Golden Path...</p>
            <p className="text-gray-400 text-sm mt-1">This may take a moment</p>
            {error && !launching && (
              <p className="text-sm text-red-400 mt-4 text-center">{error}</p>
            )}
          </div>
        )}

        {step === 3 && result && (
          <div className="flex flex-col items-center py-8">
            <CheckCircle size={48} className="text-green-400 mb-4" />
            <h3 className="text-lg font-semibold text-white mb-2">Completed Successfully</h3>
            <p className="text-gray-400 text-sm text-center max-w-sm">
              {result?.outputs?.message || 'Golden path executed successfully.'}
            </p>
            <div className="mt-4 bg-card border border-border rounded-lg p-4 w-full text-left">
              <p className="text-xs text-gray-500 mb-2 font-mono">Run Summary</p>
              <pre className="text-xs text-green-300 font-mono whitespace-pre-wrap overflow-x-auto">
                {JSON.stringify(result, null, 2)}
              </pre>
            </div>
            <button
              type="button"
              onClick={onSuccess}
              className="mt-6 px-6 py-2 bg-accent hover:bg-accent/90 text-white rounded-lg transition-colors"
            >
              Done
            </button>
          </div>
        )}
      </div>
    </div>
  )
}

function RunLogsModal({ run, onClose }) {
  const statusClass = STATUS_COLORS[run?.status] || STATUS_COLORS.pending
  return (
    <>
      <button type="button" aria-label="Close" className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <aside className="fixed right-0 top-0 h-full w-full max-w-[480px] z-50 bg-surface border-l border-border p-6 overflow-y-auto">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Run Logs</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>
        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium mb-4 ${statusClass}`}>
          {run?.status}
        </span>
        <p className="text-xs text-gray-400 mb-4">
          {run?.template_name || `Template #${run?.template_id}`} · {run?.requested_by} ·{' '}
          {run?.created_at ? new Date(run.created_at).toLocaleString() : '—'}
        </p>
        {run?.run_logs ? (
          <pre className="text-xs text-green-300 font-mono bg-card border border-border p-4 rounded-lg whitespace-pre-wrap">
            {run.run_logs}
          </pre>
        ) : (
          <p className="text-sm text-gray-500">No logs available for this run.</p>
        )}
      </aside>
    </>
  )
}

function NewTemplateModal({ onClose, onCreated, authFetch }) {
  const [form, setForm] = useState({
    name: '',
    slug: '',
    description: '',
    category: 'General',
    entity_kind: 'Service',
    is_active: true,
    config_schema_json: '{"fields": []}',
    steps_json: JSON.stringify(
      [
        { type: 'form', label: 'Configure' },
        { type: 'review', label: 'Review' },
        { type: 'execute', label: 'Executing' },
        { type: 'complete', label: 'Done' },
      ],
      null,
      2
    ),
  })
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)

  const handleName = (name) => {
    setForm((f) => ({
      ...f,
      name,
      slug: f.slug || slugify(name),
    }))
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) {
      setError('Name is required')
      return
    }
    setSaving(true)
    setError(null)
    try {
      const res = await authFetch('/api/golden-paths', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: form.name.trim(),
          slug: form.slug.trim() || slugify(form.name),
          description: form.description,
          category: form.category,
          entity_kind: form.entity_kind || null,
          is_active: form.is_active,
          config_schema_json: form.config_schema_json,
          steps_json: form.steps_json,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      onCreated(await res.json())
    } catch (err) {
      setError(err.message || 'Failed to create template')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <form
        onSubmit={(e) => void submit(e)}
        className="bg-surface border border-border rounded-2xl p-6 w-full max-w-lg max-h-[90vh] overflow-y-auto"
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">New Golden Path Template</h2>
          <button type="button" onClick={onClose} className="text-gray-400 hover:text-white">
            <X size={20} />
          </button>
        </div>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs text-gray-400">Name *</span>
            <input
              value={form.name}
              onChange={(e) => handleName(e.target.value)}
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-400">Slug</span>
            <input
              value={form.slug}
              onChange={(e) => setForm((f) => ({ ...f, slug: e.target.value }))}
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm font-mono"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-400">Description</span>
            <textarea
              rows={2}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm resize-none"
            />
          </label>
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs text-gray-400">Category</span>
              <select
                value={form.category}
                onChange={(e) => setForm((f) => ({ ...f, category: e.target.value }))}
                className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              >
                {CATEGORIES.filter((c) => c !== 'All').map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </label>
            <label className="block">
              <span className="text-xs text-gray-400">Entity kind</span>
              <select
                value={form.entity_kind}
                onChange={(e) => setForm((f) => ({ ...f, entity_kind: e.target.value }))}
                className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-sm"
              >
                {['Service', 'API', 'Component', 'Library', 'Database'].map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="flex items-center gap-2 text-sm text-gray-300">
            <input
              type="checkbox"
              checked={form.is_active}
              onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.checked }))}
            />
            Active
          </label>
          <label className="block">
            <span className="text-xs text-gray-400">config_schema_json</span>
            <textarea
              rows={4}
              value={form.config_schema_json}
              onChange={(e) => setForm((f) => ({ ...f, config_schema_json: e.target.value }))}
              placeholder='{"fields":[{"name":"field","label":"Label","type":"string","required":true}]}'
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-xs font-mono resize-none"
            />
          </label>
          <label className="block">
            <span className="text-xs text-gray-400">steps_json</span>
            <textarea
              rows={3}
              value={form.steps_json}
              onChange={(e) => setForm((f) => ({ ...f, steps_json: e.target.value }))}
              placeholder='[{"type":"form","label":"Configure"},...]'
              className="mt-1 w-full bg-card border border-border rounded-lg px-3 py-2 text-white text-xs font-mono resize-none"
            />
          </label>
        </div>
        {error && <p className="text-sm text-red-400 mt-3">{error}</p>}
        <div className="flex gap-2 mt-6">
          <button
            type="button"
            onClick={onClose}
            className="flex-1 py-2 rounded-lg border border-border text-gray-300 text-sm"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            className="flex-1 py-2 rounded-lg bg-accent hover:bg-accent/90 text-white text-sm font-semibold disabled:opacity-50"
          >
            {saving ? 'Saving…' : 'Create Template'}
          </button>
        </div>
      </form>
    </div>
  )
}

function TemplateCard({ template, onLaunch }) {
  const badge = CATEGORY_BADGE[template.category] || CATEGORY_BADGE.General
  const n = stepCount(template)

  return (
    <div className="bg-card border border-border rounded-xl p-5 hover:border-white/20 transition-all flex flex-col min-h-[200px]">
      <span className={`inline-flex w-fit px-2 py-0.5 rounded text-[10px] font-semibold border ${badge}`}>
        {template.category}
      </span>
      <h3 className="font-semibold text-white text-base mt-2">{template.name}</h3>
      <p className="text-gray-400 text-sm mt-1 line-clamp-2 flex-1">{template.description || '—'}</p>
      {template.entity_kind && (
        <span className="inline-block mt-2 text-[10px] text-gray-500 bg-white/5 border border-border px-2 py-0.5 rounded w-fit">
          {template.entity_kind}
        </span>
      )}
      <p className="text-gray-500 text-xs mt-2">{n} steps</p>
      <div className="mt-4 flex justify-end">
        <button
          type="button"
          onClick={onLaunch}
          className="bg-accent hover:bg-accent/90 text-white text-sm px-4 py-1.5 rounded-lg font-semibold transition-colors"
        >
          Launch
        </button>
      </div>
    </div>
  )
}

export default function GoldenPathsPage() {
  const { authFetch, user } = useAuth()
  const { role } = useAuth()
  const isAdmin = role === 'Admin'

  const [templates, setTemplates] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [runsLoading, setRunsLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState(null)
  const [activeTab, setActiveTab] = useState('templates')
  const [activeCategory, setActiveCategory] = useState('All')
  const [searchTerm, setSearchTerm] = useState('')
  const [launchingTemplate, setLaunchingTemplate] = useState(null)
  const [selectedRun, setSelectedRun] = useState(null)
  const [showNewModal, setShowNewModal] = useState(false)
  const [toast, setToast] = useState(null)
  const [activeRunId, setActiveRunId] = useState(null)
  const [wizardRunStatus, setWizardRunStatus] = useState(null)

  const showToastMsg = useCallback((msg) => {
    setToast(msg)
    window.setTimeout(() => setToast(null), 4000)
  }, [])

  const fetchTemplates = useCallback(async () => {
    try {
      const res = await authFetch('/api/golden-paths')
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setTemplates(Array.isArray(data) ? data : [])
    } catch (e) {
      setError(e.message || 'Failed to load templates')
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  const fetchRuns = useCallback(async () => {
    try {
      const res = await authFetch('/api/golden-path-runs')
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      setRuns(Array.isArray(data) ? data : [])
    } catch (e) {
      setRuns([])
    } finally {
      setRunsLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void fetchTemplates()
    void fetchRuns()
  }, [fetchTemplates, fetchRuns])

  usePortalWebSocket({
    userId: user?.username || 'anonymous',
    onMessage: useCallback(
      (msg) => {
        if (msg.type === 'golden_path_run_update') {
          if (activeRunId != null && String(activeRunId) === String(msg.run_id)) {
            setWizardRunStatus(msg.status === 'completed' ? 'done' : 'failed')
          }
          setRuns((prev) =>
            prev.map((r) =>
              String(r.id) === String(msg.run_id) ? { ...r, status: msg.status } : r
            )
          )
        }
      },
      [activeRunId]
    ),
  })

  const handleRefresh = async () => {
    setRefreshing(true)
    setLoading(true)
    setRunsLoading(true)
    setError(null)
    await Promise.all([fetchTemplates(), fetchRuns()])
    setRefreshing(false)
  }

  const filteredTemplates = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    return templates.filter((t) => {
      if (activeCategory !== 'All' && t.category !== activeCategory) return false
      if (!q) return true
      return (
        (t.name || '').toLowerCase().includes(q) ||
        (t.description || '').toLowerCase().includes(q) ||
        (t.slug || '').toLowerCase().includes(q)
      )
    })
  }, [templates, activeCategory, searchTerm])

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Golden Paths"
        subtitle="Guided workflows to scaffold services, pipelines, and platform setup"
        actions={(
          <div className="flex items-center gap-2">
            {isAdmin && (
              <button
                type="button"
                onClick={() => setShowNewModal(true)}
                className="inline-flex items-center gap-2 px-4 py-2 bg-accent hover:bg-accent/90 rounded-lg text-sm font-semibold text-white"
              >
                <Plus size={16} /> New Template
              </button>
            )}
            <button
              type="button"
              onClick={() => void handleRefresh()}
              className="flex items-center gap-1.5 px-3 py-2 text-xs font-medium border border-border rounded-lg hover:bg-card transition-colors text-slate-400 hover:text-white"
            >
              <RefreshCw size={14} className={refreshing ? 'animate-spin' : ''} />
              Refresh
            </button>
          </div>
        )}
      />

      <div className="flex gap-1">
        {['templates', 'history'].map((tab) => (
          <button
            key={tab}
            type="button"
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
              activeTab === tab
                ? 'bg-accent text-white'
                : 'text-gray-400 hover:text-white hover:bg-white/5'
            }`}
          >
            {tab === 'templates'
              ? `Templates (${templates.length})`
              : `Run History (${runs.length})`}
          </button>
        ))}
      </div>

      {activeTab === 'templates' && (
        <div className="flex gap-2 flex-wrap">
          {CATEGORIES.map((cat) => (
            <button
              key={cat}
              type="button"
              onClick={() => setActiveCategory(cat)}
              className={`px-3 py-1 rounded-lg text-xs font-medium transition-colors ${
                activeCategory === cat
                  ? 'bg-accent text-white'
                  : 'text-gray-400 hover:text-white bg-card border border-border'
              }`}
            >
              {cat}
            </button>
          ))}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-2 text-sm text-red-300">
          {error}
        </div>
      )}

      {activeTab === 'templates' && loading && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="h-48 bg-card rounded-xl animate-pulse border border-border" />
          ))}
        </div>
      )}

      {activeTab === 'templates' && !loading && (
        <div className="flex flex-col gap-6">
          <input
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            placeholder="Search golden paths..."
            className="bg-card border border-border rounded-lg px-3 py-2 text-sm text-white placeholder-gray-500 w-64 focus:outline-none focus:border-accent/50"
          />
          {filteredTemplates.length === 0 ? (
            <EmptyState
              icon={Workflow}
              title="No golden path templates found"
              className="py-24"
            />
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {filteredTemplates.map((t) => (
                <TemplateCard key={t.id} template={t} onLaunch={() => setLaunchingTemplate(t)} />
              ))}
            </div>
          )}
        </div>
      )}

      {activeTab === 'history' && (
        <div>
          {runsLoading ? (
            <div className="flex justify-center py-16 text-gray-400 gap-2">
              <Loader2 className="w-6 h-6 animate-spin" /> Loading run history…
            </div>
          ) : runs.length === 0 ? (
            <EmptyState title="No runs yet." className="py-12" />
          ) : (
            <div className="bg-card border border-border rounded-xl overflow-hidden">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-border">
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase">
                      Template
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase">
                      Status
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase">
                      Requested By
                    </th>
                    <th className="text-left text-xs text-gray-500 font-medium px-4 py-3 uppercase">
                      Date
                    </th>
                    <th className="text-right text-xs text-gray-500 font-medium px-4 py-3 uppercase">
                      Logs
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {runs.map((run) => (
                    <tr key={run.id} className="border-b border-border hover:bg-white/[0.02]">
                      <td className="px-4 py-3 text-sm text-white">
                        {run.template_name || `Template #${run.template_id}`}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            STATUS_COLORS[run.status] || STATUS_COLORS.pending
                          }`}
                        >
                          {run.status}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-400">{run.requested_by}</td>
                      <td className="px-4 py-3 text-sm text-gray-400">
                        {run.created_at ? new Date(run.created_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 text-right">
                        <button
                          type="button"
                          onClick={() => setSelectedRun(run)}
                          className="inline-flex items-center gap-1 text-accent hover:text-accent/80 text-sm"
                        >
                          <Eye size={14} /> View Logs
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {launchingTemplate && (
        <LaunchWizardModal
          template={launchingTemplate}
          authFetch={authFetch}
          wizardRunStatus={wizardRunStatus}
          onRunComplete={(run) => {
            if (run?.id != null) setActiveRunId(run.id)
          }}
          onClose={() => {
            setLaunchingTemplate(null)
            setActiveRunId(null)
            setWizardRunStatus(null)
          }}
          onSuccess={() => {
            setLaunchingTemplate(null)
            setActiveRunId(null)
            setWizardRunStatus(null)
            void fetchRuns()
            showToastMsg('Golden path completed')
          }}
        />
      )}

      {selectedRun && <RunLogsModal run={selectedRun} onClose={() => setSelectedRun(null)} />}

      {showNewModal && (
        <NewTemplateModal
          authFetch={authFetch}
          onClose={() => setShowNewModal(false)}
          onCreated={() => {
            setShowNewModal(false)
            void fetchTemplates()
            showToastMsg('Template created')
          }}
        />
      )}

      {toast && (
        <div className="fixed bottom-6 right-6 z-[60] px-4 py-3 rounded-lg bg-emerald-600 text-white text-sm font-medium shadow-lg">
          {toast}
        </div>
      )}
    </div>
  )
}
