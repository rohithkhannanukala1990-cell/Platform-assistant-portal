import { useCallback, useEffect, useState } from 'react'
import {
  Plus,
  Trash2,
  Play,
  Save,
  AlertCircle,
  CheckCircle2,
  Plug,
  Loader2,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

const EMPTY_FORM = {
  name: '',
  description: '',
  transport: 'stdio',
  command: '',
  args: '',
  url: '',
  env_json: '',
  enabled: true,
  require_hitl: true,
  allowlist: '',
}

function parseArgs(text) {
  return String(text || '')
    .split(/[\n,]/)
    .map((s) => s.trim())
    .filter(Boolean)
}

function parseEnv(text) {
  const raw = String(text || '').trim()
  if (!raw) return {}
  // Accept either JSON object or KEY=VALUE lines.
  if (raw.startsWith('{')) {
    const obj = JSON.parse(raw)
    return Object.fromEntries(Object.entries(obj).map(([k, v]) => [String(k), String(v)]))
  }
  const env = {}
  for (const line of raw.split('\n')) {
    const idx = line.indexOf('=')
    if (idx <= 0) continue
    env[line.slice(0, idx).trim()] = line.slice(idx + 1).trim()
  }
  return env
}

export default function MCPServersPanel() {
  const { authFetch, role } = useAuth()
  const isAdmin = role === 'Admin'
  const [rows, setRows] = useState([])
  const [form, setForm] = useState(EMPTY_FORM)
  const [editingId, setEditingId] = useState(null)
  const [error, setError] = useState(null)
  const [message, setMessage] = useState(null)
  const [busy, setBusy] = useState(false)
  const [testResult, setTestResult] = useState(null)

  const load = useCallback(async () => {
    if (!isAdmin) return
    try {
      const res = await authFetch('/api/mcp/servers')
      if (!res.ok) throw new Error('Failed to load MCP servers')
      setRows(await res.json())
    } catch (e) {
      setError(e.message || 'Failed to load MCP servers')
    }
  }, [authFetch, isAdmin])

  useEffect(() => {
    void load()
  }, [load])

  function setField(key, value) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function startEdit(row) {
    setEditingId(row.id)
    setForm({
      name: row.name || '',
      description: row.description || '',
      transport: row.transport || 'stdio',
      command: row.command || '',
      args: (row.args || []).join(', '),
      url: row.url || '',
      env_json: '',
      enabled: !!row.enabled,
      require_hitl: !!row.require_hitl,
      allowlist: (row.allowlist || []).join(', '),
    })
    setTestResult(null)
    setMessage(null)
    setError(null)
  }

  function resetForm() {
    setEditingId(null)
    setForm(EMPTY_FORM)
    setTestResult(null)
  }

  async function handleSave() {
    if (!isAdmin) return
    setBusy(true)
    setError(null)
    setMessage(null)
    try {
      const payload = {
        name: form.name.trim(),
        description: form.description.trim(),
        transport: form.transport,
        command: form.command.trim(),
        args: parseArgs(form.args),
        url: form.url.trim(),
        enabled: !!form.enabled,
        require_hitl: !!form.require_hitl,
        allowlist: parseArgs(form.allowlist),
      }
      if (form.env_json.trim()) {
        try {
          payload.env = parseEnv(form.env_json)
        } catch {
          throw new Error('Env must be JSON object or KEY=VALUE lines')
        }
      }

      const res = editingId
        ? await authFetch(`/api/mcp/servers/${editingId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
        : await authFetch('/api/mcp/servers', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
          })
      if (!res.ok) {
        const t = await res.text()
        throw new Error(t || 'Save failed')
      }
      setMessage(editingId ? 'MCP server updated' : 'MCP server created')
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
    if (!window.confirm('Delete this MCP server?')) return
    setBusy(true)
    setError(null)
    try {
      const res = await authFetch(`/api/mcp/servers/${id}`, { method: 'DELETE' })
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
    setTestResult(null)
    try {
      const res = await authFetch(`/api/mcp/servers/${id}/test`, { method: 'POST' })
      const data = await res.json().catch(() => ({}))
      if (!res.ok) throw new Error(data.detail || 'Test failed')
      setTestResult({ id, ...data })
      setMessage(data.connected ? `Connected (${data.tool_count} tools, ${data.latency_ms}ms)` : 'Connection failed')
      if (!data.connected) setError(data.error || 'Connection failed')
    } catch (e) {
      setError(e.message || 'Test failed')
    } finally {
      setBusy(false)
    }
  }

  if (!isAdmin) {
    return (
      <div className="flex flex-col gap-2">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <Plug className="w-3.5 h-3.5 text-cyan-400" />
          MCP Servers
        </div>
        <p className="text-[11px] text-slate-600">Admin role required to manage MCP servers.</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          <Plug className="w-3.5 h-3.5 text-cyan-400" />
          MCP Servers
        </div>
        <button
          type="button"
          onClick={resetForm}
          className="flex items-center gap-1 text-[11px] text-accent hover:text-white"
        >
          <Plus className="w-3 h-3" /> New
        </button>
      </div>
      <p className="text-[11px] text-slate-500">
        Connect external MCP servers as a client. Tool calls still go through auth, tenant scope, and HITL.
      </p>

      {error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-red-500/10 border border-red-500/30 text-xs text-red-400">
          <AlertCircle className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}
      {message && !error && (
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-xs text-emerald-400">
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
          {message}
        </div>
      )}

      <div className="flex flex-col gap-2">
        {rows.length === 0 && (
          <p className="text-[11px] text-slate-600">No MCP servers configured yet.</p>
        )}
        {rows.map((row) => (
          <div
            key={row.id}
            className="flex items-start justify-between gap-2 px-3 py-2 rounded-lg border border-border bg-card"
          >
            <button type="button" onClick={() => startEdit(row)} className="text-left flex-1 min-w-0">
              <div className="text-xs font-semibold text-slate-200 truncate">{row.name}</div>
              <div className="text-[10px] text-slate-500 truncate">
                {row.transport}
                {row.transport === 'stdio' ? ` · ${row.command}` : ` · ${row.url}`}
                {row.has_env ? ` · env: ${(row.env_keys || []).join(', ')}` : ''}
                {row.require_hitl ? ' · HITL' : ''}
                {!row.enabled ? ' · disabled' : ''}
              </div>
            </button>
            <div className="flex items-center gap-1 shrink-0">
              <button
                type="button"
                title="Test connection"
                disabled={busy}
                onClick={() => handleTest(row.id)}
                className="p-1.5 rounded-md hover:bg-surface text-slate-400 hover:text-accent"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
              </button>
              <button
                type="button"
                title="Delete"
                disabled={busy}
                onClick={() => handleDelete(row.id)}
                className="p-1.5 rounded-md hover:bg-surface text-slate-400 hover:text-red-400"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        ))}
      </div>

      {testResult?.tools?.length > 0 && (
        <div className="text-[10px] text-slate-400 border border-border rounded-lg p-2 bg-card/60">
          Tools from last test: {testResult.tools.map((t) => t.name).join(', ')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Name</span>
          <input
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
            value={form.name}
            onChange={(e) => setField('name', e.target.value)}
            placeholder="filesystem"
          />
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Transport</span>
          <select
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
            value={form.transport}
            onChange={(e) => setField('transport', e.target.value)}
          >
            <option value="stdio">stdio</option>
            <option value="sse">sse</option>
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Enabled</span>
          <select
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
            value={form.enabled ? '1' : '0'}
            onChange={(e) => setField('enabled', e.target.value === '1')}
          >
            <option value="1">Yes</option>
            <option value="0">No</option>
          </select>
        </label>
        {form.transport === 'stdio' ? (
          <>
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-[10px] text-slate-500 uppercase">Command</span>
              <input
                className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
                value={form.command}
                onChange={(e) => setField('command', e.target.value)}
                placeholder="npx"
              />
            </label>
            <label className="col-span-2 flex flex-col gap-1">
              <span className="text-[10px] text-slate-500 uppercase">Args (comma-separated)</span>
              <input
                className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
                value={form.args}
                onChange={(e) => setField('args', e.target.value)}
                placeholder="-y, @modelcontextprotocol/server-filesystem, /tmp"
              />
            </label>
          </>
        ) : (
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-[10px] text-slate-500 uppercase">URL</span>
            <input
              className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
              value={form.url}
              onChange={(e) => setField('url', e.target.value)}
              placeholder="https://mcp.example.com/sse"
            />
          </label>
        )}
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">
            Env secrets {editingId ? '(leave blank to keep)' : '(JSON or KEY=VALUE)'}
          </span>
          <textarea
            rows={2}
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200 font-mono"
            value={form.env_json}
            onChange={(e) => setField('env_json', e.target.value)}
            placeholder={'API_KEY=...\n# or {"API_KEY":"..."}'}
          />
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Allowlist (empty = all)</span>
          <input
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
            value={form.allowlist}
            onChange={(e) => setField('allowlist', e.target.value)}
            placeholder="list_files, get_issue"
          />
        </label>
        <label className="col-span-2 flex items-center gap-2 text-xs text-slate-300">
          <input
            type="checkbox"
            checked={!!form.require_hitl}
            onChange={(e) => setField('require_hitl', e.target.checked)}
          />
          Require HITL approval for every tool on this server
        </label>
        <label className="col-span-2 flex flex-col gap-1">
          <span className="text-[10px] text-slate-500 uppercase">Description</span>
          <input
            className="px-2 py-1.5 text-xs rounded-lg bg-card border border-border text-slate-200"
            value={form.description}
            onChange={(e) => setField('description', e.target.value)}
          />
        </label>
      </div>

      <button
        type="button"
        disabled={busy || !form.name.trim()}
        onClick={handleSave}
        className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg bg-accent/20 border border-accent/40 text-accent text-xs font-semibold hover:bg-accent/30 disabled:opacity-50"
      >
        <Save className="w-3.5 h-3.5" />
        {editingId ? 'Update server' : 'Add server'}
      </button>
    </div>
  )
}
