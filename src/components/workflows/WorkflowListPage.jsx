import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, Play, Plus, RefreshCw, Workflow } from 'lucide-react'
import { authFetch } from '../../utils/api'
import { useAuth } from '../../contexts/AuthContext'
import { PageHeader, EmptyState } from '../ui'

const EVENT_SOURCES = [
  'alert_rule_match',
  'webhook_inbound',
  'catalog_entity_changed',
  'agent_run_completed',
  'incident_created',
]

const DEFAULT_STEPS = [
  {
    id: 's1',
    type: 'agent',
    agent: 'incident_agent',
    input: { task: 'Handle {{trigger.title}}' },
    depends_on: [],
    requires_approval: false,
  },
]

function RiskBadge({ risk }) {
  const tone =
    risk === 'high'
      ? 'text-rose-300 border-rose-500/40 bg-rose-500/10'
      : risk === 'low'
        ? 'text-emerald-300 border-emerald-500/40 bg-emerald-500/10'
        : 'text-amber-300 border-amber-500/40 bg-amber-500/10'
  return (
    <span className={`inline-flex rounded border px-2 py-0.5 text-xs capitalize ${tone}`}>
      {risk || 'medium'}
    </span>
  )
}

function TriggeredByBadge({ value }) {
  const label = value || 'manual'
  const tone = String(label).startsWith('event:')
    ? 'bg-sky-500/15 text-sky-300'
    : label === 'schedule'
      ? 'bg-violet-500/15 text-violet-300'
      : 'bg-slate-700/60 text-slate-300'
  return (
    <span className={`inline-flex rounded px-2 py-0.5 text-xs ${tone}`}>{label}</span>
  )
}

function emptyForm() {
  return {
    name: '',
    description: '',
    steps: DEFAULT_STEPS,
    trigger_type: 'manual',
    trigger_config: {},
    enabled: true,
    risk: 'medium',
    max_runs_per_hour: 12,
    max_concurrent_runs: 1,
    on_concurrent_limit: 'drop',
  }
}

function TriggerConfigPanel({ form, setForm, preview, previewLoading }) {
  const cfg = form.trigger_config || {}
  const matchers = useMemo(() => {
    return Object.entries(cfg)
      .filter(([k]) => k !== 'source' && k !== 'cron' && k !== 'timezone')
      .map(([key, value]) => ({
        key,
        value: Array.isArray(value) ? value.join(',') : String(value ?? ''),
      }))
  }, [cfg])

  function setTriggerType(type) {
    setForm((prev) => ({
      ...prev,
      trigger_type: type,
      trigger_config:
        type === 'schedule'
          ? { cron: cfg.cron || '0 9 * * 1-5', timezone: cfg.timezone || 'UTC' }
          : type === 'event'
            ? { source: cfg.source || 'alert_rule_match', ...Object.fromEntries(Object.entries(cfg).filter(([k]) => k !== 'cron' && k !== 'timezone')) }
            : {},
    }))
  }

  function setCron(cron) {
    setForm((prev) => ({
      ...prev,
      trigger_config: { ...(prev.trigger_config || {}), cron, timezone: (prev.trigger_config || {}).timezone || 'UTC' },
    }))
  }

  function setEventSource(source) {
    setForm((prev) => ({
      ...prev,
      trigger_config: { ...(prev.trigger_config || {}), source },
    }))
  }

  function updateMatcher(idx, field, value) {
    const rows = [...matchers]
    rows[idx] = { ...rows[idx], [field]: value }
    const next = { source: cfg.source || 'alert_rule_match' }
    for (const row of rows) {
      if (!row.key.trim()) continue
      if (row.key.endsWith('_pattern') || !row.value.includes(',')) {
        next[row.key.trim()] = row.value
      } else {
        next[row.key.trim()] = row.value.split(',').map((s) => s.trim()).filter(Boolean)
      }
    }
    setForm((prev) => ({ ...prev, trigger_config: next }))
  }

  function addMatcher() {
    const next = { ...cfg, source: cfg.source || 'alert_rule_match', severity: cfg.severity || ['high', 'critical'] }
    if (!('severity' in cfg)) {
      setForm((prev) => ({ ...prev, trigger_config: next }))
      return
    }
    setForm((prev) => ({
      ...prev,
      trigger_config: { ...cfg, [`field_${matchers.length + 1}`]: '' },
    }))
  }

  return (
    <div className="space-y-3 rounded-xl border border-slate-800 bg-slate-900/40 p-4">
      <div className="text-sm font-medium text-white">Trigger</div>
      <div className="flex flex-wrap gap-3 text-sm text-slate-300">
        {['manual', 'schedule', 'event'].map((t) => (
          <label key={t} className="inline-flex items-center gap-2 capitalize">
            <input
              type="radio"
              name="trigger_type"
              checked={form.trigger_type === t}
              onChange={() => setTriggerType(t)}
            />
            {t}
          </label>
        ))}
      </div>

      {form.trigger_type === 'schedule' ? (
        <div className="space-y-2">
          <label className="block text-xs text-slate-400">
            Cron expression
            <input
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 font-mono text-sm text-slate-100"
              value={cfg.cron || ''}
              onChange={(e) => setCron(e.target.value)}
              placeholder="0 9 * * 1-5"
            />
          </label>
          <p className="text-xs text-slate-400">
            {preview?.human || 'Enter a cron expression for a live preview.'}
          </p>
          {previewLoading ? (
            <p className="text-xs text-slate-500">Loading next fire times…</p>
          ) : (
            <ul className="list-disc space-y-1 pl-5 text-xs text-slate-400">
              {(preview?.next_fire_times || []).map((t) => (
                <li key={t}>{new Date(t).toLocaleString()}</li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      {form.trigger_type === 'event' ? (
        <div className="space-y-2">
          <label className="block text-xs text-slate-400">
            Event source
            <select
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-slate-100"
              value={cfg.source || 'alert_rule_match'}
              onChange={(e) => setEventSource(e.target.value)}
            >
              {EVENT_SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="space-y-2">
            <div className="text-xs text-slate-400">Matchers (key / value — comma lists or *_pattern regex)</div>
            {matchers.map((row, idx) => (
              <div key={idx} className="flex gap-2">
                <input
                  className="w-1/3 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100"
                  value={row.key}
                  onChange={(e) => updateMatcher(idx, 'key', e.target.value)}
                  placeholder="severity"
                />
                <input
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-950 px-2 py-1.5 text-xs text-slate-100"
                  value={row.value}
                  onChange={(e) => updateMatcher(idx, 'value', e.target.value)}
                  placeholder="high,critical or payments.*"
                />
              </div>
            ))}
            <button
              type="button"
              onClick={addMatcher}
              className="text-xs text-indigo-300 hover:text-indigo-200"
            >
              + Add matcher
            </button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

export default function WorkflowListPage() {
  const navigate = useNavigate()
  const { role } = useAuth()
  const isAdmin = role === 'Admin'
  const [rows, setRows] = useState([])
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busyId, setBusyId] = useState('')
  const [editing, setEditing] = useState(null)
  const [form, setForm] = useState(emptyForm)
  const [preview, setPreview] = useState(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const [wfRes, runRes] = await Promise.all([
        authFetch('/api/workflows'),
        authFetch('/api/workflows/runs'),
      ])
      if (!wfRes.ok) throw new Error(`Failed to load workflows (${wfRes.status})`)
      const data = await wfRes.json()
      setRows(Array.isArray(data) ? data : [])
      if (runRes.ok) {
        const runData = await runRes.json()
        setRuns(Array.isArray(runData) ? runData : [])
      }
    } catch (err) {
      setError(err?.message || 'Failed to load')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    void load()
  }, [load])

    useEffect(() => {
    if (form.trigger_type !== 'schedule') {
      setPreview(null)
      return
    }
    const cron = (form.trigger_config || {}).cron || ''
    const tz = (form.trigger_config || {}).timezone || 'UTC'
    if (!cron.trim()) {
      setPreview(null)
      return
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
  }, [form.trigger_type, form.trigger_config])

  async function toggleEnabled(row) {
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: row.name,
          description: row.description || '',
          steps: row.steps || [],
          trigger_type: row.trigger_type || 'manual',
          trigger_config: row.trigger_config || {},
          enabled: !row.enabled,
          risk: row.risk || 'medium',
          max_runs_per_hour: row.max_runs_per_hour ?? 12,
          max_concurrent_runs: row.max_concurrent_runs ?? 1,
          on_concurrent_limit: row.on_concurrent_limit || 'drop',
          workspace_id: row.workspace_id || null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Update failed (${res.status})`)
      }
      await load()
    } catch (err) {
      setError(err?.message || 'Update failed')
    } finally {
      setBusyId('')
    }
  }

  async function runWorkflow(row, dryRun = false) {
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}/run`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ dry_run: dryRun, context: {} }),
      })
      const body = await res.json().catch(() => ({}))
      if (!res.ok) {
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Run failed (${res.status})`)
      }
      navigate(`/workflows/runs/${encodeURIComponent(body.id)}`)
    } catch (err) {
      setError(err?.message || 'Run failed')
    } finally {
      setBusyId('')
    }
  }

  async function approveLive(row) {
    if (!isAdmin) return
    setBusyId(row.id)
    try {
      const res = await authFetch(`/api/workflows/${encodeURIComponent(row.id)}/approve-live`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error(`Approve failed (${res.status})`)
      await load()
    } catch (err) {
      setError(err?.message || 'Approve failed')
    } finally {
      setBusyId('')
    }
  }

  function openCreate() {
    setEditing({})
    setForm(emptyForm())
  }

  function openEdit(row) {
    setEditing(row)
    setForm({
      name: row.name || '',
      description: row.description || '',
      steps: row.steps || DEFAULT_STEPS,
      trigger_type: row.trigger_type || 'manual',
      trigger_config: row.trigger_config || {},
      enabled: !!row.enabled,
      risk: row.risk || 'medium',
      max_runs_per_hour: row.max_runs_per_hour ?? 12,
      max_concurrent_runs: row.max_concurrent_runs ?? 1,
      on_concurrent_limit: row.on_concurrent_limit || 'drop',
    })
  }

  async function saveForm() {
    if (!isAdmin) return
    setSaving(true)
    setError('')
    try {
      const payload = {
        ...form,
        name: (form.name || '').trim(),
        steps: form.steps || DEFAULT_STEPS,
      }
      const isUpdate = Boolean(editing?.id)
      const res = await authFetch(
        isUpdate ? `/api/workflows/${encodeURIComponent(editing.id)}` : '/api/workflows',
        {
          method: isUpdate ? 'PUT' : 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        },
      )
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail ? JSON.stringify(body.detail) : `Save failed (${res.status})`)
      }
      setEditing(null)
      await load()
    } catch (err) {
      setError(err?.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Workflows"
        subtitle="Chain agents with schedule and event triggers, plus human approval gates."
        actions={
          <div className="flex items-center gap-2">
            {isAdmin ? (
              <button
                type="button"
                onClick={openCreate}
                className="inline-flex items-center gap-2 rounded-lg bg-indigo-600 px-3 py-2 text-sm text-white hover:bg-indigo-500"
              >
                <Plus size={14} /> New workflow
              </button>
            ) : null}
            <button
              type="button"
              onClick={() => void load()}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-700 px-3 py-2 text-sm text-slate-200 hover:bg-slate-800"
            >
              <RefreshCw size={14} /> Refresh
            </button>
          </div>
        }
      />

      {error ? (
        <div className="rounded-lg border border-rose-500/40 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">
          {error}
        </div>
      ) : null}

      {editing !== null ? (
        <div className="space-y-4 rounded-xl border border-slate-800 bg-slate-950/60 p-4">
          <div className="text-sm font-medium text-white">
            {editing?.id ? 'Edit workflow' : 'Create workflow'}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
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
          </div>
          <label className="block text-xs text-slate-400">
            Description
            <textarea
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white"
              rows={2}
              value={form.description}
              onChange={(e) => setForm((p) => ({ ...p, description: e.target.value }))}
            />
          </label>
          <TriggerConfigPanel
            form={form}
            setForm={setForm}
            preview={preview}
            previewLoading={previewLoading}
          />
          <div className="flex gap-2">
            <button
              type="button"
              disabled={saving || !form.name.trim()}
              onClick={() => void saveForm()}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm text-white hover:bg-indigo-500 disabled:opacity-40"
            >
              {saving ? 'Saving…' : 'Save'}
            </button>
            <button
              type="button"
              onClick={() => setEditing(null)}
              className="rounded-lg border border-slate-700 px-4 py-2 text-sm text-slate-300"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : null}

      {loading ? (
        <div className="flex items-center gap-2 text-slate-400">
          <Loader2 className="animate-spin" size={18} /> Loading workflows…
        </div>
      ) : !rows.length ? (
        <EmptyState
          icon={Workflow}
          title="No workflows yet"
          hint="Create a workflow to chain agents with schedule or event triggers."
        />
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Name</th>
                <th className="px-4 py-3 font-medium">Trigger</th>
                <th className="px-4 py-3 font-medium">Next run</th>
                <th className="px-4 py-3 font-medium">Risk</th>
                <th className="px-4 py-3 font-medium">Enabled</th>
                <th className="px-4 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row) => (
                <tr key={row.id} className="border-t border-slate-800/80 text-slate-200">
                  <td className="px-4 py-3">
                    <div className="font-medium text-white">{row.name}</div>
                    <div className="text-xs text-slate-500">{row.description || '—'}</div>
                    {!row.first_live_run_approved_at ? (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <span className="rounded border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-200">
                          Dry-run only — approve live runs to enable
                        </span>
                        {isAdmin ? (
                          <button
                            type="button"
                            disabled={busyId === row.id}
                            onClick={() => void approveLive(row)}
                            className="rounded border border-amber-500/50 px-2 py-0.5 text-xs text-amber-100 hover:bg-amber-500/20"
                          >
                            Approve live runs
                          </button>
                        ) : null}
                      </div>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 capitalize">{row.trigger_type || 'manual'}</td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {row.trigger_type === 'schedule' && row.next_run
                      ? new Date(row.next_run).toLocaleString()
                      : '—'}
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge risk={row.risk} />
                  </td>
                  <td className="px-4 py-3">
                    <button
                      type="button"
                      disabled={busyId === row.id || !isAdmin}
                      onClick={() => void toggleEnabled(row)}
                      className={`rounded-full px-3 py-1 text-xs ${
                        row.enabled
                          ? 'bg-emerald-500/15 text-emerald-300'
                          : 'bg-slate-700/60 text-slate-400'
                      }`}
                    >
                      {row.enabled ? 'On' : 'Off'}
                    </button>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        disabled={busyId === row.id || !row.enabled}
                        onClick={() => void runWorkflow(row, false)}
                        className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-500 disabled:opacity-40"
                      >
                        <Play size={12} /> Run
                      </button>
                      {isAdmin ? (
                        <button
                          type="button"
                          onClick={() => openEdit(row)}
                          className="text-xs text-slate-400 hover:text-slate-200"
                        >
                          Edit
                        </button>
                      ) : null}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="space-y-3">
        <h3 className="text-sm font-medium text-white">Recent runs</h3>
        <div className="overflow-hidden rounded-xl border border-slate-800">
          <table className="min-w-full text-left text-sm">
            <thead className="bg-slate-900/80 text-slate-400">
              <tr>
                <th className="px-4 py-3 font-medium">Run</th>
                <th className="px-4 py-3 font-medium">Status</th>
                <th className="px-4 py-3 font-medium">Triggered by</th>
                <th className="px-4 py-3 font-medium">Started</th>
              </tr>
            </thead>
            <tbody>
              {runs.slice(0, 20).map((run) => (
                <tr key={run.id} className="border-t border-slate-800/80 text-slate-200">
                  <td className="px-4 py-3">
                    <Link
                      to={`/workflows/runs/${encodeURIComponent(run.id)}`}
                      className="text-indigo-300 hover:text-indigo-200"
                    >
                      {run.id.slice(0, 8)}…
                    </Link>
                  </td>
                  <td className="px-4 py-3 capitalize">{run.status}</td>
                  <td className="px-4 py-3">
                    <TriggeredByBadge value={run.triggered_by} />
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-400">
                    {run.started_at ? new Date(run.started_at).toLocaleString() : '—'}
                  </td>
                </tr>
              ))}
              {!runs.length ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                    No runs yet
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
