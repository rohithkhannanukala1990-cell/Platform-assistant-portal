import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useSearchParams, useNavigate } from 'react-router-dom'
import {
  Plus,
  Edit2,
  Trash2,
  Copy,
  Pin,
  PinOff,
  ChevronRight,
  GripVertical,
  Check,
  X,
  Layers,
  Zap,
  Shield,
  DollarSign,
  Wrench,
  Search,
  Filter,
  RefreshCw,
  ExternalLink,
  Settings,
  Users,
  Activity,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { usePortalContext } from '../contexts/PortalContext'
import { useToast } from './ToastNotification'
import { PermissionGate } from './PermissionGate'

function debounce(fn, wait) {
  let t
  return (...args) => {
    clearTimeout(t)
    t = setTimeout(() => fn(...args), wait)
  }
}

function ToolCard({ tool, onSwitchAccount, onRunAgent, onRemove }) {
  const statusColor = tool.status === 'connected' ? 'text-green-400' : 'text-red-400'

  return (
    <div className="bg-gray-800 border border-gray-600 rounded-xl p-4 w-56 shadow-lg select-none">
      <div className="flex items-center justify-between mb-2">
        <span className="text-white font-semibold capitalize">{tool.tool_id}</span>
        <button
          type="button"
          onClick={onRemove}
          className="text-gray-500 hover:text-red-400 text-xs"
          aria-label="Remove tool"
        >
          ✕
        </button>
      </div>
      <div className="text-xs text-gray-400 mb-1">
        Account: <span className="text-gray-200">{tool.account_name}</span>
      </div>
      <div className={`text-xs mb-3 ${statusColor}`}>
        {tool.status === 'connected' ? '● Connected' : '● Disconnected'}
      </div>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={onSwitchAccount}
          className="flex-1 text-xs bg-gray-700 hover:bg-gray-600 text-white rounded px-2 py-1"
        >
          Switch Account ▾
        </button>
        <button
          type="button"
          onClick={onRunAgent}
          className="flex-1 text-xs bg-indigo-600 hover:bg-indigo-500 text-white rounded px-2 py-1"
        >
          Run Agent ▶
        </button>
      </div>
    </div>
  )
}

function AccountSelectorModal({ toolId, workspaceId, onSelect, onClose }) {
  const { authFetch } = useAuth()
  const [accounts, setAccounts] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    authFetch(`/api/workspaces/${workspaceId}/tools/${toolId}/accounts`)
      .then((r) => (r.ok ? r.json() : []))
      .then((data) => {
        if (cancelled) return
        setAccounts(Array.isArray(data) ? data : [])
        setLoading(false)
      })
      .catch(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [authFetch, toolId, workspaceId])

  return (
    <div className="fixed inset-0 bg-black/60 flex items-center justify-center z-50">
      <div className="bg-gray-800 rounded-xl p-6 w-80 shadow-2xl">
        <h3 className="text-white font-semibold mb-4">Select Account — {toolId}</h3>
        {loading && <p className="text-gray-400 text-sm">Loading accounts…</p>}
        {!loading && accounts.length === 0 && (
          <p className="text-gray-400 text-sm">No accounts connected for {toolId}.</p>
        )}
        {accounts.map((acc) => (
          <button
            key={acc.account_alias}
            type="button"
            onClick={() => onSelect(acc)}
            className="w-full text-left px-4 py-3 rounded-lg bg-gray-700 hover:bg-indigo-700 text-white text-sm mb-2"
          >
            <span className="font-medium">{acc.account_name}</span>
            <span className="text-gray-400 ml-2 text-xs">({acc.account_alias})</span>
            <span
              className={`float-right text-xs ${
                acc.status === 'connected' ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {acc.status}
            </span>
          </button>
        ))}
        <button
          type="button"
          onClick={onClose}
          className="mt-2 w-full text-gray-400 hover:text-white text-sm py-2"
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

const ENV_OPTIONS = [
  { id: 'local', label: 'Local' },
  { id: 'development', label: 'Development' },
  { id: 'test', label: 'Test' },
  { id: 'staging', label: 'Staging' },
  { id: 'production', label: 'Production' },
  { id: 'dr', label: 'DR' },
]

const ICON_EMOJI_OPTIONS = ['🗂️', '🚨', '🚀', '💰', '🛠️', '🔒', '📊', '🔍', '⚡', '🌐', '🎯', '🔧']

const COLOR_SWATCHES = [
  '#6366f1',
  '#ef4444',
  '#8b5cf6',
  '#f59e0b',
  '#10b981',
  '#06b6d4',
  '#f43f5e',
  '#84cc16',
]

function emptyForm() {
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

function flattenGroupedTools(grouped) {
  const out = []
  if (!grouped || typeof grouped !== 'object') return out
  for (const [, list] of Object.entries(grouped)) {
    if (Array.isArray(list)) {
      for (const t of list) out.push({ ...t })
    }
  }
  return out.sort((a, b) => (a.name || '').localeCompare(b.name || ''))
}

function matchesSearch(ws, q) {
  if (!q.trim()) return true
  const s = q.toLowerCase()
  const tags = Array.isArray(ws.tags) ? ws.tags.join(' ').toLowerCase() : ''
  return (
    (ws.name || '').toLowerCase().includes(s) ||
    (ws.description || '').toLowerCase().includes(s) ||
    tags.includes(s)
  )
}

function isToolAdded(workspaceTools, toolId, accountId) {
  const aid = accountId || null
  return (workspaceTools || []).some(
    (row) => row.tool_id === toolId && (row.account_id || null) === aid
  )
}

function statusDotClass(status) {
  if (status === 'connected') return 'bg-emerald-500'
  if (status === 'failed') return 'bg-red-500'
  return 'bg-slate-500'
}

function envBadge(env) {
  const e = (env || '').toLowerCase()
  if (e === 'production' || e === 'dr') return 'bg-rose-500/15 text-rose-200 border-rose-500/30'
  if (e === 'staging') return 'bg-amber-500/15 text-amber-200 border-amber-500/30'
  return 'bg-slate-500/15 text-slate-200 border-slate-500/30'
}

export default function WorkspaceBuilder() {
  const { authFetch } = useAuth()
  const { showToast, toast } = useToast()
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const { setActiveWorkspace, refetchPinnedWorkspaces } = usePortalContext()
  const canvasRef = useRef(null)

  const [view, setView] = useState('list')
  const [workspaces, setWorkspaces] = useState([])
  const [selectedWorkspace, setSelectedWorkspace] = useState(null)
  const [isLoading, setIsLoading] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [createForm, setCreateForm] = useState(emptyForm)
  const [editForm, setEditForm] = useState(emptyForm)
  const [toolPickerOpen, setToolPickerOpen] = useState(false)
  const [availableTools, setAvailableTools] = useState([])
  const [toolSearchQuery, setToolSearchQuery] = useState('')
  const [dragOrder, setDragOrder] = useState([])
  const [dragFromIndex, setDragFromIndex] = useState(null)
  const [health, setHealth] = useState(null)
  const [healthLoading, setHealthLoading] = useState(false)
  const [pickerLoading, setPickerLoading] = useState(false)
  const [tagDraft, setTagDraft] = useState('')
  const [editTagDraft, setEditTagDraft] = useState('')
  const [filterPinnedOnly, setFilterPinnedOnly] = useState(false)
  const [accountPick, setAccountPick] = useState({})
  const [canvasTools, setCanvasTools] = useState([])
  const [accountModal, setAccountModal] = useState(null)

  const workspaceId = selectedWorkspace?.id || null

  useEffect(() => {
    if (!workspaceId) {
      setCanvasTools([])
      return
    }
    let cancelled = false
    authFetch(`/api/workspaces/${workspaceId}/canvas`)
      .then((r) => (r.ok ? r.json() : { tools: [] }))
      .then((data) => {
        if (!cancelled) setCanvasTools(Array.isArray(data.tools) ? data.tools : [])
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [authFetch, workspaceId])

  const saveCanvas = useMemo(
    () =>
      debounce((wsId, tools) => {
        if (!wsId) return
        authFetch(`/api/workspaces/${wsId}/canvas`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ tools }),
        }).catch(() => {})
      }, 800),
    [authFetch]
  )

  useEffect(() => {
    if (!workspaceId) return
    saveCanvas(workspaceId, canvasTools)
  }, [canvasTools, workspaceId, saveCanvas])

  const addToolToCanvas = useCallback((toolId, account, x, y) => {
    setCanvasTools((prev) => [
      ...prev,
      {
        tool_id: toolId,
        account_alias: account.account_alias,
        account_name: account.account_name,
        status: account.status,
        x,
        y,
      },
    ])
  }, [])

  const handleToolDrop = useCallback(
    (toolId, x, y) => {
      if (!workspaceId) return
      authFetch(`/api/workspaces/${workspaceId}/tools/${toolId}/accounts`)
        .then((r) => (r.ok ? r.json() : []))
        .then((accounts) => {
          const list = Array.isArray(accounts) ? accounts : []
          if (list.length === 1) {
            addToolToCanvas(toolId, list[0], x, y)
          } else if (list.length > 1) {
            setAccountModal({ toolId, x, y })
          } else {
            addToolToCanvas(
              toolId,
              {
                account_alias: 'default',
                account_name: 'Not configured',
                status: 'disconnected',
              },
              x,
              y
            )
          }
        })
        .catch(() => {
          addToolToCanvas(
            toolId,
            {
              account_alias: 'default',
              account_name: 'Not configured',
              status: 'disconnected',
            },
            x,
            y
          )
        })
    },
    [authFetch, workspaceId, addToolToCanvas]
  )

  const onCanvasDragOver = useCallback((e) => {
    e.preventDefault()
    if (e.dataTransfer) e.dataTransfer.dropEffect = 'copy'
  }, [])

  const onCanvasDrop = useCallback(
    (e) => {
      e.preventDefault()
      const toolId = e.dataTransfer?.getData('application/x-tool-id') || e.dataTransfer?.getData('text/plain')
      if (!toolId) return
      const rect = canvasRef.current?.getBoundingClientRect()
      const x = rect ? Math.max(0, e.clientX - rect.left - 112) : 0
      const y = rect ? Math.max(0, e.clientY - rect.top - 40) : 0
      handleToolDrop(toolId, x, y)
    },
    [handleToolDrop]
  )

  const loadWorkspaces = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await authFetch('/api/workspaces')
      if (!res.ok) throw new Error(await res.text())
      setWorkspaces(await res.json())
    } catch (e) {
      showToast(`Failed to load workspaces: ${e.message}`, 'error')
      setWorkspaces([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch, showToast])

  useEffect(() => {
    void loadWorkspaces()
  }, [loadWorkspaces])

  const loadWorkspaceDetail = useCallback(
    async (id) => {
      try {
        const res = await authFetch(`/api/workspaces/${id}`)
        if (!res.ok) throw new Error(await res.text())
        const detail = await res.json()
        setSelectedWorkspace(detail)
        setDragOrder((detail.tools || []).map((t) => t.id))
        return detail
      } catch (e) {
        showToast(e.message || 'Failed to load workspace', 'error')
        return null
      }
    },
    [authFetch, showToast]
  )

  const loadHealth = useCallback(
    async (id) => {
      setHealthLoading(true)
      try {
        const res = await authFetch(`/api/workspaces/${id}/health`)
        if (!res.ok) throw new Error(await res.text())
        setHealth(await res.json())
      } catch {
        setHealth(null)
      } finally {
        setHealthLoading(false)
      }
    },
    [authFetch]
  )

  useEffect(() => {
    if (view === 'detail' && selectedWorkspace?.id) {
      void loadHealth(selectedWorkspace.id)
    } else {
      setHealth(null)
    }
  }, [view, selectedWorkspace?.id, loadHealth])

  const filteredWorkspaces = useMemo(() => {
    return workspaces.filter((w) => matchesSearch(w, searchQuery))
  }, [workspaces, searchQuery])

  const pinnedWs = useMemo(
    () => filteredWorkspaces.filter((w) => w.is_pinned),
    [filteredWorkspaces]
  )
  const restWs = useMemo(() => {
    let rest = filteredWorkspaces.filter((w) => !w.is_pinned)
    if (filterPinnedOnly) rest = []
    return rest
  }, [filteredWorkspaces, filterPinnedOnly])

  const orderedTools = useMemo(() => {
    const tools = selectedWorkspace?.tools || []
    if (!dragOrder.length) return tools
    const map = new Map(tools.map((t) => [t.id, t]))
    return dragOrder.map((id) => map.get(id)).filter(Boolean)
  }, [selectedWorkspace?.tools, dragOrder])

  const healthSummary = useMemo(() => {
    if (!health?.tool_statuses) return { healthy: 0, degraded: 0, unknown: 0 }
    let healthy = 0
    let degraded = 0
    let unknown = 0
    for (const row of health.tool_statuses) {
      if (row.status === 'connected') healthy += 1
      else if (row.status === 'failed') degraded += 1
      else unknown += 1
    }
    return { healthy, degraded, unknown }
  }, [health])

  const openCreate = useCallback(() => {
    setCreateForm(emptyForm())
    setTagDraft('')
    setView('create')
  }, [])

  useEffect(() => {
    if (searchParams.get('view') !== 'workspaces' || searchParams.get('create') !== 'true') return
    openCreate()
    const next = new URLSearchParams(searchParams)
    next.delete('create')
    setSearchParams(next, { replace: true })
  }, [searchParams, setSearchParams, openCreate])

  useEffect(() => {
    const wsId = searchParams.get('ws')
    if (!wsId || searchParams.get('view') !== 'workspaces') return
    void loadWorkspaceDetail(wsId).then((d) => {
      const next = new URLSearchParams(searchParams)
      next.delete('ws')
      setSearchParams(next, { replace: true })
      if (d) {
        setSelectedWorkspace(d)
        setView('detail')
      }
    })
  }, [searchParams, setSearchParams, loadWorkspaceDetail])

  const activateWorkspace = useCallback(
    async (w) => {
      await setActiveWorkspace(w)
      await refetchPinnedWorkspaces()
      const tc = w.tool_count ?? (Array.isArray(w.tools) ? w.tools.length : 0)
      const env = w.environment || 'production'
      showToast(`✅ Workspace activated — ${tc} tools loaded for ${env}`, 'success')
    },
    [setActiveWorkspace, refetchPinnedWorkspaces, showToast]
  )

  const populateEditFromWorkspace = useCallback((d) => {
    setEditForm({
      name: d.name,
      description: d.description || '',
      icon: d.icon || '🗂️',
      color: d.color || '#6366f1',
      environment: d.environment || 'production',
      tags: Array.isArray(d.tags) ? [...d.tags] : [],
      is_pinned: !!d.is_pinned,
    })
    setEditTagDraft('')
  }, [])
  const saveCreate = async () => {
    if (!createForm.name.trim()) {
      showToast('Workspace name is required', 'warning')
      return
    }
    try {
      const res = await authFetch('/api/workspaces', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createForm.name.trim(),
          description: createForm.description || '',
          icon: createForm.icon,
          color: createForm.color,
          environment: createForm.environment,
          tags: createForm.tags,
          is_pinned: createForm.is_pinned,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const created = await res.json()
      showToast('Workspace created', 'success')
      await loadWorkspaces()
      const detail = await loadWorkspaceDetail(created.id)
      if (detail) {
        setSelectedWorkspace(detail)
        setView('detail')
      }
    } catch (e) {
      showToast(e.message || 'Save failed', 'error')
    }
  }

  const saveEdit = async () => {
    if (!selectedWorkspace?.id || !editForm.name.trim()) {
      showToast('Workspace name is required', 'warning')
      return
    }
    try {
      const res = await authFetch(`/api/workspaces/${selectedWorkspace.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: editForm.name.trim(),
          description: editForm.description || '',
          icon: editForm.icon,
          color: editForm.color,
          environment: editForm.environment,
          tags: editForm.tags,
          is_pinned: editForm.is_pinned,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const updated = await res.json()
      showToast('Workspace updated', 'success')
      await loadWorkspaces()
      const detail = await loadWorkspaceDetail(updated.id)
      if (detail) {
        setSelectedWorkspace(detail)
        setView('detail')
      }
    } catch (e) {
      showToast(e.message || 'Update failed', 'error')
    }
  }

  const togglePin = async (ws) => {
    try {
      const res = await authFetch(`/api/workspaces/${ws.id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_pinned: !ws.is_pinned }),
      })
      if (!res.ok) throw new Error(await res.text())
      await loadWorkspaces()
      if (selectedWorkspace?.id === ws.id) {
        const detail = await loadWorkspaceDetail(ws.id)
        if (detail) setSelectedWorkspace(detail)
      }
      showToast('Pin updated', 'success')
    } catch (e) {
      showToast(e.message || 'Pin failed', 'error')
    }
  }

  const duplicateWs = async (ws) => {
    try {
      const res = await authFetch(`/api/workspaces/${ws.id}/duplicate`, { method: 'POST' })
      if (!res.ok) throw new Error(await res.text())
      const dup = await res.json()
      showToast('Workspace duplicated', 'success')
      await loadWorkspaces()
      const detail = await loadWorkspaceDetail(dup.id)
      if (detail) {
        setSelectedWorkspace(detail)
        setView('detail')
      }
    } catch (e) {
      showToast(e.message || 'Duplicate failed', 'error')
    }
  }

  const deleteWs = async (ws) => {
    if (!window.confirm(`Delete workspace "${ws.name}"? This cannot be undone.`)) return
    try {
      const res = await authFetch(`/api/workspaces/${ws.id}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      showToast('Workspace deleted', 'success')
      setSelectedWorkspace(null)
      setView('list')
      await loadWorkspaces()
    } catch (e) {
      showToast(e.message || 'Delete failed', 'error')
    }
  }

  const removeTool = async (toolId) => {
    if (!selectedWorkspace?.id) return
    try {
      const res = await authFetch(`/api/workspaces/${selectedWorkspace.id}/tools/${toolId}`, {
        method: 'DELETE',
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Tool removed', 'success')
      await loadWorkspaceDetail(selectedWorkspace.id)
    } catch (e) {
      showToast(e.message || 'Remove failed', 'error')
    }
  }

  const persistReorder = async (nextOrder) => {
    if (!selectedWorkspace?.id) return
    try {
      const res = await authFetch(`/api/workspaces/${selectedWorkspace.id}/tools/reorder`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tool_ids: nextOrder }),
      })
      if (!res.ok) throw new Error(await res.text())
      await loadWorkspaceDetail(selectedWorkspace.id)
    } catch (e) {
      showToast(e.message || 'Reorder failed', 'error')
    }
  }

  const onDragStart = (index) => setDragFromIndex(index)
  const onDragOver = (e) => e.preventDefault()
  const onDrop = async (toIndex) => {
    if (dragFromIndex === null || dragFromIndex === toIndex) {
      setDragFromIndex(null)
      return
    }
    const order = [...dragOrder]
    const [moved] = order.splice(dragFromIndex, 1)
    order.splice(toIndex, 0, moved)
    setDragOrder(order)
    setDragFromIndex(null)
    await persistReorder(order)
  }

  const openToolPicker = async () => {
    setToolPickerOpen(true)
    setToolSearchQuery('')
    setAccountPick({})
    setPickerLoading(true)
    try {
      const res = await authFetch('/api/tools')
      if (!res.ok) throw new Error(await res.text())
      const grouped = await res.json()
      const flat = flattenGroupedTools(grouped)
      const enriched = await Promise.all(
        flat.map(async (t) => {
          const ar = await authFetch(`/api/tools/${t.id}/accounts`)
          const list = ar.ok ? await ar.json() : []
          const accounts = list.filter((a) => a.is_active)
          return { ...t, accounts }
        })
      )
      setAvailableTools(enriched)
    } catch (e) {
      showToast(e.message || 'Failed to load tools', 'error')
      setAvailableTools([])
    } finally {
      setPickerLoading(false)
    }
  }

  const addToolFromPicker = async (toolId, accountId) => {
    if (!selectedWorkspace?.id) return
    const aid = accountId || null
    try {
      const res = await authFetch(`/api/workspaces/${selectedWorkspace.id}/tools`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_id: toolId,
          account_id: aid || undefined,
          display_order: (selectedWorkspace.tools || []).length,
          is_primary: false,
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      const body = await res.json()
      if (body.already_exists) {
        showToast('Already in workspace', 'warning')
      } else {
        showToast('Tool added', 'success')
      }
      await loadWorkspaceDetail(selectedWorkspace.id)
    } catch (e) {
      showToast(e.message || 'Add failed', 'error')
    }
  }

  const filteredPickerTools = useMemo(() => {
    const q = toolSearchQuery.toLowerCase().trim()
    if (!q) return availableTools
    return availableTools.filter(
      (t) =>
        (t.name || '').toLowerCase().includes(q) ||
        (t.category || '').toLowerCase().includes(q)
    )
  }, [availableTools, toolSearchQuery])

  const renderWorkspaceCard = (ws) => (
    <div
      key={ws.id}
      className="group relative rounded-xl border border-border bg-card/40 overflow-hidden hover:border-slate-500/80 transition-colors cursor-pointer flex flex-col min-h-[140px]"
      style={{ borderLeftWidth: 4, borderLeftColor: ws.color || '#6366f1' }}
      role="button"
      tabIndex={0}
      onClick={() => {
        void loadWorkspaceDetail(ws.id).then((d) => {
          if (d) {
            setSelectedWorkspace(d)
            setView('detail')
          }
        })
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          void loadWorkspaceDetail(ws.id).then((d) => {
            if (d) {
              setSelectedWorkspace(d)
              setView('detail')
            }
          })
        }
      }}
    >
      <div className="p-4 flex flex-col flex-1">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <span className="text-2xl shrink-0" aria-hidden>
              {ws.icon || '🗂️'}
            </span>
            <h3 className="font-bold text-white truncate">{ws.name}</h3>
          </div>
          {ws.is_pinned ? (
            <Pin className="w-4 h-4 text-amber-400 shrink-0 fill-current" aria-label="Pinned" />
          ) : (
            <PinOff className="w-4 h-4 text-slate-600 shrink-0 opacity-0 group-hover:opacity-100" aria-hidden />
          )}
        </div>
        <p className="text-sm text-slate-400 mt-2 line-clamp-2 flex-1">{ws.description || '—'}</p>
        <div className="flex items-center justify-between mt-3 text-xs text-slate-500">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={`px-2 py-0.5 rounded-md border text-[10px] font-semibold uppercase ${envBadge(ws.environment)}`}
            >
              {ws.environment}
            </span>
            <span>{ws.tool_count ?? 0} tools</span>
          </div>
          <span className="inline-flex items-center gap-1">
            <Users className="w-3.5 h-3.5" />
            {ws.member_count ?? 0}
          </span>
        </div>
        <div className="flex flex-wrap gap-1 mt-2">
          {(ws.tags || []).slice(0, 4).map((tag) => (
            <span
              key={tag}
              className="px-1.5 py-0.5 rounded bg-slate-800 text-[10px] text-slate-400"
            >
              {tag}
            </span>
          ))}
        </div>
      </div>
      <div className="absolute inset-x-0 bottom-0 p-2 bg-slate-950/90 border-t border-border opacity-0 group-hover:opacity-100 transition-opacity flex flex-wrap gap-1 justify-end">
        <button
          type="button"
          className="px-2 py-1 rounded-md bg-blue-600/90 text-white text-xs font-semibold"
          onClick={(e) => {
            e.stopPropagation()
            void loadWorkspaceDetail(ws.id).then((d) => {
              if (d) {
                setSelectedWorkspace(d)
                setView('detail')
              }
            })
          }}
        >
          🚀 Open
        </button>
        <button
          type="button"
          className="px-2 py-1 rounded-md bg-slate-700 text-xs text-white"
          onClick={(e) => {
            e.stopPropagation()
            void loadWorkspaceDetail(ws.id).then((d) => {
              if (!d) return
              setSelectedWorkspace(d)
              populateEditFromWorkspace(d)
              setView('edit')
            })
          }}
        >
          ✏️ Edit
        </button>
        <button
          type="button"
          className="px-2 py-1 rounded-md bg-slate-700 text-xs text-white"
          onClick={(e) => {
            e.stopPropagation()
            void duplicateWs(ws)
          }}
        >
          📋 Copy
        </button>
        <PermissionGate resource="workspaces" action="delete">
          <button
            type="button"
            className="px-2 py-1 rounded-md bg-red-900/80 text-xs text-red-100"
            onClick={(e) => {
              e.stopPropagation()
              void deleteWs(ws)
            }}
          >
            🗑️ Delete
          </button>
        </PermissionGate>
      </div>
    </div>
  )

  const renderTagInput = (form, setForm, draft, setDraft) => (
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

  const renderForm = (isEdit) => {
    const form = isEdit ? editForm : createForm
    const setForm = isEdit ? setEditForm : setCreateForm
    const draft = isEdit ? editTagDraft : tagDraft
    const setDraft = isEdit ? setEditTagDraft : setTagDraft

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
        {renderTagInput(form, setForm, draft, setDraft)}
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
            onClick={() => {
              if (isEdit && selectedWorkspace) {
                setView('detail')
              } else {
                setView('list')
              }
            }}
            className="px-4 py-2 rounded-lg border border-border text-slate-300 hover:bg-slate-800"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void (isEdit ? saveEdit() : saveCreate())}
            className="px-6 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
          >
            Save Workspace
          </button>
        </div>
      </div>
    )
  }

  if (view === 'create') {
    return (
      <div className="max-w-5xl mx-auto w-full">
        <nav className="text-xs text-slate-500 mb-6 flex items-center gap-1">
          <button type="button" className="hover:text-blue-400" onClick={() => setView('list')}>
            Workspaces
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300">Create</span>
        </nav>
        {renderForm(false)}
      </div>
    )
  }

  if (view === 'edit' && selectedWorkspace) {
    return (
      <div className="max-w-5xl mx-auto w-full">
        <nav className="text-xs text-slate-500 mb-6 flex items-center gap-1 flex-wrap">
          <button type="button" className="hover:text-blue-400" onClick={() => setView('list')}>
            Workspaces
          </button>
          <ChevronRight className="w-3 h-3" />
          <button
            type="button"
            className="hover:text-blue-400 truncate max-w-[180px]"
            onClick={() => setView('detail')}
          >
            {selectedWorkspace.name}
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300">Edit</span>
        </nav>
        {renderForm(true)}
      </div>
    )
  }

  if (view === 'detail' && selectedWorkspace) {
    const ws = selectedWorkspace
    return (
      <div className="max-w-5xl mx-auto w-full space-y-8 pb-16">
        <nav className="text-xs text-slate-500 flex items-center gap-1 flex-wrap">
          <button type="button" className="hover:text-blue-400" onClick={() => setView('list')}>
            Workspaces
          </button>
          <ChevronRight className="w-3 h-3" />
          <span className="text-slate-300 font-medium">{ws.name}</span>
        </nav>

        <div className="flex flex-col lg:flex-row lg:items-start justify-between gap-6">
          <div className="flex gap-4 min-w-0">
            <span className="text-5xl shrink-0">{ws.icon}</span>
            <div className="min-w-0">
              <h1 className="text-2xl font-bold text-white">{ws.name}</h1>
              <p className="text-slate-400 mt-1">{ws.description || '—'}</p>
              <div className="flex flex-wrap gap-2 mt-3">
                {(ws.tags || []).map((tag) => (
                  <span
                    key={tag}
                    className="px-2 py-0.5 rounded-md text-xs font-medium border"
                    style={{
                      borderColor: `${ws.color}55`,
                      backgroundColor: `${ws.color}18`,
                      color: '#e2e8f0',
                    }}
                  >
                    {tag}
                  </span>
                ))}
              </div>
            </div>
          </div>
          <div className="flex flex-wrap gap-2 shrink-0">
            <button
              type="button"
              onClick={() => void togglePin(ws)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 border border-border text-sm text-white"
            >
              {ws.is_pinned ? <PinOff className="w-4 h-4" /> : <Pin className="w-4 h-4" />}
              {ws.is_pinned ? 'Unpin' : 'Pin'}
            </button>
            <button
              type="button"
              onClick={() => {
                populateEditFromWorkspace(ws)
                setView('edit')
              }}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 border border-border text-sm text-white"
            >
              <Edit2 className="w-4 h-4" /> Edit
            </button>
            <button
              type="button"
              onClick={() => void duplicateWs(ws)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-slate-800 border border-border text-sm text-white"
            >
              <Copy className="w-4 h-4" /> Duplicate
            </button>
            <button
              type="button"
              onClick={() => void activateWorkspace(ws)}
              className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-blue-600 border border-blue-500/40 text-sm text-white font-semibold hover:bg-blue-500"
            >
              <Zap className="w-4 h-4" /> Activate Workspace
            </button>
            <PermissionGate resource="workspaces" action="delete">
              <button
                type="button"
                onClick={() => void deleteWs(ws)}
                className="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg bg-red-950/50 border border-red-800 text-sm text-red-200"
              >
                <Trash2 className="w-4 h-4" /> Delete
              </button>
            </PermissionGate>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-slate-900/50 px-4 py-3 flex flex-wrap items-center gap-6 text-sm">
          <Activity className="w-4 h-4 text-slate-500 shrink-0" />
          {healthLoading ? (
            <span className="text-slate-400">Loading health…</span>
          ) : (
            <>
              <span className="inline-flex items-center gap-2 text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-500" />
                {healthSummary.healthy} healthy
              </span>
              <span className="inline-flex items-center gap-2 text-amber-400">
                <span className="w-2 h-2 rounded-full bg-amber-500" />
                {healthSummary.degraded} degraded
              </span>
              <span className="inline-flex items-center gap-2 text-slate-400">
                <span className="w-2 h-2 rounded-full bg-slate-500" />
                {healthSummary.unknown} unknown
              </span>
              <button
                type="button"
                onClick={() => void loadHealth(ws.id)}
                className="ml-auto inline-flex items-center gap-1 text-xs text-blue-400 hover:text-blue-300"
              >
                <RefreshCw className="w-3.5 h-3.5" /> Refresh
              </button>
            </>
          )}
        </div>

        <section>
          <div className="flex items-center justify-between gap-4 mb-4">
            <h2 className="text-lg font-semibold text-white">Tools in this workspace</h2>
            <button
              type="button"
              onClick={() => void openToolPicker()}
              className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold"
            >
              <Plus className="w-4 h-4" /> Add Tool
            </button>
          </div>

          {orderedTools.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border py-12 text-center text-slate-400">
              No tools added yet — click + Add Tool
            </div>
          ) : (
            <ul className="space-y-2">
              {orderedTools.map((row, index) => (
                <li
                  key={row.id}
                  draggable
                  onDragStart={() => onDragStart(index)}
                  onDragOver={onDragOver}
                  onDrop={() => void onDrop(index)}
                  className="group flex items-center gap-3 rounded-xl border border-border bg-card/30 px-3 py-3 hover:bg-slate-900/40"
                >
                  <GripVertical className="w-5 h-5 text-slate-600 shrink-0 cursor-grab active:cursor-grabbing" />
                  <span className="text-xl">{row.tool_icon || '🔧'}</span>
                  <div className="flex-1 min-w-0">
                    <div className="font-medium text-white truncate">{row.tool_name}</div>
                    <div className="text-xs text-slate-500 truncate">
                      {row.account_name || 'Default account context'}
                    </div>
                  </div>
                  <span
                    className={`text-[10px] px-2 py-0.5 rounded-md border uppercase font-semibold ${envBadge(row.account_environment || ws.environment)}`}
                  >
                    {row.account_environment || ws.environment}
                  </span>
                  <span
                    className={`w-2.5 h-2.5 rounded-full shrink-0 ${statusDotClass(row.account_status)}`}
                    title={row.account_status || 'unknown'}
                  />
                  {row.is_primary ? (
                    <span className="text-[10px] font-bold uppercase text-amber-400 border border-amber-500/40 px-2 py-0.5 rounded">
                      Primary
                    </span>
                  ) : null}
                  <button
                    type="button"
                    onClick={() => void removeTool(row.tool_id)}
                    className="opacity-0 group-hover:opacity-100 p-2 rounded-lg hover:bg-red-950/50 text-red-400 transition-opacity"
                    aria-label="Remove tool"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section>
          <div className="flex items-center justify-between gap-4 mb-4">
            <div>
              <h2 className="text-lg font-semibold text-white">Workspace Canvas</h2>
              <p className="text-xs text-slate-500 mt-1">
                Drop tools from the picker to place them on the canvas. State auto-saves.
              </p>
            </div>
            {canvasTools.length > 0 && (
              <button
                type="button"
                onClick={() => setCanvasTools([])}
                className="text-xs text-slate-400 hover:text-red-400"
              >
                Clear canvas
              </button>
            )}
          </div>
          <div
            ref={canvasRef}
            onDragOver={onCanvasDragOver}
            onDrop={onCanvasDrop}
            className="hidden md:block relative w-full min-h-[420px] rounded-xl border border-dashed border-slate-700 bg-slate-950/40 overflow-hidden"
          >
            {canvasTools.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-slate-500 text-sm pointer-events-none">
                Drop a tool from the picker here
              </div>
            )}
            {canvasTools.map((tool, idx) => (
              <div
                key={`${tool.tool_id}-${tool.account_alias}-${idx}`}
                style={{ position: 'absolute', left: tool.x, top: tool.y }}
              >
                <ToolCard
                  tool={tool}
                  onSwitchAccount={() =>
                    setAccountModal({ toolId: tool.tool_id, replaceIdx: idx })
                  }
                  onRunAgent={() => {
                    toast?.info?.(`Opening agent runner for ${tool.tool_id} (${tool.account_alias})`)
                    navigate(
                      `/agents?tool=${encodeURIComponent(tool.tool_id)}&account=${encodeURIComponent(
                        tool.account_alias
                      )}`
                    )
                  }}
                  onRemove={() =>
                    setCanvasTools((prev) => prev.filter((_, i) => i !== idx))
                  }
                />
              </div>
            ))}
          </div>

          <div className="md:hidden space-y-3 p-4">
            <p className="text-xs text-slate-400 text-center">
              Canvas view available on desktop. Tool list below:
            </p>
            {canvasTools.map((tool, idx) => (
              <div
                key={`${tool.tool_id}-${tool.account_alias}-${idx}`}
                className="p-3 bg-slate-800 rounded-xl border border-slate-700"
              >
                <p className="text-sm font-semibold text-white">{tool.tool_id}</p>
                <p className="text-xs text-slate-400">{tool.account_alias}</p>
              </div>
            ))}
          </div>
        </section>

        {accountModal && (
          <AccountSelectorModal
            toolId={accountModal.toolId}
            workspaceId={ws.id}
            onSelect={(acc) => {
              if (accountModal.replaceIdx !== undefined) {
                setCanvasTools((prev) =>
                  prev.map((t, i) =>
                    i === accountModal.replaceIdx
                      ? {
                          ...t,
                          account_alias: acc.account_alias,
                          account_name: acc.account_name,
                          status: acc.status,
                        }
                      : t
                  )
                )
              } else {
                addToolToCanvas(
                  accountModal.toolId,
                  acc,
                  accountModal.x ?? 100,
                  accountModal.y ?? 100
                )
              }
              setAccountModal(null)
            }}
            onClose={() => setAccountModal(null)}
          />
        )}

        {toolPickerOpen && (
          <div
            className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
            role="dialog"
            aria-modal="true"
            aria-labelledby="tool-picker-title"
            onClick={() => setToolPickerOpen(false)}
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
                  onClick={() => setToolPickerOpen(false)}
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
              <div className="px-4 py-3 border-b border-border">
                <div className="relative">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                  <input
                    value={toolSearchQuery}
                    onChange={(e) => setToolSearchQuery(e.target.value)}
                    placeholder="Search tools…"
                    className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
                  />
                </div>
              </div>
              <div className="overflow-y-auto flex-1 p-2">
                {pickerLoading ? (
                  <p className="text-center text-slate-400 py-8">Loading tools…</p>
                ) : (
                  filteredPickerTools.map((t) => {
                    const pickKey = t.id
                    const selAcc =
                      accountPick[pickKey] !== undefined
                        ? accountPick[pickKey]
                        : t.accounts?.length === 1
                          ? t.accounts[0].id
                          : ''
                    const added = isToolAdded(ws.tools, t.id, selAcc || null)
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
                              setAccountPick((prev) => ({ ...prev, [pickKey]: e.target.value }))
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
                              onClick={() =>
                                void addToolFromPicker(t.id, selAcc || null)
                              }
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
        )}
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto w-full space-y-10 pb-16">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight">Workspaces</h1>
          <p className="text-sm text-slate-400 mt-1">
            Saved tool collections for quick context switching
          </p>
        </div>
        <PermissionGate resource="workspaces" action="create">
          <button
            type="button"
            onClick={openCreate}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold shrink-0"
          >
            <Plus className="w-5 h-5" /> New Workspace
          </button>
        </PermissionGate>
      </div>

      <div className="flex flex-col sm:flex-row gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
          <input
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search workspaces…"
            className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
          />
        </div>
        <button
          type="button"
          onClick={() => setFilterPinnedOnly((v) => !v)}
          className={`inline-flex items-center gap-2 px-3 py-2 rounded-lg border text-sm font-medium ${
            filterPinnedOnly ? 'border-amber-500/50 bg-amber-500/10 text-amber-200' : 'border-border text-slate-400 hover:bg-slate-800'
          }`}
        >
          <Filter className="w-4 h-4" />
          Pinned only
        </button>
        <button
          type="button"
          onClick={() => void loadWorkspaces()}
          className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-border text-slate-400 hover:bg-slate-800 text-sm"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} /> Refresh
        </button>
      </div>

      {!isLoading && filteredWorkspaces.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 rounded-xl border border-dashed border-border">
          <Layers className="w-14 h-14 text-slate-600 mb-4" />
          <p className="text-slate-400 font-medium">No workspaces yet</p>
          <button
            type="button"
            onClick={openCreate}
            className="mt-4 inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-blue-600 text-white font-semibold text-sm"
          >
            <Plus className="w-4 h-4" /> Create your first workspace
          </button>
        </div>
      ) : filterPinnedOnly ? (
        <section>
          <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-4">
            Pinned workspaces
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {pinnedWs.length ? (
              pinnedWs.map((ws) => renderWorkspaceCard(ws))
            ) : (
              <p className="text-slate-500 text-sm col-span-full">
                No pinned workspaces match your search.
              </p>
            )}
          </div>
        </section>
      ) : (
        <>
          {pinnedWs.length > 0 && (
            <section>
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider mb-4 flex items-center gap-2">
                <Pin className="w-4 h-4 text-amber-400" /> Pinned
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                {pinnedWs.map((ws) => renderWorkspaceCard(ws))}
              </div>
            </section>
          )}

          <section>
            <div className="flex items-center gap-3 mb-4 flex-wrap">
              <h2 className="text-sm font-bold text-slate-300 uppercase tracking-wider">
                All Workspaces
              </h2>
              <div className="flex gap-2 text-slate-600">
                <Shield className="w-4 h-4" title="Security" />
                <DollarSign className="w-4 h-4" title="Cost" />
                <Wrench className="w-4 h-4" title="Ops" />
                <Zap className="w-4 h-4" title="Automation" />
              </div>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {restWs.map((ws) => renderWorkspaceCard(ws))}
            </div>
          </section>
        </>
      )}

      <div className="flex items-center justify-center gap-2 text-[10px] text-slate-600 pt-4 border-t border-border/40">
        <Settings className="w-3 h-3" />
        <span>Workspace settings apply to saved collections only.</span>
        <ExternalLink className="w-3 h-3 opacity-50" />
      </div>
    </div>
  )
}
