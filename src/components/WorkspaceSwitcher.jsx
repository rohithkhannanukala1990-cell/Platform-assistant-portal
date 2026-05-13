import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, Plus, Check, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'

function envBadgeClass(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production' || e === 'dr') return 'bg-rose-500/15 text-rose-200 border-rose-500/30'
  if (e === 'staging') return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
  return 'bg-slate-500/15 text-slate-200 border-slate-500/30'
}

function truncate(s, max) {
  if (!s) return ''
  return s.length <= max ? s : `${s.slice(0, max)}…`
}

export default function WorkspaceSwitcher() {
  const navigate = useNavigate()
  const { authFetch } = useAuth()
  const { activeWorkspace, pinnedWorkspaces, setActiveWorkspace, refetchPinnedWorkspaces } =
    usePortalContext()
  const [isOpen, setIsOpen] = useState(false)
  const [allList, setAllList] = useState([])
  const rootRef = useRef(null)

  const loadAll = useCallback(async () => {
    try {
      const res = await authFetch('/api/workspaces')
      if (!res.ok) {
        setAllList([])
        return
      }
      const data = await res.json()
      const rows = (Array.isArray(data) ? data : []).filter((w) => !w.is_pinned).slice(0, 8)
      setAllList(rows)
    } catch {
      setAllList([])
    }
  }, [authFetch])

  useEffect(() => {
    if (!isOpen) return undefined
    void loadAll()
    void refetchPinnedWorkspaces()
  }, [isOpen, loadAll, refetchPinnedWorkspaces])

  useEffect(() => {
    if (!isOpen) return undefined
    function onDoc(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) setIsOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [isOpen])

  const triggerLabel = useMemo(() => {
    if (activeWorkspace) {
      return (
        <>
          <span className="text-base leading-none shrink-0">{activeWorkspace.icon || '🗂️'}</span>
          <span className="font-medium truncate max-w-[140px]">{activeWorkspace.name}</span>
        </>
      )
    }
    return (
      <>
        <span className="text-base leading-none shrink-0">🗂️</span>
        <span className="font-medium">Workspace</span>
      </>
    )
  }, [activeWorkspace])

  const onPick = async (ws) => {
    await setActiveWorkspace(ws)
    setIsOpen(false)
  }

  const onClear = async () => {
    await setActiveWorkspace(null)
    setIsOpen(false)
  }

  const renderWorkspaceRow = (ws) => {
    const active = activeWorkspace?.id === ws.id
    return (
      <button
        key={ws.id}
        type="button"
        onClick={() => void onPick(ws)}
        className={`w-full text-left px-3 py-2 flex items-center gap-2 hover:bg-gray-700/80 rounded-md transition-colors ${
          active ? 'bg-blue-500/15 border border-blue-500/30' : ''
        }`}
      >
        <span className="text-lg shrink-0">{ws.icon || '🗂️'}</span>
        <span className="flex-1 min-w-0 text-sm text-white truncate">{truncate(ws.name, 20)}</span>
        {active ? <Check className="w-4 h-4 text-blue-400 shrink-0" aria-label="Active" /> : null}
        <span
          className={`text-[10px] px-1.5 py-0.5 rounded border uppercase font-semibold shrink-0 ${envBadgeClass(ws.environment)}`}
        >
          {ws.environment}
        </span>
      </button>
    )
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-sm text-slate-200 hover:bg-gray-700/80 hover:border-gray-600 transition-colors max-w-[220px]"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        {triggerLabel}
        <ChevronDown className={`w-4 h-4 text-slate-500 shrink-0 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div
          className="absolute right-0 top-full mt-1 z-[100] w-[280px] rounded-lg border border-gray-700 bg-gray-800 shadow-xl py-2 px-2 flex flex-col gap-2 max-h-[min(480px,80vh)] overflow-y-auto"
          role="listbox"
        >
          <div className="flex items-center justify-between gap-2 px-1">
            <span className="text-xs font-semibold text-slate-400">Switch Workspace</span>
            <button
              type="button"
              onClick={() => {
                setIsOpen(false)
                navigate('/ops?view=workspaces&create=true')
              }}
              className="inline-flex items-center gap-1 px-2 py-1 rounded-md bg-blue-600 hover:bg-blue-500 text-white text-[11px] font-semibold"
            >
              <Plus className="w-3 h-3" /> New Workspace
            </button>
          </div>

          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider px-1 mb-1">📌 Pinned</p>
            <div className="space-y-0.5">
              {pinnedWorkspaces.length ? pinnedWorkspaces.map(renderWorkspaceRow) : null}
            </div>
            {!pinnedWorkspaces.length ? (
              <p className="text-[11px] text-slate-500 px-1 py-1">No pinned workspaces</p>
            ) : null}
          </div>

          <div className="border-t border-gray-700/80" />

          <div>
            <p className="text-[10px] text-slate-500 uppercase tracking-wider px-1 mb-1">All</p>
            <div className="space-y-0.5">{allList.map(renderWorkspaceRow)}</div>
            <button
              type="button"
              className="w-full text-left text-xs text-blue-400 hover:text-blue-300 px-2 py-1.5 mt-1"
              onClick={() => {
                setIsOpen(false)
                navigate('/ops?view=workspaces')
              }}
            >
              View All →
            </button>
          </div>

          {activeWorkspace ? (
            <>
              <div className="border-t border-gray-700/80" />
              <button
                type="button"
                onClick={() => void onClear()}
                className="w-full inline-flex items-center justify-center gap-2 px-2 py-2 rounded-lg border border-gray-600 text-sm text-slate-300 hover:bg-gray-700/80"
              >
                <X className="w-4 h-4" /> Clear Workspace
              </button>
            </>
          ) : null}
        </div>
      )}
    </div>
  )
}
