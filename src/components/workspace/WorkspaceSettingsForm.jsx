import { X } from 'lucide-react'

export const ENV_OPTIONS = [
  { id: 'local', label: 'Local' },
  { id: 'development', label: 'Development' },
  { id: 'test', label: 'Test' },
  { id: 'staging', label: 'Staging' },
  { id: 'production', label: 'Production' },
  { id: 'dr', label: 'DR' },
]

export const ICON_EMOJI_OPTIONS = ['🗂️', '🚨', '🚀', '💰', '🛠️', '🔒', '📊', '🔍', '⚡', '🌐', '🎯', '🔧']

export const COLOR_SWATCHES = [
  '#6366f1',
  '#ef4444',
  '#8b5cf6',
  '#f59e0b',
  '#10b981',
  '#06b6d4',
  '#f43f5e',
  '#84cc16',
]

export function emptyForm() {
  return {
    name: '',
    description: '',
    icon: '🗂️',
    color: '#6366f1',
    environment: 'production',
    tags: [],
    is_pinned: false,
  }
}

function TagInput({ form, setForm, draft, setDraft }) {
  return (
    <div>
      <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Tags</label>
      <input
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === 'Enter') {
            e.preventDefault()
            const v = draft.trim()
            if (v && !form.tags.includes(v)) {
              setForm({ ...form, tags: [...form.tags, v] })
              setDraft('')
            }
          }
        }}
        placeholder="Add tags (e.g. production, sre, oncall)"
        className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
      />
      <div className="flex flex-wrap gap-2 mt-2">
        {form.tags.map((tag) => (
          <button
            key={tag}
            type="button"
            onClick={() => setForm({ ...form, tags: form.tags.filter((x) => x !== tag) })}
            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-slate-800 text-xs text-slate-200 border border-border"
          >
            {tag}
            <X className="w-3 h-3" />
          </button>
        ))}
      </div>
    </div>
  )
}

export default function WorkspaceSettingsForm({
  mode = 'create',
  form,
  setForm,
  tagDraft,
  setTagDraft,
  onCancel,
  onSave,
}) {
  const isEdit = mode === 'edit'

  return (
    <div className="max-w-2xl mx-auto space-y-6 pb-16">
      <h2 className="text-xl font-bold text-white">{isEdit ? 'Edit Workspace' : 'Create Workspace'}</h2>
      <div>
        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">
          Workspace Name *
        </label>
        <input
          value={form.name}
          onChange={(e) => setForm({ ...form, name: e.target.value })}
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white"
          placeholder="My workspace"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Description</label>
        <textarea
          rows={2}
          value={form.description}
          onChange={(e) => setForm({ ...form, description: e.target.value })}
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white resize-none"
        />
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Icon</label>
        <div className="flex flex-wrap gap-2">
          {ICON_EMOJI_OPTIONS.map((ic) => (
            <button
              key={ic}
              type="button"
              onClick={() => setForm({ ...form, icon: ic })}
              className={`text-xl w-11 h-11 rounded-lg border flex items-center justify-center transition-colors ${
                form.icon === ic ? 'border-blue-500 bg-blue-500/20' : 'border-border bg-slate-900 hover:border-slate-500'
              }`}
            >
              {ic}
            </button>
          ))}
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Color</label>
        <div className="flex flex-wrap gap-2">
          {COLOR_SWATCHES.map((c) => (
            <button
              key={c}
              type="button"
              aria-label={c}
              onClick={() => setForm({ ...form, color: c })}
              className={`w-10 h-10 rounded-full border-2 shrink-0 transition-transform ${
                form.color === c ? 'border-white scale-110' : 'border-transparent'
              }`}
              style={{ backgroundColor: c }}
            />
          ))}
        </div>
      </div>
      <div>
        <label className="block text-xs font-semibold text-slate-400 uppercase mb-2">Environment</label>
        <select
          value={form.environment}
          onChange={(e) => setForm({ ...form, environment: e.target.value })}
          className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white"
        >
          {ENV_OPTIONS.map((e) => (
            <option key={e.id} value={e.id}>
              {e.label}
            </option>
          ))}
        </select>
      </div>
      <TagInput form={form} setForm={setForm} draft={tagDraft} setDraft={setTagDraft} />
      <label className="flex items-center gap-3 cursor-pointer">
        <input
          type="checkbox"
          checked={form.is_pinned}
          onChange={(e) => setForm({ ...form, is_pinned: e.target.checked })}
          className="rounded border-slate-500"
        />
        <span className="text-sm text-slate-300">Pin to top</span>
      </label>
      <div className="flex justify-between gap-3 pt-4">
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded-lg border border-border text-slate-300 hover:bg-slate-800"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void onSave()}
          className="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
        >
          Save Workspace
        </button>
      </div>
    </div>
  )
}
