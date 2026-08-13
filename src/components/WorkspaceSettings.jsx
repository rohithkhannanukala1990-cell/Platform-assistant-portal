import { useCallback, useEffect, useState } from 'react'
import { Loader2, Save, Shield, Plug, Route, Flag } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const HITL_MODES = [
  {
    id: 'always',
    label: 'Always require approval',
    hint: 'Every AI tool action waits for HITL.',
  },
  {
    id: 'risky_only',
    label: 'Risky actions only',
    hint: 'Approve deploys, restarts, and destructive ops.',
  },
  {
    id: 'off',
    label: 'Off (non-production)',
    hint: 'Production actions still require HITL — cannot be disabled.',
  },
]

const CONNECTOR_OPTIONS = [
  'aws',
  'gcp',
  'azure',
  'github',
  'gitlab',
  'jira',
  'slack',
  'kubernetes',
  'datadog',
  'pagerduty',
]

/** Workspace settings panel — HITL mode, allowed connectors, golden paths, flags. */
export default function WorkspaceSettings({ workspaceId, workspaceName }) {
  const { authFetch } = useAuth()
  const { toast } = useToast()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [hitlMode, setHitlMode] = useState('risky_only')
  const [allowedConnectors, setAllowedConnectors] = useState([])
  const [goldenPathKeys, setGoldenPathKeys] = useState('')
  const [flagNotes, setFlagNotes] = useState('')
  const [availablePaths, setAvailablePaths] = useState([])

  const load = useCallback(async () => {
    if (!workspaceId) {
      setLoading(false)
      return
    }
    setLoading(true)
    try {
      const [settingsRes, pathsRes] = await Promise.all([
        authFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/settings`),
        authFetch('/api/golden-paths'),
      ])
      if (settingsRes.ok) {
        const data = await settingsRes.json()
        const s = data.settings || {}
        setHitlMode(s.hitl_mode || 'risky_only')
        setAllowedConnectors(Array.isArray(s.allowed_connectors) ? s.allowed_connectors : [])
        setGoldenPathKeys(
          Array.isArray(s.default_golden_path_keys)
            ? s.default_golden_path_keys.join(', ')
            : ''
        )
        const flags = s.flags || {}
        setFlagNotes(typeof flags.notes === 'string' ? flags.notes : '')
      }
      if (pathsRes.ok) {
        const data = await pathsRes.json()
        const items = Array.isArray(data) ? data : data.templates || data.items || []
        setAvailablePaths(items)
      }
    } catch {
      toast.error('Failed to load workspace settings')
    } finally {
      setLoading(false)
    }
  }, [authFetch, workspaceId, toast])

  useEffect(() => {
    void load()
  }, [load])

  const toggleConnector = (id) => {
    setAllowedConnectors((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    )
  }

  const save = async () => {
    if (!workspaceId) return
    setSaving(true)
    try {
      const keys = goldenPathKeys
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean)
      const res = await authFetch(`/api/workspaces/${encodeURIComponent(workspaceId)}/settings`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          hitl_mode: hitlMode,
          allowed_connectors: allowedConnectors,
          default_golden_path_keys: keys,
          flags: { notes: flagNotes },
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      const s = data.settings || {}
      setHitlMode(s.hitl_mode || hitlMode)
      toast.success('Workspace settings saved')
    } catch (e) {
      toast.error(e.message || 'Save failed')
    } finally {
      setSaving(false)
    }
  }

  if (!workspaceId) {
    return (
      <div className="rounded-xl border border-dashed border-border p-6 text-center text-sm text-slate-500">
        Select or activate a workspace to edit settings. Demo mode uses the default workspace.
      </div>
    )
  }

  if (loading) {
    return (
      <div className="flex items-center gap-2 text-sm text-slate-500 py-8 justify-center">
        <Loader2 className="w-4 h-4 animate-spin" /> Loading settings…
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-border bg-card/40 p-5 space-y-6">
      <div className="flex items-start justify-between gap-3 flex-wrap">
        <div>
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Shield className="w-4 h-4 text-violet-400" />
            Workspace settings
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            {workspaceName || workspaceId} — HITL for production actions cannot be disabled.
          </p>
        </div>
        <button
          type="button"
          disabled={saving}
          onClick={() => void save()}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-violet-600 hover:bg-violet-500 text-white text-xs font-semibold disabled:opacity-50"
        >
          {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
          Save
        </button>
      </div>

      <section className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <Shield className="w-3 h-3" /> HITL mode
        </p>
        <div className="flex flex-col gap-2">
          {HITL_MODES.map((m) => (
            <label
              key={m.id}
              className={`flex items-start gap-3 px-3 py-2.5 rounded-lg border cursor-pointer transition-colors ${
                hitlMode === m.id
                  ? 'border-violet-500/40 bg-violet-500/10'
                  : 'border-border hover:bg-slate-800/40'
              }`}
            >
              <input
                type="radio"
                name="hitl_mode"
                className="mt-1"
                checked={hitlMode === m.id}
                onChange={() => setHitlMode(m.id)}
              />
              <span>
                <span className="text-sm text-white font-medium">{m.label}</span>
                <span className="block text-[11px] text-slate-500 mt-0.5">{m.hint}</span>
              </span>
            </label>
          ))}
        </div>
        <p className="text-[11px] text-amber-300/90 border border-amber-500/20 bg-amber-950/20 rounded-lg px-3 py-2">
          Production / DR actions always require human approval, even when mode is “Off”.
        </p>
      </section>

      <section className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <Plug className="w-3 h-3" /> Allowed connectors
        </p>
        <div className="flex flex-wrap gap-2">
          {CONNECTOR_OPTIONS.map((id) => {
            const on = allowedConnectors.includes(id)
            return (
              <button
                key={id}
                type="button"
                onClick={() => toggleConnector(id)}
                className={`px-2.5 py-1 rounded-md text-xs font-semibold border transition-colors ${
                  on
                    ? 'bg-emerald-600/20 border-emerald-500/40 text-emerald-200'
                    : 'bg-slate-900 border-border text-slate-500 hover:text-slate-300'
                }`}
              >
                {id}
              </button>
            )
          })}
        </div>
        <p className="text-[11px] text-slate-500">
          Empty list means all connectors are allowed (demo-friendly default).
        </p>
      </section>

      <section className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <Route className="w-3 h-3" /> Default golden paths
        </p>
        <input
          value={goldenPathKeys}
          onChange={(e) => setGoldenPathKeys(e.target.value)}
          placeholder="create-new-service, onboarding-checklist"
          className="w-full rounded-lg bg-slate-950 border border-border px-3 py-2 text-sm text-white placeholder:text-slate-600"
        />
        {availablePaths.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {availablePaths.slice(0, 8).map((p) => {
              const key = p.key || p.slug || p.id
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    const parts = goldenPathKeys
                      .split(',')
                      .map((x) => x.trim())
                      .filter(Boolean)
                    if (!parts.includes(key)) {
                      setGoldenPathKeys([...parts, key].join(', '))
                    }
                  }}
                  className="text-[10px] px-2 py-0.5 rounded border border-violet-500/30 text-violet-300 hover:bg-violet-500/10"
                >
                  + {p.name || key}
                </button>
              )
            })}
          </div>
        )}
      </section>

      <section className="space-y-2">
        <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500 flex items-center gap-1.5">
          <Flag className="w-3 h-3" /> Notes / flags
        </p>
        <textarea
          value={flagNotes}
          onChange={(e) => setFlagNotes(e.target.value)}
          rows={2}
          placeholder="Optional per-workspace notes"
          className="w-full rounded-lg bg-slate-950 border border-border px-3 py-2 text-sm text-white placeholder:text-slate-600 resize-none"
        />
      </section>
    </div>
  )
}
