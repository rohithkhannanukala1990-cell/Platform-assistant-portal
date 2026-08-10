import { useMemo } from 'react'

export const EVENT_SOURCES = [
  'alert_rule_match',
  'webhook_inbound',
  'catalog_entity_changed',
  'agent_run_completed',
  'incident_created',
]

// Extracted so both the workflow list page and the visual builder can reuse
// the exact same manual/schedule/event trigger UI (incl. cron preview).
export default function TriggerConfigPanel({ form, setForm, preview, previewLoading }) {
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
              {(preview?.next_fire_times || []).slice(0, 5).map((t) => (
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
