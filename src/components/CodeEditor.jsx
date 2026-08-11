import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import Editor, { DiffEditor } from '@monaco-editor/react'
import { useSearchParams } from 'react-router-dom'
import { authFetch } from '../utils/api'
import EditorAgentPanel, { SuggestedEditCard } from './editor/EditorAgentPanel'

const LANGUAGES = [
  'yaml', 'json', 'python', 'javascript', 'typescript',
  'bash', 'dockerfile', 'hcl', 'sql', 'markdown',
]

const SNAPSHOT_KEY = 'aiops_editor_crash_snapshot'

export function detectLanguage(filename) {
  if (!filename) return 'yaml'
  const ext = filename.split('.').pop().toLowerCase()
  const map = {
    yml: 'yaml', yaml: 'yaml', json: 'json', py: 'python',
    js: 'javascript', jsx: 'javascript',
    ts: 'typescript', tsx: 'typescript',
    sh: 'bash', bash: 'bash',
    dockerfile: 'dockerfile', tf: 'hcl', hcl: 'hcl',
    sql: 'sql', md: 'markdown',
  }
  return map[ext] || 'yaml'
}

function Tab({ file, active, dirty, onSelect, onClose }) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={`group flex items-center gap-1 px-3 py-1.5 text-xs border-r border-border ${
        active ? 'bg-slate-900 text-white' : 'bg-slate-950 text-slate-400 hover:text-slate-200'
      }`}
      data-testid={`tab-${file.id}`}
    >
      <span className={dirty ? 'text-amber-300' : ''}>{dirty ? '● ' : ''}{file.filename}</span>
      <span
        role="button"
        tabIndex={0}
        onClick={(e) => {
          e.stopPropagation()
          onClose()
        }}
        className="opacity-0 group-hover:opacity-100 text-slate-500 hover:text-white ml-1"
      >
        ×
      </span>
    </button>
  )
}

export default function CodeEditor() {
  const [searchParams] = useSearchParams()
  const [files, setFiles] = useState([])
  const [openTabs, setOpenTabs] = useState([]) // file ids
  const [activeId, setActiveId] = useState(null)
  const [dirtyMap, setDirtyMap] = useState({})
  const [saveState, setSaveState] = useState('') // '' | saving | saved
  const [tree, setTree] = useState([])
  const [repo, setRepo] = useState(searchParams.get('repo') || '')
  const [refName, setRefName] = useState(searchParams.get('ref') || 'main')
  const [treePath, setTreePath] = useState('')
  const [treeError, setTreeError] = useState('')
  const [agentOpen, setAgentOpen] = useState(false)
  const [selection, setSelection] = useState({ start: 0, end: 0 })
  const [suggestedEdits, setSuggestedEdits] = useState([])
  const [problems, setProblems] = useState([])
  const [prDiff, setPrDiff] = useState(null)
  const [prMeta, setPrMeta] = useState(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [isFullscreen, setFullscreen] = useState(false)
  const [githubConnected, setGithubConnected] = useState(null) // null = checking
  const [templates, setTemplates] = useState([])
  const [templatePickerOpen, setTemplatePickerOpen] = useState(false)
  const [hintDismissed, setHintDismissed] = useState(true) // default hidden until we know
  const debounceRef = useRef(null)
  const editorRef = useRef(null)
  const contentCache = useRef({})

  const active = useMemo(
    () => openTabs.map((id) => files.find((f) => f.id === id) || contentCache.current[id]).find((f) => f?.id === activeId) || files.find((f) => f.id === activeId),
    [openTabs, files, activeId]
  )

  const loadFiles = useCallback(async () => {
    const res = await authFetch('/api/editor/files')
    if (!res.ok) return
    const data = await res.json()
    setFiles(Array.isArray(data) ? data : [])
  }, [])

  useEffect(() => {
    void loadFiles()
    try {
      const raw = localStorage.getItem(SNAPSHOT_KEY)
      if (raw) {
        // crash recovery only — do not treat as source of truth
        JSON.parse(raw)
      }
    } catch {
      /* ignore */
    }
  }, [loadFiles])

  // Check GitHub connection proactively so the sidebar can show a clear CTA
  // instead of waiting for a tree fetch to fail.
  useEffect(() => {
    let cancelled = false
    authFetch('/api/tools/github/accounts')
      .then((res) => (res.ok ? res.json() : []))
      .then((accounts) => {
        if (cancelled) return
        const connected = Array.isArray(accounts) && accounts.some((a) => a.status === 'connected')
        setGithubConnected(connected)
      })
      .catch(() => {
        if (!cancelled) setGithubConnected(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    authFetch('/api/editor/templates')
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setTemplates(Array.isArray(data) ? data : []))
      .catch(() => setTemplates([]))
  }, [])

  useEffect(() => {
    authFetch('/api/user-prefs/editor_hint_dismissed')
      .then((res) => (res.ok ? res.json() : { value: null }))
      .then((body) => setHintDismissed(body.value === '1'))
      .catch(() => setHintDismissed(true))
  }, [])

  function dismissHint() {
    setHintDismissed(true)
    void authFetch('/api/user-prefs/editor_hint_dismissed', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ value: '1' }),
    })
  }

  useEffect(() => {
    if (searchParams.get('repo')) {
      setRepo(searchParams.get('repo'))
      void browseTree(searchParams.get('repo'), searchParams.get('ref') || 'main', '')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const openFile = useCallback((file) => {
    contentCache.current[file.id] = file
    setFiles((prev) => {
      const exists = prev.some((f) => f.id === file.id)
      return exists ? prev.map((f) => (f.id === file.id ? file : f)) : [file, ...prev]
    })
    setOpenTabs((tabs) => (tabs.includes(file.id) ? tabs : [...tabs, file.id]))
    setActiveId(file.id)
  }, [])

  const createScratch = useCallback(async (filename = 'untitled.yaml', content = '# Start typing…\n') => {
    const res = await authFetch('/api/editor/files', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ filename, content, language: detectLanguage(filename) }),
    })
    if (!res.ok) return
    const file = await res.json()
    openFile(file)
  }, [openFile])

  const createFromTemplate = useCallback(async (template) => {
    const content = JSON.stringify(
      {
        name: template.name,
        description: template.description,
        category: template.category,
      },
      null,
      2
    )
    const filename = `${(template.name || 'template').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.json`
    setTemplatePickerOpen(false)
    await createScratch(filename, content)
  }, [createScratch])

  const saveFile = useCallback(async (fileId, content, filename) => {
    setSaveState('saving')
    const res = await authFetch(`/api/editor/files/${encodeURIComponent(fileId)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ content, filename }),
    })
    if (!res.ok) {
      setSaveState('')
      return false
    }
    const updated = await res.json()
    contentCache.current[fileId] = updated
    setFiles((prev) => prev.map((f) => (f.id === fileId ? updated : f)))
    setDirtyMap((m) => ({ ...m, [fileId]: false }))
    setSaveState('saved')
    setTimeout(() => setSaveState((s) => (s === 'saved' ? '' : s)), 1500)
    return true
  }, [])

  const onChange = useCallback(
    (val) => {
      if (!activeId) return
      const next = val || ''
      setFiles((prev) =>
        prev.map((f) => (f.id === activeId ? { ...f, content: next } : f))
      )
      contentCache.current[activeId] = {
        ...(contentCache.current[activeId] || {}),
        id: activeId,
        content: next,
      }
      setDirtyMap((m) => ({ ...m, [activeId]: true }))
      try {
        localStorage.setItem(
          SNAPSHOT_KEY,
          JSON.stringify({ id: activeId, content: next, ts: Date.now() })
        )
      } catch {
        /* ignore */
      }
      if (debounceRef.current) clearTimeout(debounceRef.current)
      debounceRef.current = setTimeout(() => {
        const f = contentCache.current[activeId]
        if (f) void saveFile(activeId, f.content, f.filename)
      }, 2000)
    },
    [activeId, saveFile]
  )

  async function browseTree(r = repo, ref = refName, path = treePath) {
    setTreeError('')
    if (!r) return
    const qs = new URLSearchParams({ repo: r, ref, path: path || '' })
    const res = await authFetch(`/api/editor/github/tree?${qs}`)
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      setTree([])
      setTreeError(typeof body.detail === 'string' ? body.detail : 'GitHub browse failed')
      return
    }
    setTree(body.entries || [])
  }

  async function openGithubFile(path) {
    const qs = new URLSearchParams({ repo, ref: refName, path })
    const res = await authFetch(`/api/editor/github/file?${qs}`)
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      setTreeError(typeof body.detail === 'string' ? body.detail : 'Failed to open file')
      return
    }
    openFile(body.file)
  }

  async function validateActive() {
    if (!activeId) return
    const res = await authFetch(`/api/editor/files/${encodeURIComponent(activeId)}/validate`, {
      method: 'POST',
    })
    const body = await res.json().catch(() => ({}))
    setProblems(body.problems || [])
  }

  async function formatActive() {
    if (!activeId) return
    const res = await authFetch(`/api/editor/files/${encodeURIComponent(activeId)}/format`, {
      method: 'POST',
    })
    const body = await res.json().catch(() => ({}))
    if (body.file) openFile(body.file)
  }

  async function proposePr() {
    if (!activeId) return
    const title = window.prompt('PR title', `Update ${active?.filename || 'file'}`)
    if (!title) return
    const res = await authFetch(`/api/editor/files/${encodeURIComponent(activeId)}/propose-pr`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        body: 'Proposed from Platform Editor',
        base_branch: refName || 'main',
      }),
    })
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      window.alert(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail))
      return
    }
    setPrDiff(body.diff || '')
    setPrMeta(body)
  }

  async function approvePr() {
    if (!prMeta?.approval_id) return
    const res = await authFetch(
      `/api/editor/pr-approvals/${encodeURIComponent(prMeta.approval_id)}/approve`,
      { method: 'POST' }
    )
    const body = await res.json().catch(() => ({}))
    if (!res.ok) {
      window.alert(body.detail || 'Approve failed')
      return
    }
    setPrMeta({ ...prMeta, pr_url: body.pr_url, status: 'approved' })
  }

  function acceptEdit(edit) {
    if (!active) return
    let next = active.content || ''
    if (edit.start_offset != null && edit.end_offset != null) {
      next = next.slice(0, edit.start_offset) + (edit.proposed || '') + next.slice(edit.end_offset)
    } else if (edit.original && next.includes(edit.original)) {
      next = next.replace(edit.original, edit.proposed || '')
    }
    onChange(next)
    setSuggestedEdits((eds) => eds.filter((e) => e.id !== edit.id))
  }

  useEffect(() => {
    const onKey = (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        if (activeId && contentCache.current[activeId]) {
          const f = contentCache.current[activeId]
          void saveFile(activeId, f.content, f.filename)
        }
      }
      if ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'p') {
        e.preventDefault()
        setPaletteOpen(true)
      }
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'p' && !e.shiftKey) {
        e.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [activeId, saveFile])

  const language = active?.language || detectLanguage(active?.filename)

  return (
    <div
      className={`flex flex-col bg-gray-900 text-white ${
        isFullscreen ? 'fixed inset-0 z-50' : 'h-[calc(100vh-120px)] w-full rounded-xl overflow-hidden'
      }`}
    >
      <div className="flex items-center gap-3 px-3 py-2 bg-card border-b border-border shrink-0">
        <span className="text-gray-400 text-xs font-semibold uppercase tracking-wide">Code Editor</span>
        <span className="text-[11px] text-slate-500" data-testid="save-indicator">
          {saveState === 'saving' ? 'Saving…' : saveState === 'saved' ? 'Saved' : dirtyMap[activeId] ? 'Unsaved' : ''}
        </span>
        <div className="flex-1" />
        <button type="button" onClick={() => void createScratch()} className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
          New
        </button>
        <button
          type="button"
          onClick={() => setTemplatePickerOpen(true)}
          disabled={!templates.length}
          className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded disabled:opacity-40"
        >
          New from template
        </button>
        <button type="button" onClick={() => void formatActive()} className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
          Format
        </button>
        <button type="button" onClick={() => void validateActive()} className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
          Validate
        </button>
        <button type="button" onClick={() => void proposePr()} className="text-xs bg-indigo-700 hover:bg-indigo-600 px-2 py-1 rounded">
          Propose PR
        </button>
        <button type="button" onClick={() => setAgentOpen((v) => !v)} className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
          Agents
        </button>
        <button type="button" onClick={() => setFullscreen((f) => !f)} className="text-xs bg-gray-700 hover:bg-gray-600 px-2 py-1 rounded">
          {isFullscreen ? 'Exit' : 'Fullscreen'}
        </button>
      </div>

      <div className="flex flex-1 min-h-0">
        <aside className="w-56 shrink-0 border-r border-border bg-slate-950 overflow-auto p-2 text-xs">
          <div className="text-slate-500 uppercase mb-1">My files</div>
          {files.map((f) => (
            <button
              key={f.id}
              type="button"
              onClick={() => openFile(f)}
              className="block w-full text-left truncate px-2 py-1 rounded hover:bg-slate-800 text-slate-300"
            >
              {dirtyMap[f.id] ? '● ' : ''}{f.filename}
            </button>
          ))}
          <div className="text-slate-500 uppercase mt-4 mb-1">GitHub</div>
          {githubConnected === false ? (
            <div className="rounded border border-slate-700 bg-slate-900/60 p-2 text-slate-300 space-y-1.5" data-testid="github-not-connected">
              <p>Repo browsing needs a GitHub connection.</p>
              <a href="/settings" className="text-indigo-300 underline">
                Settings → Tool Registry
              </a>
              <p className="text-slate-500">Local files above work fully without it.</p>
            </div>
          ) : githubConnected === null ? (
            <p className="text-slate-500">Checking GitHub connection…</p>
          ) : (
            <>
              <input
                value={repo}
                onChange={(e) => setRepo(e.target.value)}
                placeholder="org/repo"
                className="w-full mb-1 bg-slate-900 border border-slate-700 rounded px-2 py-1"
              />
              <div className="flex gap-1 mb-1">
                <input
                  value={refName}
                  onChange={(e) => setRefName(e.target.value)}
                  className="flex-1 bg-slate-900 border border-slate-700 rounded px-2 py-1"
                />
                <button type="button" onClick={() => void browseTree()} className="px-2 rounded bg-slate-800">
                  Go
                </button>
              </div>
              {treeError ? <p className="text-rose-300 mb-1">{treeError}</p> : null}
              {tree.map((e) => (
                <button
                  key={e.path}
                  type="button"
                  onClick={() => {
                    if (e.type === 'dir') {
                      setTreePath(e.path)
                      void browseTree(repo, refName, e.path)
                    } else {
                      void openGithubFile(e.path)
                    }
                  }}
                  className="block w-full text-left truncate px-2 py-1 rounded hover:bg-slate-800 text-slate-300"
                >
                  {e.type === 'dir' ? '📁 ' : '📄 '}
                  {e.name}
                </button>
              ))}
            </>
          )}
        </aside>

        <div className="flex-1 flex flex-col min-w-0">
          {!hintDismissed ? (
            <div className="flex items-center gap-3 border-b border-border bg-indigo-950/40 px-3 py-1.5 text-[11px] text-indigo-200">
              <span>
                This editor: <strong>edits &amp; saves files</strong> (autosave on),{' '}
                <strong>runs agent actions</strong> on a selection (Agents panel), and{' '}
                <strong>proposes pull requests</strong> from GitHub-linked files.
              </span>
              <button type="button" onClick={dismissHint} className="ml-auto text-indigo-300 hover:text-white">
                Dismiss
              </button>
            </div>
          ) : null}
          <div className="flex overflow-x-auto border-b border-border bg-slate-950">
            {openTabs.map((id) => {
              const f = files.find((x) => x.id === id) || contentCache.current[id]
              if (!f) return null
              return (
                <Tab
                  key={id}
                  file={f}
                  active={id === activeId}
                  dirty={!!dirtyMap[id]}
                  onSelect={() => setActiveId(id)}
                  onClose={() => {
                    setOpenTabs((t) => t.filter((x) => x !== id))
                    if (activeId === id) setActiveId(null)
                  }}
                />
              )
            })}
          </div>
          <div className="flex-1 min-h-0">
            {active ? (
              <Editor
                height="100%"
                language={language}
                value={active.content || ''}
                onChange={onChange}
                theme="vs-dark"
                onMount={(ed) => {
                  editorRef.current = ed
                  ed.onDidChangeCursorSelection((sel) => {
                    const model = ed.getModel()
                    if (!model) return
                    const s = model.getOffsetAt(sel.selection.getStartPosition())
                    const e = model.getOffsetAt(sel.selection.getEndPosition())
                    setSelection({ start: s, end: e })
                  })
                }}
                options={{
                  fontSize: 14,
                  minimap: { enabled: false },
                  scrollBeyondLastLine: false,
                  wordWrap: 'on',
                  automaticLayout: true,
                  tabSize: 2,
                }}
              />
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 text-sm">
                Open a file or create a new scratch buffer
              </div>
            )}
          </div>
          {suggestedEdits.length ? (
            <div className="max-h-56 overflow-auto border-t border-border p-2 bg-slate-950">
              {suggestedEdits.map((edit) => (
                <SuggestedEditCard
                  key={edit.id}
                  edit={edit}
                  onAccept={acceptEdit}
                  onReject={(e) => setSuggestedEdits((eds) => eds.filter((x) => x.id !== e.id))}
                />
              ))}
            </div>
          ) : null}
          {problems.length ? (
            <div className="border-t border-border px-3 py-2 text-xs text-rose-300 bg-slate-950">
              Problems: {problems.map((p) => p.message).join(' · ')}
            </div>
          ) : null}
          {prDiff != null ? (
            <div className="border-t border-border p-2 bg-slate-950 space-y-2">
              <div className="flex items-center gap-2 text-xs">
                <span>PR proposal {prMeta?.approval_id}</span>
                {prMeta?.pr_url ? (
                  <a href={prMeta.pr_url} target="_blank" rel="noreferrer" className="text-indigo-300 underline">
                    Open PR
                  </a>
                ) : (
                  <button type="button" onClick={() => void approvePr()} className="px-2 py-0.5 rounded bg-emerald-700">
                    Approve & create PR
                  </button>
                )}
                <button type="button" onClick={() => setPrDiff(null)} className="text-slate-500">
                  Dismiss
                </button>
              </div>
              <pre className="text-[11px] text-slate-300 max-h-40 overflow-auto whitespace-pre-wrap">{prDiff}</pre>
            </div>
          ) : null}
        </div>

        <EditorAgentPanel
          open={agentOpen}
          onClose={() => setAgentOpen(false)}
          file={active}
          selection={selection}
          onSuggestedEdits={(eds) => setSuggestedEdits(eds)}
        />
      </div>

      {paletteOpen ? (
        <div className="fixed inset-0 z-[90] bg-black/50 flex items-start justify-center pt-24" onClick={() => setPaletteOpen(false)}>
          <div className="w-full max-w-md bg-slate-900 border border-border rounded-xl p-2" onClick={(e) => e.stopPropagation()}>
            {[
              ['Save', () => activeId && saveFile(activeId, contentCache.current[activeId]?.content, contentCache.current[activeId]?.filename)],
              ['Format', () => formatActive()],
              ['Validate', () => validateActive()],
              ['Propose PR', () => proposePr()],
              ['Toggle Agents', () => setAgentOpen((v) => !v)],
            ].map(([label, fn]) => (
              <button
                key={label}
                type="button"
                className="w-full text-left px-3 py-2 text-sm hover:bg-slate-800 rounded"
                onClick={() => {
                  setPaletteOpen(false)
                  void fn()
                }}
              >
                {label}
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {templatePickerOpen ? (
        <div className="fixed inset-0 z-[90] bg-black/50 flex items-start justify-center pt-24" onClick={() => setTemplatePickerOpen(false)}>
          <div className="w-full max-w-md bg-slate-900 border border-border rounded-xl p-2 max-h-[70vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
            <div className="px-3 py-2 text-xs uppercase text-slate-500">New from template</div>
            {templates.length === 0 ? (
              <p className="px-3 py-2 text-sm text-slate-400">No templates available.</p>
            ) : (
              templates.map((t) => (
                <button
                  key={t.id}
                  type="button"
                  className="w-full text-left px-3 py-2 text-sm hover:bg-slate-800 rounded"
                  onClick={() => void createFromTemplate(t)}
                >
                  <div className="text-white">{t.name}</div>
                  {t.description ? <div className="text-xs text-slate-400 truncate">{t.description}</div> : null}
                </button>
              ))
            )}
          </div>
        </div>
      ) : null}
    </div>
  )
}
