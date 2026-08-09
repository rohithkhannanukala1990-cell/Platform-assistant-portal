import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { DiffEditor } from '@monaco-editor/react'
import { authFetch } from '../../utils/api'

const GROUNDING_COLORS = {
  live: 'text-emerald-300',
  partial: 'text-amber-300',
  none: 'text-rose-300',
  demo: 'text-cyan-300',
}

export default function EditorAgentPanel({
  open,
  onClose,
  file,
  selection,
  onSuggestedEdits,
}) {
  const [instruction, setInstruction] = useState('')
  const [busy, setBusy] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  const run = useCallback(
    async (action, agent) => {
      if (!file?.id) return
      setBusy(true)
      setError('')
      try {
        const res = await authFetch(`/api/editor/files/${encodeURIComponent(file.id)}/agent-action`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            action,
            agent,
            instruction: instruction || undefined,
            selection_start: selection?.start ?? 0,
            selection_end: selection?.end ?? (file.content || '').length,
          }),
        })
        const body = await res.json().catch(() => ({}))
        if (!res.ok) throw new Error(body.detail || `Agent failed (${res.status})`)
        setResult(body)
        if (Array.isArray(body.suggested_edits) && body.suggested_edits.length) {
          onSuggestedEdits?.(body.suggested_edits)
        }
      } catch (err) {
        setError(err?.message || 'Agent failed')
      } finally {
        setBusy(false)
      }
    },
    [file, instruction, onSuggestedEdits, selection]
  )

  if (!open) return null

  const grounding = (result?.grounding || 'none').toLowerCase()

  return (
    <aside className="w-80 shrink-0 border-l border-border bg-slate-950 flex flex-col">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-xs font-semibold uppercase tracking-wide text-slate-400">Agent</span>
        <button type="button" onClick={onClose} className="text-slate-500 hover:text-white text-xs">
          Close
        </button>
      </div>
      <div className="p-3 space-y-2 border-b border-border">
        <textarea
          value={instruction}
          onChange={(e) => setInstruction(e.target.value)}
          placeholder="e.g. add a health check to this deployment"
          className="w-full h-20 rounded-lg bg-slate-900 border border-slate-700 text-sm text-slate-200 p-2"
        />
        <div className="flex flex-wrap gap-1">
          {[
            ['review', 'Review'],
            ['explain', 'Explain'],
            ['generate_tests', 'Tests'],
            ['security', 'Security'],
            ['validate_terraform', 'Terraform'],
            ['optimise_query', 'SQL'],
          ].map(([action, label]) => (
            <button
              key={action}
              type="button"
              disabled={busy || !file?.id}
              onClick={() => void run(action)}
              className="text-[11px] px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40"
            >
              {label}
            </button>
          ))}
        </div>
        <button
          type="button"
          disabled={busy || !file?.id || !instruction.trim()}
          onClick={() => void run(undefined, 'documentation_agent')}
          className="w-full text-xs py-1.5 rounded bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40"
        >
          {busy ? 'Running…' : 'Ask'}
        </button>
      </div>
      <div className="flex-1 overflow-auto p-3 text-sm space-y-2">
        {error ? <p className="text-rose-300 text-xs">{error}</p> : null}
        {result ? (
          <>
            <div className="flex items-center gap-2">
              <span className={`text-xs uppercase ${GROUNDING_COLORS[grounding] || GROUNDING_COLORS.none}`}>
                [{grounding === 'none' ? 'no data' : grounding}]
              </span>
              <span className="text-slate-500 text-xs">{result.agent}</span>
            </div>
            {grounding === 'none' && result.connect_hint ? (
              <p className="text-rose-200 text-xs border border-rose-500/30 bg-rose-500/10 rounded p-2">
                {result.connect_hint}
              </p>
            ) : null}
            <p className="text-slate-200 whitespace-pre-wrap">{result.summary}</p>
            {(result.suggested_edits || []).length ? (
              <p className="text-amber-200 text-xs">
                {(result.suggested_edits || []).length} suggested edit(s) — accept each hunk explicitly.
              </p>
            ) : null}
          </>
        ) : (
          <p className="text-slate-500 text-xs">Select code and run an action, or ask a question.</p>
        )}
      </div>
    </aside>
  )
}

export function SuggestedEditCard({ edit, onAccept, onReject }) {
  return (
    <div className="border border-amber-500/30 rounded-lg overflow-hidden bg-slate-900/80 mb-2" data-testid="suggested-edit">
      <div className="flex items-center justify-between px-2 py-1 border-b border-border text-xs text-slate-400">
        <span>{edit.rationale || edit.id || 'Suggested edit'}</span>
        <div className="flex gap-1">
          <button
            type="button"
            data-testid="accept-hunk"
            onClick={() => onAccept(edit)}
            className="px-2 py-0.5 rounded bg-emerald-700 text-white"
          >
            Accept
          </button>
          <button
            type="button"
            data-testid="reject-hunk"
            onClick={() => onReject(edit)}
            className="px-2 py-0.5 rounded bg-slate-700 text-white"
          >
            Reject
          </button>
        </div>
      </div>
      <div className="h-40">
        <DiffEditor
          height="100%"
          original={edit.original || ''}
          modified={edit.proposed || ''}
          language="plaintext"
          theme="vs-dark"
          options={{ readOnly: true, renderSideBySide: true, minimap: { enabled: false } }}
        />
      </div>
    </div>
  )
}
