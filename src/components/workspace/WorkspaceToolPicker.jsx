import { Check, Plus, Search, X } from 'lucide-react'

function isToolAdded(workspaceTools, toolId, accountId) {
  const aid = accountId || null
  return (workspaceTools || []).some(
    (row) => row.tool_id === toolId && (row.account_id || null) === aid
  )
}

export default function WorkspaceToolPicker({
  open,
  loading,
  tools,
  searchQuery,
  onSearchChange,
  accountPick,
  onAccountPickChange,
  workspaceTools,
  onAdd,
  onClose,
}) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
      role="dialog"
      aria-modal="true"
      aria-labelledby="tool-picker-title"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg max-h-[85vh] flex flex-col rounded-xl border border-border bg-slate-950 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h3 id="tool-picker-title" className="font-semibold text-white">
            Add Tool to Workspace
          </h3>
          <button
            type="button"
            className="p-2 rounded-lg hover:bg-slate-800 text-slate-400"
            onClick={onClose}
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
        <div className="px-4 py-3 border-b border-border">
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search tools…"
              className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
            />
          </div>
        </div>
        <div className="overflow-y-auto flex-1 p-2">
          {loading ? (
            <p className="text-center text-slate-400 py-8">Loading tools…</p>
          ) : (
            (Array.isArray(tools) ? tools : []).map((t) => {
              const pickKey = t.id
              const selAcc =
                accountPick[pickKey] !== undefined
                  ? accountPick[pickKey]
                  : t.accounts?.length === 1
                    ? t.accounts[0].id
                    : ''
              const added = isToolAdded(workspaceTools, t.id, selAcc || null)
              return (
                <div
                  key={t.id}
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData('application/x-tool-id', t.id)
                    e.dataTransfer.setData('text/plain', t.id)
                    e.dataTransfer.effectAllowed = 'copy'
                  }}
                  className="flex flex-col gap-2 rounded-lg border border-border/60 p-3 mb-2 bg-slate-900/40 cursor-grab active:cursor-grabbing"
                >
                  <div className="flex items-center gap-2">
                    <span className="text-lg">{t.icon || '🔧'}</span>
                    <div className="flex-1 min-w-0">
                      <div className="font-medium text-white truncate">{t.name}</div>
                      <div className="text-[10px] text-slate-500 uppercase">{t.category}</div>
                    </div>
                  </div>
                  {t.accounts?.length > 0 ? (
                    <select
                      value={selAcc}
                      onChange={(e) =>
                        onAccountPickChange((prev) => ({ ...prev, [pickKey]: e.target.value }))
                      }
                      className="w-full text-sm px-2 py-1.5 rounded-lg bg-slate-900 border border-border text-white"
                    >
                      <option value="">No specific account</option>
                      {t.accounts.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.account_name} ({a.environment})
                        </option>
                      ))}
                    </select>
                  ) : null}
                  <div className="flex justify-end">
                    {added ? (
                      <button
                        type="button"
                        disabled
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-slate-800 text-slate-500 text-xs font-semibold cursor-not-allowed"
                      >
                        <Check className="w-3.5 h-3.5" /> Added
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() => void onAdd(t.id, selAcc || null)}
                        className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-xs font-semibold"
                      >
                        <Plus className="w-3.5 h-3.5" /> Add
                      </button>
                    )}
                  </div>
                </div>
              )
            })
          )}
        </div>
      </div>
    </div>
  )
}
