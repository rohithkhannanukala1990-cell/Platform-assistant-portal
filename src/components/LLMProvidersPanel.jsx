import { useCallback, useEffect, useState } from 'react'
import { Plus, Trash2, Play, Save, AlertCircle, CheckCircle2, Cpu } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const EMPTY_FORM = {
  provider: 'openai',
  model_name: 'gpt-4o-mini',
  base_url: 'https://api.openai.com/v1',
  api_key: '',
  fallback_provider: 'openai',
  fallback_model: 'gpt-4o-mini',
  monthly_token_budget: 1000000,
  is_active: true,
  priority: 100,
}

export default function LLMProvidersPanel() {
  const { authFetch, role } = useAuth()
  const isAdmin = role === 'Admin'
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/llm/providers')
      if (!res.ok) throw new Error('Failed to load providers')
      setRows(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load providers')
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function startEdit(row) {
    setEditingId(row.id)
    setForm({
      provider: row.provider || 'openai',
      model_name: row.model_name || 'gpt-4o-mini',
      base_url: row.base_url || '',
      api_key: '',
      fallback_provider: row.fallback_provider || 'openai',
      fallback_model: row.fallback_model || 'gpt-4o-mini',
      monthly_token_budget: row.monthly_token_budget ?? 1000000,
      is_active: !!row.is_active,
      priority: row.priority ?? 100,
    })
    setMessage(null)
    setError(null)
  }

  function resetForm() {
    setEditingId(null)
    setForm(EMPTY_FORM)
  }

  async function handleSave() {
    if (!isAdmin) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const payload = {
        provider: form.provider,
        model_name: form.model_name,
        base_url: form.base_url || null,
        fallback_provider: form.fallback_provider,
        fallback_model: form.fallback_model,
        monthly_token_budget: Number(form.monthly_token_budget) || 1000000,
        is_active: !!form.is_active,
        priority: Number(form.priority) || 0,
      }
      if (form.api_key.trim()) payload.api_key = form.api_key.trim()

      const res = editingId
        ? await authFetch(`/api/llm/providers/${editingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
        : await authFetch('/api/llm/providers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t || 'Save failed')
      }
      setMessage(editingId ? 'Provider updated' : 'Provider created')
      resetForm()
      await load()
    } catch (e) {
      setError(e.message || 'Save failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleDelete(id) {
    if (!isAdmin) return
    if (!window.confirm('Delete this LLM provider?')) return
    setBusy(true)
    setError(null)
    try {
      const res = await authFetch(`/api/llm/providers/${id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error('Delete failed')
      if (editingId === id) resetForm()
      await load()
    } catch (e) {
      setError(e.message || 'Delete failed')
    } finally {
      setBusy(false)
    }
  }

  async function handleTest(id) {
    if (!isAdmin) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const res = await authFetch('/api/llm/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ provider_id: id, prompt: 'Reply with exactly: pong' }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Test failed')
      setMessage(`Test ok: ${(data.response || '').slice(0, 120)}`)
    } catch (e) {
      setError(e.message || 'Test failed')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2 pb-2 border-b border-border">
        <Cpu className="w-3.5 h-3.5 text-emerald-400" />
        <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider">LLM providers</h3>
      </div>

      {!isAdmin && (
        <p className="text-[11px] text-slate-500">View only — Admin role required to change providers.</p>
      )}

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}
      {message && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          {message}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {rows.length === 0 && (
          <p className="text-[11px] text-slate-600">No providers configured yet.</p>
        )}
        {rows.map((row) => (
          <div
            key={row.id}
            className="flex flex-col gap-2 rounded-lg border border-border bg-card/40 px-3 py-2.5"
          >
            <div className="flex items-start justify-between gap-2">
              <div>
                <p className="text-xs font-semibold text-slate-200">
                  {row.model_name}{' '}
                  <span className="text-slate-500 font-normal">({row.provider})</span>
                </p>
                <p className="text-[11px] text-slate-500 mt-0.5">
                  priority {row.priority}
                  {row.is_active ? ' · active' : ' · inactive'}
                  {row.has_api_key ? ' · key set' : ' · no key'}
                </p>
              </div>
              {isAdmin && (
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => startEdit(row)}
                    className="px-2 py-1 text-[11px] rounded bg-slate-800 text-slate-300 hover:bg-slate-700"
                  >
                    Edit
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleTest(row.id)}
                    className="p-1.5 rounded bg-slate-800 text-emerald-400 hover:bg-slate-700"
                    title="Test"
                  >
                    <Play className="w-3 h-3" />
                  </button>
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => handleDelete(row.id)}
                    className="p-1.5 rounded bg-slate-800 text-rose-400 hover:bg-slate-700"
                    title="Delete"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              )}
            </div>
          </div>
        ))}
      </div>

      {isAdmin && (
        <div className="flex flex-col gap-2.5 rounded-lg border border-border bg-sidebar/40 p-3">
          <p className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider">
            {editingId ? `Edit provider #${editingId}` : 'Add provider'}
          </p>
          <div className="grid grid-cols-2 gap-2">
            <select
              value={form.provider}
              onChange={(e) => setField('provider', e.target.value)}
              className="bg-card border border-border rounded-lg px-2 py-2 text-xs text-slate-300"
            >
              <option value="openai">openai</option>
              <option value="openai_compatible">openai_compatible</option>
              <option value="anthropic">anthropic</option>
            </select>
            <input
              value={form.model_name}
              onChange={(e) => setField('model_name', e.target.value)}
              placeholder="model"
              className="bg-card border border-border rounded-lg px-2 py-2 text-xs text-slate-300"
            />
            <input
              value={form.base_url}
              onChange={(e) => setField('base_url', e.target.value)}
              placeholder="base_url"
              className="col-span-2 bg-card border border-border rounded-lg px-2 py-2 text-xs text-slate-300"
            />
            <input
              type="password"
              value={form.api_key}
              onChange={(e) => setField('api_key', e.target.value)}
              placeholder={editingId ? 'API key (leave blank to keep)' : 'API key'}
              className="col-span-2 bg-card border border-border rounded-lg px-2 py-2 text-xs text-slate-300"
            />
            <input
              type="number"
              value={form.priority}
              onChange={(e) => setField('priority', e.target.value)}
              placeholder="priority"
              className="bg-card border border-border rounded-lg px-2 py-2 text-xs text-slate-300"
            />
            <label className="flex items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={(e) => setField('is_active', e.target.checked)}
              />
              Active
            </label>
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={busy}
              onClick={() => void handleSave()}
              className="flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold rounded-lg bg-accent text-black hover:bg-green-400 disabled:opacity-50"
            >
              {editingId ? <Save className="w-3 h-3" /> : <Plus className="w-3 h-3" />}
              {editingId ? 'Update' : 'Add'}
            </button>
            {editingId && (
              <button
                type="button"
                onClick={resetForm}
                className="px-3 py-1.5 text-xs rounded-lg border border-border text-slate-400 hover:text-white"
              >
                Cancel
              </button>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
