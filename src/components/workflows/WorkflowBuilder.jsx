import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import {
  AlertTriangle, ArrowDown, ArrowUp, Loader2, Plus, Save, ShieldCheck, Trash2, Play,
} from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { PageHeader } from '../ui'
import TriggerConfigPanel from './TriggerConfigPanel'

const STEP_TYPES = [
  { value: 'agent', label: 'Agent' },
  { value: 'connector', label: 'Connector action' },
  { value: 'hitl', label: 'HITL gate' },
  { value: 'condition', label: 'Condition' },
]

function shortId(existing) {
  let n = existing.length + 1
  while (existing.includes(`s${n}`)) n += 1
  return `s${n}`
}

function newStep(type, existingIds) {
  const id = shortId(existingIds)
  const base = { id, type, depends_on: existingIds.length ? [existingIds[existingIds.length - 1]] : [] }
  if (type === 'agent') return { ...base, agent: '', inputText: '{}' }
  if (type === 'connector') return { ...base, connector: '', method: '', argsText: '{}' }
  if (type === 'hitl') return { ...base, prompt: '' }
  return { ...base, expression: '' }
}

function toUiStep(raw) {
  const type = raw.type || 'agent'
  const base = { id: raw.id, type, depends_on: raw.depends_on || [] }
  if (type === 'agent') return { ...base, agent: raw.agent || '', inputText: JSON.stringify(raw.input || {}, null, 2) }
  if (type === 'connector') {
    return {
      ...base,
      connector: raw.connector || '',
      method: raw.method || '',
      argsText: JSON.stringify(raw.args || {}, null, 2),
    }
  }
  if (type === 'hitl') return { ...base, prompt: raw.prompt || '' }
  return { ...base, expression: raw.expression || raw.when || '' }
}

function toBackendStep(ui) {
  const base = { id: ui.id, type: ui.type, depends_on: ui.depends_on || [] }
  if (ui.type === 'agent') {
    let input = {}
    try {
      input = JSON.parse(ui.inputText || '{}')
    } catch {
      throw new Error(`step ${ui.id}: input is not valid JSON`)
    }
    return { ...base, agent: ui.agent, input }
  }
  if (ui.type === 'connector') {
    let args = {}
    try {
      args = JSON.parse(ui.argsText || '{}')
    } catch {
      throw new Error(`step ${ui.id}: args is not valid JSON`)
    }
    return { ...base, connector: ui.connector, method: ui.method, args }
  }
  if (ui.type === 'hitl') return { ...base, prompt: ui.prompt }
  return { ...base, expression: ui.expression }
}

function emptyForm() {
  return {
    name: '',
    description: '',
    trigger_type: 'manual',
    trigger_config: {},
    enabled: true,
    risk: 'medium',
    max_runs_per_hour: 12,
    max_concurrent_runs: 1,
    on_concurrent_limit: 'drop',
  }
}

// Parses validate_workflow_steps' "step {sid}: message" convention so errors
// can be shown inline against the specific step rather than one banner.
function groupStepErrors(errors) {
  const bySid = {}
  const general = []
  for (const msg of errors || []) {
    const m = /^step ([^:]+):/.exec(msg)
    if (m) {
      const sid = m[1].trim()
      if (!bySid[sid]) bySid[sid] = []
      bySid[sid].push(msg)
    } else {
      general.push(msg)
    }
  }
  return { bySid, general }
}

export default function WorkflowBuilder() {
  const { workflowId } = useParams()
  const navigate = useNavigate()
  const { authFetch, role } = useAuth()
  const isAdmin = role === 'Admin'
  const isNew = !workflowId || workflowId === 'new'

  const [form, setForm] = useState(emptyForm)
  const [steps, setSteps] = useState(() => [newStep('agent', [])])
  const [agents, setAgents] = useState([])
  const [connectors, setConnectors] = useState([])
  const [loading, setLoading] = useState(!isNew)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [stepErrors, setStepErrors] = useState({})
  const [generalErrors, setGeneralErrors] = useState([])
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [savedId, setSavedId] = useState(isNew ? null : workflowId)
  const [firstLiveRunApprovedAt, setFirstLiveRunApprovedAt] = useState(null)
  const [dryRunning, setDryRunning] = useState(false)

  const activeFieldRef = useRef({ stepId: null, field: null, start: 0, end: 0 })

  useEffect(() => {
    authFetch('/api/agents/')
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setAgents(Array.isArray(data) ? data : []))
      .catch(() => setAgents([]))
    authFetch('/api/connectors')
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => setConnectors(Array.isArray(data) ? data : []))
      .catch(() => setConnectors([]))
  }, [authFetch])

  useEffect(() => {
    if (isNew) return
    let cancelled = false
    setLoading(true)
    authFetch(`/api/workflows/${encodeURIComponent(workflowId)}`)
      .then((r) => {
        if (!r.ok) throw new Error(`Failed to load workflow (${r.status})`)
        return r.json()
      })
      .then((row) => {
        if (cancelled) return
        setForm({
          name: row.name || '',
          description: row.description || '',
          trigger_type: row.trigger_type || 'manual',
          trigger_config: row.trigger_config || {},
          enabled: !!row.enabled,
          risk: row.risk || 'medium',
          max_runs_per_hour: row.max_runs_per_hour ?? 12,
          max_concurrent_runs: row.max_concurrent_runs ?? 1,
          on_concurrent_limit: row.on_concurrent_limit || 'drop',
        })
        setSteps((row.steps || []).map(toUiStep))
        setFirstLiveRunApprovedAt(row.first_live_run_approved_at || null)
        setSavedId(row.id)
      })
      .catch((err) => setError(err.message || 'Failed to load workflow'))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [authFetch, isNew, workflowId])

  useEffect(() => {
    if (form.trigger_type !== 'schedule') {
      setPreview(null)
      return undefined
    }
    const cron = (form.trigger_config || {}).cron || ''
    const tz = (form.trigger_config || {}).timezone || 'UTC'
    if (!cron.trim()) {
      setPreview(null)
      return undefined
    }
    let cancelled = false
    const timer = setTimeout(async () => {
      setPreviewLoading(true)
      try {
        const qs = new URLSearchParams({ cron, timezone: tz })
        const res = await authFetch(`/api/workflows/triggers/preview?${qs}`)
        if (res.ok && !cancelled) setPreview(await res.json())
      } finally {
        if (!cancelled) setPreviewLoading(false)
      }
    }, 300)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [authFetch, form.trigger_type, form.trigger_config])

  const stepIds = useMemo(() => steps.map((s) => s.id), [steps])

  function updateStep(idx, patch) {
    setSteps((prev) => prev.map((s, i) => (i === idx ? { ...s, ...patch } : s)))
  }

  function addStep(type) {
    setSteps((prev) => [...prev, newStep(type, prev.map((s) => s.id))])
  }

  function removeStep(idx) {
    setSteps((prev) => prev.filter((_, i) => i !== idx))
  }

  function moveStep(idx, dir) {
    setSteps((prev) => {
      const next = [...prev]
      const target = idx + dir
      if (target < 0 || target >= next.length) return prev
      ;[next[idx], next[target]] = [next[target], next[idx]]
      return next
    })
  }

  function trackCursor(stepId, field) {
    return (e) => {
      activeFieldRef.current = {
        stepId,
        field,
        start: e.target.selectionStart ?? 0,
        end: e.target.selectionEnd ?? 0,
      }
    }
  }

  function insertToken(token, { quoted = false } = {}) {
    const active = activeFieldRef.current
    if (!active.stepId) return
    const idx = steps.findIndex((s) => s.id === active.stepId)
    if (idx === -1) return
    const step = steps[idx]
    const current = step[active.field] || ''
    const text = quoted ? `"${token}"` : token
    const next = current.slice(0, active.start) + text + current.slice(active.end)
    updateStep(idx, { [active.field]: next })
  }

  function variablePicker(stepIdx) {
    const priorIds = stepIds.slice(0, stepIdx)
    if (!priorIds.length) return null
    const step = steps[stepIdx]
    const quoted = step.type === 'agent' || step.type === 'connector'
    return (
      <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
        <span className="text-slate-500">Insert:</span>
        <button
          type="button"
          className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-slate-300 hover:border-indigo-500"
          onClick={() => insertToken('{{trigger}}', { quoted })}
        >
          trigger
        </button>
        {priorIds.map((sid) => (
          <span key={sid} className="flex items-center gap-1">
            {['output', 'output.summary', 'status'].map((suffix) => (
              <button
                key={suffix}
                type="button"
                className="rounded border border-slate-700 bg-slate-900 px-1.5 py-0.5 text-slate-300 hover:border-indigo-500"
                onClick={() => insertToken(`{{steps.${sid}.${suffix}}}`, { quoted })}
              >
                {sid}.{suffix}
              </button>
            ))}
          </span>
        ))}
      </div>
    )
  }

  const buildBackendSteps = useCallback(() => steps.map(toBackendStep), [steps])

  async function runValidate() {
    setError('')
    let backendSteps
    try {
      backendSteps = buildBackendSteps()
    } catch (err) {
      setGeneralErrors([err.message])
      setStepErrors({})
      return null
    }
    try {
      const res = await authFetch('/api/workflows/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ steps: backendSteps }),
      })
      if (res.ok) {
        setStepErrors({})
        setGeneralErrors([])
        return backendSteps
      }
      const body = await res.json().catch(() => ({}))
      const errors = Array.isArray(body.detail) ? body.detail : [String(body.detail || 'Validation failed')]
      const { bySid, general } = groupStepErrors(errors)
      setStepErrors(bySid)
      setGeneralErrors(general)
      return null
    } catch (err) {
      setGeneralErrors([err.message || 'Validation request failed'])
      return null
    }
  }

  async function save() {
    if (!isAdmin) return
    setSaving(true)
    setError('')
    const backendSteps = await runValidate()
    if (!backendSteps) {
      setSaving(false)
      return
    }
    try {
      const payload = { ...form, name: form.name.trim(), steps: backendSteps }
      const isUpdate = !isNew && savedId
      const res = await authFetch(isUpdate ? `/api/workflows/${encodeURIComponent(savedId)}` : '/api/workflows', {
        method: isUpdate ? 'PUT' : 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Save failed (${res.status})`)
      }
      const row = await res.json()
      setSavedId(row.id)
      setFirstLiveRunApprovedAt(row.first_live_run_approved_at || null)
      if (isNew) navigate(`/workflows/builder/${encodeURIComponent(row.id)}`, { replace: true })
    } catch (err) {
      setError(err.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  async function dryRun() {
    if (!savedId) return
    setDryRunning(true)
    setError('')
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(savedId)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: true, context: {} }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(body.detail ? JSON.stringify(body.detail) : `Dry-run failed (${res.status})`)
      navigate(`/workflows/runs/${encodeURIComponent(body.id)}`)
    } catch (err) {
      setError(err.message || 'Dry-run failed')
    } finally {
      setDryRunning(false)
    }
  }

  async function approveLive() {
    if (!isAdmin || !savedId) return
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(savedId)}/approve-live`, { method: 'POST' })
      if (!res.ok) throw new Error(`Approve failed (${res.status})`)
      const row = await res.json()
      setFirstLiveRunApprovedAt(row.first_live_run_approved_at || null)
    } catch (err) {
      setError(err.message || 'Approve failed')
    }
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 p-6 text-slate-400">
        <Loader2 className="animate-spin" size={18} /> Loading workflow…
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-6 p-6">
      <PageHeader
        title={isNew ? 'New workflow' : `Edit: ${form.name || savedId}`}
        subtitle="Vertical step list — add, remove, and reorder. No canvas required."
        actions={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => navigate('/workflows')}
              className="rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800"
            >
              Back to list
            </button>
          </div>
        }
      />

      {!firstLiveRunApprovedAt && savedId && (
        <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-4 py-3 text-sm text-amber-200">
          <span className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" /> This workflow has not had a live run approved — runs execute in dry-run only.
          </span>
          {isAdmin && (
            <button
              type="button"
              onClick={() => void approveLive()}
              className="flex items-center gap-1 rounded border border-amber-500/50 px-2 py-1 text-xs text-amber-100 hover:bg-amber-500/20"
            >
              <ShieldCheck className="h-3.5 w-3.5" /> Approve for live runs
            </button>
          )}
        </div>
      )}

      {error && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      )}
      {generalErrors.length > 0 && (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          <ul className="list-disc pl-5">
            {generalErrors.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="grid gap-3 rounded-xl border border-slate-800 bg-slate-950/60 p-4 md:grid-cols-2">
        <label className="block text-xs text-slate-400">
          Name
          <input
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={form.name}
            onChange={(e) => setForm((p) => ({ ...p, name: e.target.value }))}
          />
        </label>
        <label className="block text-xs text-slate-400">
          Risk
          <select
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            value={form.risk}
            onChange={(e) => setForm((p) => ({ ...p, risk: e.target.value }))}
          >
            <option value="low">low</option>
            <option value="medium">medium</option>
            <option value="high">high</option>
          </select>
        </label>
        <label className="block text-xs text-slate-400 md:col-span-2">
          Description
          <textarea
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
            rows={2}
            value={form.description}
            onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
          />
        </label>
      </div>

      <TriggerConfigPanel form={form} setForm={setForm} preview={preview} previewLoading={previewLoading} />

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium text-white">Steps</h3>
          <div className="flex gap-1.5">
            {STEP_TYPES.map((t) => (
              <button
                key={t.value}
                type="button"
                onClick={() => addStep(t.value)}
                className="flex items-center gap-1 rounded-lg border border-slate-700 px-2 py-1 text-xs text-slate-300 hover:bg-slate-800"
              >
                <Plus className="h-3 w-3" /> {t.label}
              </button>
            ))}
          </div>
        </div>

        {steps.map((step, idx) => {
          const errs = stepErrors[step.id] || []
          return (
            <div
              key={step.id}
              className={`space-y-2 rounded-xl border p-3 ${errs.length ? 'border-rose-500/50 bg-rose-500/5' : 'border-slate-800 bg-slate-900/40'}`}
            >
              <div className="flex flex-wrap items-center gap-2">
                <input
                  className="w-24 rounded border border-slate-700 bg-slate-950 px-2 py-1 font-mono text-xs text-slate-200"
                  value={step.id}
                  onChange={(e) => updateStep(idx, { id: e.target.value.trim() })}
                />
                <select
                  className="rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                  value={step.type}
                  onChange={(e) => setSteps((prev) => prev.map((s, i) => (i === idx ? newStep(e.target.value, stepIds.filter((id) => id !== s.id)) : s)))}
                >
                  {STEP_TYPES.map((t) => (
                    <option key={t.value} value={t.value}>{t.label}</option>
                  ))}
                </select>
                <label className="flex items-center gap-1 text-xs text-slate-400">
                  depends on
                  <select
                    multiple
                    className="h-8 min-w-[8rem] rounded border border-slate-700 bg-slate-950 px-2 py-1 text-xs text-slate-200"
                    value={step.depends_on}
                    onChange={(e) =>
                      updateStep(idx, {
                        depends_on: Array.from(e.target.selectedOptions).map((o) => o.value),
                      })
                    }
                  >
                    {stepIds.filter((id) => id !== step.id).map((id) => (
                      <option key={id} value={id}>{id}</option>
                    ))}
                  </select>
                </label>
                <div className="ml-auto flex items-center gap-1">
                  <button type="button" disabled={idx === 0} onClick={() => moveStep(idx, -1)} className="rounded border border-slate-700 p-1 text-slate-300 disabled:opacity-30">
                    <ArrowUp className="h-3 w-3" />
                  </button>
                  <button type="button" disabled={idx === steps.length - 1} onClick={() => moveStep(idx, 1)} className="rounded border border-slate-700 p-1 text-slate-300 disabled:opacity-30">
                    <ArrowDown className="h-3 w-3" />
                  </button>
                  <button type="button" onClick={() => removeStep(idx)} className="rounded border border-rose-700/50 p-1 text-rose-300 hover:bg-rose-500/10">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </div>
              </div>

              {step.type === 'agent' && (
                <>
                  <select
                    className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
                    value={step.agent}
                    onChange={(e) => updateStep(idx, { agent: e.target.value })}
                  >
                    <option value="">Select agent…</option>
                    {agents.map((a) => (
                      <option key={a.name} value={a.name}>{a.name}</option>
                    ))}
                  </select>
                  <textarea
                    className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-200"
                    rows={3}
                    value={step.inputText}
                    onFocus={trackCursor(step.id, 'inputText')}
                    onSelect={trackCursor(step.id, 'inputText')}
                    onChange={(e) => updateStep(idx, { inputText: e.target.value })}
                  />
                </>
              )}

              {step.type === 'connector' && (
                <>
                  <div className="flex gap-2">
                    <select
                      className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
                      value={step.connector}
                      onChange={(e) => updateStep(idx, { connector: e.target.value })}
                    >
                      <option value="">Select connector…</option>
                      {connectors.map((c) => (
                        <option key={c.id} value={c.id}>{c.id}</option>
                      ))}
                    </select>
                    <input
                      className="flex-1 rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
                      placeholder="method (e.g. deploy)"
                      value={step.method}
                      onChange={(e) => updateStep(idx, { method: e.target.value })}
                    />
                  </div>
                  <textarea
                    className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-200"
                    rows={3}
                    value={step.argsText}
                    onFocus={trackCursor(step.id, 'argsText')}
                    onSelect={trackCursor(step.id, 'argsText')}
                    onChange={(e) => updateStep(idx, { argsText: e.target.value })}
                  />
                </>
              )}

              {step.type === 'hitl' && (
                <textarea
                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-200"
                  rows={2}
                  placeholder="Approve this step?"
                  value={step.prompt}
                  onFocus={trackCursor(step.id, 'prompt')}
                  onSelect={trackCursor(step.id, 'prompt')}
                  onChange={(e) => updateStep(idx, { prompt: e.target.value })}
                />
              )}

              {step.type === 'condition' && (
                <input
                  className="w-full rounded border border-slate-700 bg-slate-950 px-2 py-1.5 font-mono text-xs text-slate-200"
                  placeholder="steps.s1.output.status == 'ok'"
                  value={step.expression}
                  onFocus={trackCursor(step.id, 'expression')}
                  onSelect={trackCursor(step.id, 'expression')}
                  onChange={(e) => updateStep(idx, { expression: e.target.value })}
                />
              )}

              {variablePicker(idx)}

              {errs.length > 0 && (
                <ul className="list-disc pl-5 text-xs text-rose-300">
                  {errs.map((e) => <li key={e}>{e}</li>)}
                </ul>
              )}
            </div>
          )
        })}
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          type="button"
          onClick={() => void runValidate()}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
        >
          <ShieldCheck className="h-4 w-4" /> Validate
        </button>
        {isAdmin && (
          <button
            type="button"
            disabled={saving || !form.name.trim()}
            onClick={() => void save()}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-40"
          >
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
            Save
          </button>
        )}
        <button
          type="button"
          disabled={!savedId || dryRunning}
          title={savedId ? '' : 'Save the workflow first to enable dry-run'}
          onClick={() => void dryRun()}
          className="flex items-center gap-1.5 rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800 disabled:opacity-40"
        >
          {dryRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
          Dry-run
        </button>
      </div>
    </div>
  )
}
