import { useCallback, useEffect, useState } from 'react'
import { Bell, Loader2, Plus, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const ACTION_OPTIONS = [
  { value: 'create_incident', label: 'Create incident' },
  { value: 'suppress', label: 'Suppress' },
  { value: 'attach_existing', label: 'Attach to existing (group)' },
]

const EMPTY_FORM = {
  name: '',
  match_service: '',
  match_severity: '',
  match_title_regex: '',
  group_window_sec: 300,
  action: 'create_incident',
  priority: 100,
  enabled: true,
}

export default function AlertRulesPanel() {
  const { authFetch, role } = useAuth()
  const [rules, setRules] = useState([])
  const [error, setError] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)
  const [saving, setSaving] = useState(false)

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/api/alert-rules')
      if (!res.ok) throw new Error('Failed to load alert rules')
      setRules(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load alert rules')
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  async function createRule(e) {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    setError(null)
    try {
      const res = await authFetch('/api/alert-rules', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          ...form,
          match_service: form.match_service || null,
          match_severity: form.match_severity || null,
          match_title_regex: form.match_title_regex || null,
        }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        throw new Error(body.detail || 'Create failed')
      }
      setForm(EMPTY_FORM)
      await load()
    } catch (e) {
      setError(e.message || 'Create failed')
    } finally {
      setSaving(false)
    }
  }

  async function deleteRule(id) {
    if (!window.confirm('Delete this alert rule?')) return
    const res = await authFetch(`/api/alert-rules/${id}`, { method: 'DELETE' })
    if (res.ok) await load()
  }

  if (role !== 'Admin') {
    return (
      <p className="text-xs text-slate-500">Alert rules are available to administrators only.</p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <Bell className="w-4 h-4 text-amber-400" />
        <h3 className="text-xs font-bold text-white uppercase tracking-wide">Alert rules (v1)</h3>
        <span className="text-[10px] text-slate-500">Rules-based correlation — not ML</span>
      </div>

      {error && (
        <div className="text-xs text-red-400 border border-red-500/30 bg-red-500/10 rounded-lg px-3 py-2">
          {error}
        </div>
      )}

      <form onSubmit={createRule} className="grid gap-2 md:grid-cols-2 text-xs">
        <input
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          placeholder="Rule name"
          value={form.name}
          onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
        />
        <select
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          value={form.action}
          onChange={(e) => setForm((f) => ({ ...f, action: e.target.value }))}
        >
          {ACTION_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
        <input
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          placeholder="Match service (optional)"
          value={form.match_service}
          onChange={(e) => setForm((f) => ({ ...f, match_service: e.target.value }))}
        />
        <input
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          placeholder="Match severity (optional)"
          value={form.match_severity}
          onChange={(e) => setForm((f) => ({ ...f, match_severity: e.target.value }))}
        />
        <input
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200 md:col-span-2"
          placeholder="Title regex (optional)"
          value={form.match_title_regex}
          onChange={(e) => setForm((f) => ({ ...f, match_title_regex: e.target.value }))}
        />
        <input
          type="number"
          min={0}
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          placeholder="Group window (sec)"
          value={form.group_window_sec}
          onChange={(e) => setForm((f) => ({ ...f, group_window_sec: Number(e.target.value) }))}
        />
        <input
          type="number"
          className="bg-black/30 border border-border rounded-lg px-2 py-1.5 text-slate-200"
          placeholder="Priority"
          value={form.priority}
          onChange={(e) => setForm((f) => ({ ...f, priority: Number(e.target.value) }))}
        />
        <button
          type="submit"
          disabled={saving}
          className="md:col-span-2 inline-flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent/15 border border-accent/40 text-accent text-xs font-semibold hover:bg-accent/25 disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Plus className="w-3 h-3" />}
          Add rule
        </button>
      </form>

      <div className="rounded-xl border border-border overflow-hidden">
        <table className="w-full text-left text-xs">
          <thead className="bg-card text-slate-500 uppercase tracking-wider">
            <tr>
              <th className="px-3 py-2">Name</th>
              <th className="px-3 py-2">Match</th>
              <th className="px-3 py-2">Action</th>
              <th className="px-3 py-2">Window</th>
              <th className="px-3 py-2" />
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {!rules.length ? (
              <tr>
                <td colSpan={5} className="px-3 py-6 text-center text-slate-500">
                  No alert rules yet.
                </td>
              </tr>
            ) : (
              rules.map((rule) => (
                <tr key={rule.id} className="hover:bg-card/40">
                  <td className="px-3 py-2 text-slate-200">{rule.name}</td>
                  <td className="px-3 py-2 text-slate-400 font-mono text-[10px]">
                    {[rule.match_service, rule.match_severity, rule.match_title_regex]
                      .filter(Boolean)
                      .join(' · ') || 'any'}
                  </td>
                  <td className="px-3 py-2 text-slate-300">{rule.action}</td>
                  <td className="px-3 py-2 text-slate-400">{rule.group_window_sec}s</td>
                  <td className="px-3 py-2 text-right">
                    <button
                      type="button"
                      onClick={() => deleteRule(rule.id)}
                      className="text-red-400 hover:text-red-300"
                      aria-label="Delete rule"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
