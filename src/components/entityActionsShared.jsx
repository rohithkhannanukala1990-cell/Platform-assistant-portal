import { useState, useMemo, useEffect } from 'react'
import { X, Loader2, AlertTriangle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export const STATUS_COLORS = {
  pending: 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/30',
  running: 'bg-blue-500/20 text-blue-300 border border-blue-500/30',
  completed: 'bg-green-500/20 text-green-300 border border-green-500/30',
  failed: 'bg-red-500/20 text-red-300 border border-red-500/30',
  not_implemented: 'bg-amber-500/20 text-amber-300 border border-amber-500/30',
}

export const ACTION_TYPE_COLORS = {
  webhook: 'bg-purple-500/20 text-purple-300',
  script: 'bg-orange-500/20 text-orange-300',
  pipeline: 'bg-blue-500/20 text-blue-300',
  manual: 'bg-gray-500/20 text-gray-300',
  internal: 'bg-blue-500/20 text-blue-300',
  approval: 'bg-amber-500/20 text-amber-300',
}

export function parseConfigSchema(action) {
  const raw = action?.config_schema_json ?? action?.config_json
  if (!raw) return { fields: [], options: {} }
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (Array.isArray(parsed?.fields)) return parsed
    if (Array.isArray(parsed)) return { fields: parsed, options: {} }
    return { fields: [], options: parsed?.options || {} }
  } catch {
    return { fields: [], options: {} }
  }
}

function actionTypeBadgeClass(actionType) {
  return ACTION_TYPE_COLORS[actionType] || ACTION_TYPE_COLORS.manual
}

export function RunActionModal({
  action,
  onClose,
  onSuccess,
  defaultEntityId = '',
  lockEntityId = false,
}) {
  const { authFetch } = useAuth()
  const schema = useMemo(() => parseConfigSchema(action), [action])
  const [entityId, setEntityId] = useState(defaultEntityId || '')
  const [formValues, setFormValues] = useState({})
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    setEntityId(defaultEntityId || '')
  }, [defaultEntityId, action?.id])

  useEffect(() => {
    const initial = {}
    for (const field of schema.fields || []) {
      if (field.default !== undefined && field.default !== null) {
        initial[field.name] = field.default
      } else if (field.type === 'boolean') {
        initial[field.name] = false
      }
    }
    setFormValues(initial)
    setError(null)
  }, [action?.id, schema])

  const requiresApproval = Boolean(action?.requires_approval)

  const handleFieldChange = (name, type, value) => {
    setFormValues((prev) => ({
      ...prev,
      [name]: type === 'boolean' ? Boolean(value) : value,
    }))
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setError(null)
    const targetEntityId = (entityId || '').trim()
    if (!targetEntityId) {
      setError('Target entity ID is required to run this action.')
      return
    }
    for (const field of schema.fields || []) {
      if (field.required && (formValues[field.name] === undefined || formValues[field.name] === '')) {
        setError(`${field.label || field.name} is required.`)
        return
      }
    }
    setSubmitting(true)
    try {
      const res = await authFetch(
        `/api/catalog/${encodeURIComponent(targetEntityId)}/actions/${encodeURIComponent(action.id)}/run`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ inputs_json: formValues }),
        }
      )
      if (!res.ok) throw new Error(await res.text())
      const data = await res.json()
      onSuccess?.(data)
    } catch (err) {
      setError(err.message || 'Failed to run action')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div
        className="bg-[#1a1a2e] border border-white/10 rounded-2xl p-6 w-full max-w-lg shadow-2xl"
        role="dialog"
        aria-modal="true"
      >
        <div className="flex items-start justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg font-semibold text-white">{action.name}</h2>
            <span
              className={`inline-block mt-1 px-2 py-0.5 rounded text-xs font-medium ${actionTypeBadgeClass(action.action_type)}`}
            >
              {action.action_type}
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10"
            aria-label="Close"
          >
            <X size={20} />
          </button>
        </div>

        {requiresApproval && (
          <div className="bg-amber-500/10 border border-amber-500/30 text-amber-300 rounded-lg p-3 mb-4 text-sm">
            ⚠ This action requires approval before execution
          </div>
        )}

        <form onSubmit={(ev) => void handleSubmit(ev)} className="space-y-4">
          {(schema.fields || []).length === 0 ? (
            <p className="text-gray-400 text-sm">No configuration required for this action.</p>
          ) : (
            (schema.fields || []).map((field) => (
              <label key={field.name} className="block">
                <span className="block text-xs font-medium text-gray-400 mb-1.5">
                  {field.label || field.name}
                  {field.required ? ' *' : ''}
                </span>
                {field.type === 'boolean' ? (
                  <input
                    type="checkbox"
                    checked={Boolean(formValues[field.name])}
                    onChange={(ev) => handleFieldChange(field.name, 'boolean', ev.target.checked)}
                    className="rounded border-white/20"
                  />
                ) : field.type === 'select' ? (
                  <select
                    value={formValues[field.name] ?? ''}
                    onChange={(ev) => handleFieldChange(field.name, 'select', ev.target.value)}
                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white w-full focus:outline-none focus:border-blue-500/50 transition-colors"
                  >
                    <option value="">Select…</option>
                    {(schema.options?.[field.name] || field.options || []).map((opt) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                ) : field.type === 'number' ? (
                  <input
                    type="number"
                    value={formValues[field.name] ?? ''}
                    onChange={(ev) => handleFieldChange(field.name, 'number', ev.target.value)}
                    placeholder={field.placeholder || ''}
                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500 w-full focus:outline-none focus:border-blue-500/50 transition-colors"
                  />
                ) : (
                  <input
                    type="text"
                    value={formValues[field.name] ?? ''}
                    onChange={(ev) => handleFieldChange(field.name, 'string', ev.target.value)}
                    placeholder={field.placeholder || ''}
                    className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500 w-full focus:outline-none focus:border-blue-500/50 transition-colors"
                  />
                )}
              </label>
            ))
          )}

          {!lockEntityId && (
            <label className="block">
              <span className="block text-xs font-medium text-gray-400 mb-1.5">
                Target Entity ID
              </span>
              <input
                type="text"
                value={entityId}
                onChange={(ev) => setEntityId(ev.target.value)}
                placeholder="Enter catalog entity ID"
                className="bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-white placeholder-gray-500 w-full focus:outline-none focus:border-blue-500/50 transition-colors"
              />
            </label>
          )}

          {error && (
            <p className="text-sm text-red-400 bg-red-500/10 border border-red-500/30 rounded-lg px-3 py-2">
              {error}
            </p>
          )}

          <div className="flex gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              className="flex-1 py-2.5 rounded-lg border border-white/10 text-gray-300 text-sm font-medium hover:bg-white/5"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={submitting}
              className={`flex-1 py-2.5 rounded-lg text-white text-sm font-semibold disabled:opacity-50 flex items-center justify-center gap-2 ${
                requiresApproval ? 'bg-amber-600 hover:bg-amber-500' : 'bg-blue-600 hover:bg-blue-500'
              }`}
            >
              {submitting && <Loader2 size={16} className="animate-spin" />}
              {submitting ? 'Running…' : requiresApproval ? 'Submit for Approval' : 'Run Now'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

export function LogsDrawer({ run, onClose }) {
  const statusClass = STATUS_COLORS[run?.status] || STATUS_COLORS.pending

  return (
    <>
      <button
        type="button"
        aria-label="Close logs drawer"
        className="fixed inset-0 z-40 bg-black/50"
        onClick={onClose}
      />
      <aside className="fixed right-0 top-0 h-full w-full max-w-[480px] z-50 bg-[#0f0f1a] border-l border-white/10 p-6 overflow-y-auto shadow-2xl">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-white">Execution Logs</h2>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded-lg text-gray-400 hover:text-white hover:bg-white/10"
          >
            <X size={20} />
          </button>
        </div>
        <span className={`inline-flex px-2 py-0.5 rounded-full text-xs font-medium mb-4 ${statusClass}`}>
          {run?.status || 'unknown'}
        </span>
        <div className="text-xs text-gray-400 space-y-1 mb-4 border-b border-white/5 pb-4">
          <p>
            <span className="text-gray-500">Entity:</span> {run?.entity_id || '—'}
          </p>
          <p>
            <span className="text-gray-500">Requested by:</span> {run?.requested_by || '—'}
          </p>
          <p>
            <span className="text-gray-500">Started:</span>{' '}
            {run?.created_at ? new Date(run.created_at).toLocaleString() : '—'}
          </p>
        </div>
        {run?.execution_logs ? (
          <pre className="text-xs text-green-300 font-mono bg-black/40 p-4 rounded-lg overflow-x-auto whitespace-pre-wrap border border-white/5">
            {run.execution_logs}
          </pre>
        ) : (
          <p className="text-sm text-gray-500">No logs available for this run.</p>
        )}
      </aside>
    </>
  )
}
