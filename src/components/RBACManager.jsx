import { useState, useEffect, useCallback, useMemo } from 'react'
import {
  Shield,
  Users,
  Lock,
  Key,
  Plus,
  Edit2,
  Trash2,
  Check,
  X,
  ChevronRight,
  AlertTriangle,
  Eye,
  Settings,
  Crown,
  UserCheck,
  UserX,
  Search,
  Filter,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const MOCK_USERS = [
  { id: 'admin', name: 'Administrator' },
  { id: 'developer1', name: 'Developer One' },
  { id: 'developer2', name: 'Developer Two' },
  { id: 'dataeng1', name: 'Data Engineer' },
]

const ACTION_ORDER = ['read', 'create', 'update', 'delete', 'apply', 'test', 'export', 'manage']

const MATRIX_ROLE_ORDER = ['viewer', 'operator', 'admin', 'superadmin']

function roleVisual(slug) {
  const s = (slug || '').toLowerCase()
  if (s === 'superadmin') return { emoji: '👑', ring: 'ring-amber-500/50 bg-amber-500/10 text-amber-200' }
  if (s === 'admin') return { emoji: '🛡️', ring: 'ring-blue-500/50 bg-blue-500/10 text-blue-200' }
  if (s === 'operator') return { emoji: '⚙️', ring: 'ring-violet-500/50 bg-violet-500/10 text-violet-200' }
  if (s === 'viewer') return { emoji: '👁️', ring: 'ring-slate-500/50 bg-slate-600/30 text-slate-200' }
  return { emoji: '🎭', ring: 'ring-indigo-500/50 bg-indigo-500/10 text-indigo-200' }
}

function resourceTitle(resource) {
  return resource
    .split('_')
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(' ')
}

function emptyCreateForm() {
  return { name: '', description: '', permissions: new Set() }
}

export default function RBACManager() {
  const { authFetch } = useAuth()
  const { role } = useAuth()
  const { showToast } = useToast()
  const isAdmin = role === 'Admin'

  const [activeTab, setActiveTab] = useState('roles')
  const [roles, setRoles] = useState([])
  const [permissions, setPermissions] = useState({})
  const [roleDetailCache, setRoleDetailCache] = useState({})
  const [matrixRoleDetails, setMatrixRoleDetails] = useState({})
  const [expandedRoleId, setExpandedRoleId] = useState(null)
  const [users] = useState(MOCK_USERS)
  const [userRolesMap, setUserRolesMap] = useState({})
  const [workspaces, setWorkspaces] = useState([])
  const [isLoading, setIsLoading] = useState(false)
  const [createRoleModal, setCreateRoleModal] = useState(false)
  const [editRoleModal, setEditRoleModal] = useState(false)
  const [editingRoleId, setEditingRoleId] = useState(null)
  const [assignRoleModal, setAssignRoleModal] = useState({ open: false, userId: null })
  const [assignForm, setAssignForm] = useState({ roleId: '', scope: 'global', workspaceId: '' })
  const [createForm, setCreateForm] = useState(emptyCreateForm)
  const [userSearch, setUserSearch] = useState('')

  const loadRoles = useCallback(async () => {
    setIsLoading(true)
    try {
      const res = await authFetch('/api/rbac/roles')
      if (!res.ok) throw new Error(await res.text())
      setRoles(await res.json())
    } catch (e) {
      showToast(e.message || 'Failed to load roles', 'error')
      setRoles([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch, showToast])

  const loadPermissions = useCallback(async () => {
    try {
      const res = await authFetch('/api/rbac/permissions')
      if (!res.ok) throw new Error(await res.text())
      setPermissions(await res.json())
    } catch (e) {
      showToast(e.message || 'Failed to load permissions', 'error')
      setPermissions({})
    }
  }, [authFetch, showToast])

  const loadWorkspaces = useCallback(async () => {
    try {
      const res = await authFetch('/api/workspaces')
      if (!res.ok) return
      setWorkspaces(await res.json())
    } catch {
      setWorkspaces([])
    }
  }, [authFetch])

  const loadUserAssignments = useCallback(async () => {
    const next = {}
    for (const u of MOCK_USERS) {
      try {
        const res = await authFetch(`/api/rbac/users/${encodeURIComponent(u.id)}/roles`)
        if (res.ok) next[u.id] = await res.json()
      } catch {
        next[u.id] = { assignments: [], effective_permissions: [], role_slugs: [] }
      }
    }
    setUserRolesMap(next)
  }, [authFetch])

  useEffect(() => {
    void loadRoles()
    void loadPermissions()
    void loadWorkspaces()
  }, [loadRoles, loadPermissions, loadWorkspaces])

  useEffect(() => {
    if (activeTab === 'users') void loadUserAssignments()
  }, [activeTab, loadUserAssignments])

  useEffect(() => {
    if (activeTab !== 'permissions' || !roles.length) return
    let cancelled = false
    async function loadMatrix() {
      const ordered = [...roles].sort((a, b) => {
        const ia = MATRIX_ROLE_ORDER.indexOf((a.slug || '').toLowerCase())
        const ib = MATRIX_ROLE_ORDER.indexOf((b.slug || '').toLowerCase())
        if (ia === -1 && ib === -1) return (a.name || '').localeCompare(b.name || '')
        if (ia === -1) return 1
        if (ib === -1) return -1
        return ia - ib
      })
      const details = {}
      await Promise.all(
        ordered.map(async (r) => {
          try {
            const res = await authFetch(`/api/rbac/roles/${encodeURIComponent(r.id)}`)
            if (res.ok && !cancelled) details[r.id] = await res.json()
          } catch {
            /* noop */
          }
        })
      )
      if (!cancelled) setMatrixRoleDetails(details)
    }
    void loadMatrix()
    return () => {
      cancelled = true
    }
  }, [activeTab, roles, authFetch])

  const toggleExpand = async (roleId) => {
    if (expandedRoleId === roleId) {
      setExpandedRoleId(null)
      return
    }
    setExpandedRoleId(roleId)
    try {
      const res = await authFetch(`/api/rbac/roles/${encodeURIComponent(roleId)}`)
      if (res.ok) {
        const data = await res.json()
        setRoleDetailCache((prev) => ({ ...prev, [roleId]: data }))
      }
    } catch {
      /* noop */
    }
  }

  const openCreateModal = () => {
    setCreateForm(emptyCreateForm())
    setCreateRoleModal(true)
  }

  const toggleCreatePermission = (key) => {
    setCreateForm((f) => {
      const next = new Set(f.permissions)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return { ...f, permissions: next }
    })
  }

  const selectAllResource = (resource, select) => {
    const rows = permissions[resource] || []
    setCreateForm((f) => {
      const next = new Set(f.permissions)
      for (const row of rows) {
        const key = `${resource}:${row.action}`
        if (select) next.add(key)
        else next.delete(key)
      }
      return { ...f, permissions: next }
    })
  }

  const submitCreateRole = async () => {
    if (!createForm.name.trim()) {
      showToast('Role name is required', 'warning')
      return
    }
    try {
      const res = await authFetch('/api/rbac/roles', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createForm.name.trim(),
          description: createForm.description || '',
          permissions: Array.from(createForm.permissions),
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Role created', 'success')
      setCreateRoleModal(false)
      setCreateForm(emptyCreateForm())
      setRoleDetailCache({})
      setMatrixRoleDetails({})
      await loadRoles()
    } catch (e) {
      showToast(e.message || 'Create failed', 'error')
    }
  }

  const openEdit = async (r) => {
    if (r.is_system) return
    try {
      const res = await authFetch(`/api/rbac/roles/${encodeURIComponent(r.id)}`)
      if (!res.ok) throw new Error(await res.text())
      const detail = await res.json()
      const keys = new Set((detail.permissions || []).map((p) => `${p.resource}:${p.action}`))
      setCreateForm({
        name: detail.name,
        description: detail.description || '',
        permissions: keys,
      })
      setEditingRoleId(r.id)
      setEditRoleModal(true)
    } catch {
      showToast('Failed to load role', 'error')
    }
  }

  const submitEditRole = async () => {
    if (!editingRoleId) return
    try {
      const res = await authFetch(`/api/rbac/roles/${encodeURIComponent(editingRoleId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: createForm.name.trim(),
          description: createForm.description || '',
          permissions: Array.from(createForm.permissions),
        }),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Role updated', 'success')
      setEditRoleModal(false)
      setEditingRoleId(null)
      setRoleDetailCache({})
      setMatrixRoleDetails({})
      await loadRoles()
    } catch (e) {
      showToast(e.message || 'Update failed', 'error')
    }
  }

  const deleteRole = async (r) => {
    if (r.is_system) return
    if (!window.confirm(`Delete role "${r.name}"?`)) return
    try {
      const res = await authFetch(`/api/rbac/roles/${encodeURIComponent(r.id)}`, { method: 'DELETE' })
      if (!res.ok) throw new Error(await res.text())
      showToast('Role deleted', 'success')
      setRoleDetailCache({})
      setMatrixRoleDetails({})
      await loadRoles()
    } catch (e) {
      showToast(e.message || 'Delete failed', 'error')
    }
  }

  const openAssign = (userId) => {
    setAssignForm({ roleId: '', scope: 'global', workspaceId: '' })
    setAssignRoleModal({ open: true, userId })
  }

  const submitAssign = async () => {
    const uid = assignRoleModal.userId
    if (!uid || !assignForm.roleId) {
      showToast('Select a role', 'warning')
      return
    }
    if (assignForm.scope === 'workspace' && !assignForm.workspaceId) {
      showToast('Select a workspace', 'warning')
      return
    }
    const body = {
      user_id: uid,
      role_id: assignForm.roleId,
      scope_type: assignForm.scope === 'workspace' ? 'workspace' : 'global',
      scope_id: assignForm.scope === 'workspace' ? assignForm.workspaceId : '',
    }
    try {
      const res = await authFetch(`/api/rbac/users/${encodeURIComponent(uid)}/roles`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error(await res.text())
      showToast('Role assigned', 'success')
      setAssignRoleModal({ open: false, userId: null })
      await loadUserAssignments()
      await loadRoles()
    } catch (e) {
      showToast(e.message || 'Assign failed', 'error')
    }
  }

  const removeUserRole = async (userId, roleId) => {
    try {
      const res = await authFetch(
        `/api/rbac/users/${encodeURIComponent(userId)}/roles/${encodeURIComponent(roleId)}`,
        { method: 'DELETE' }
      )
      if (!res.ok) throw new Error(await res.text())
      showToast('Role removed', 'success')
      await loadUserAssignments()
      await loadRoles()
    } catch (e) {
      showToast(e.message || 'Remove failed', 'error')
    }
  }

  const matrixResources = useMemo(() => Object.keys(permissions).sort(), [permissions])

  const matrixColumns = useMemo(() => {
    return [...roles].sort((a, b) => {
      const ia = MATRIX_ROLE_ORDER.indexOf((a.slug || '').toLowerCase())
      const ib = MATRIX_ROLE_ORDER.indexOf((b.slug || '').toLowerCase())
      if (ia === -1 && ib === -1) return (a.name || '').localeCompare(b.name || '')
      if (ia === -1) return 1
      if (ib === -1) return -1
      return ia - ib
    })
  }, [roles])

  const roleHasResourceAccess = (roleId, resource) => {
    const d = matrixRoleDetails[roleId]
    if (!d?.permissions) return false
    return d.permissions.some((p) => p.resource === resource)
  }

  const filteredUsers = useMemo(() => {
    const q = userSearch.trim().toLowerCase()
    if (!q) return users
    return users.filter((u) => u.id.toLowerCase().includes(q) || (u.name || '').toLowerCase().includes(q))
  }, [users, userSearch])

  const renderExpandedPerms = (rid) => {
    const detail = roleDetailCache[rid]
    if (!detail?.permissions?.length) {
      return <p className="text-xs text-slate-500 py-3">Loading permissions…</p>
    }
    const byRes = {}
    for (const p of detail.permissions) {
      if (!byRes[p.resource]) byRes[p.resource] = []
      byRes[p.resource].push(p.action)
    }
    return (
      <div className="mt-4 pl-4 border-l-2 border-slate-600 space-y-4">
        {Object.keys(byRes)
          .sort()
          .map((res) => (
            <div key={res}>
              <p className="text-xs font-bold text-slate-400 uppercase mb-2">{resourceTitle(res)}</p>
              <div className="flex flex-wrap gap-2">
                {[...new Set(byRes[res])]
                  .sort((a, b) => ACTION_ORDER.indexOf(a) - ACTION_ORDER.indexOf(b))
                  .map((a) => (
                    <span
                      key={a}
                      className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md bg-emerald-500/15 text-emerald-200 text-xs border border-emerald-500/30"
                    >
                      <Check className="w-3 h-3" /> {a}
                    </span>
                  ))}
              </div>
            </div>
          ))}
      </div>
    )
  }

  if (!isAdmin) {
    return (
      <div className="max-w-3xl mx-auto py-12 text-center text-slate-400">
        <Lock className="w-12 h-12 mx-auto mb-4 text-slate-600" />
        <p>Access Control is available to administrators only.</p>
      </div>
    )
  }

  return (
    <div className="max-w-6xl mx-auto w-full space-y-8 pb-16">
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white tracking-tight flex items-center gap-2">
            <Shield className="w-7 h-7 text-indigo-400 shrink-0" aria-hidden />
            Roles &amp; Permissions
          </h1>
          <p className="text-sm text-slate-400 mt-1">Control who can access what</p>
        </div>
        {isAdmin ? (
          <button
            type="button"
            onClick={openCreateModal}
            className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-blue-600 hover:bg-blue-500 text-white font-semibold shrink-0"
          >
            <Plus className="w-5 h-5" /> New Role
          </button>
        ) : null}
      </div>

      <div className="flex gap-2 border-b border-border pb-px">
        {[
          { id: 'roles', label: 'Roles', icon: Crown },
          { id: 'permissions', label: 'Matrix', icon: Filter },
          { id: 'users', label: 'User assignments', icon: Users },
        ].map((t) => {
          const Icon = t.icon
          const active = activeTab === t.id
          return (
            <button
              key={t.id}
              type="button"
              onClick={() => setActiveTab(t.id)}
              className={`inline-flex items-center gap-2 px-4 py-2 rounded-t-lg text-sm font-medium border-b-2 -mb-px transition-colors ${
                active
                  ? 'border-blue-500 text-white bg-slate-900/50'
                  : 'border-transparent text-slate-400 hover:text-slate-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              {t.label}
            </button>
          )
        })}
      </div>

      {activeTab === 'roles' && (
        <div className="space-y-4">
          {isLoading && roles.length === 0 ? (
            <p className="text-slate-500 text-sm">Loading roles…</p>
          ) : null}
          {roles.map((r) => {
            const v = roleVisual(r.slug)
            const expanded = expandedRoleId === r.id
            return (
              <div
                key={r.id}
                className="rounded-xl border border-border bg-card/30 overflow-hidden"
              >
                <button
                  type="button"
                  className="w-full flex items-start gap-4 p-4 text-left hover:bg-slate-900/40 transition-colors"
                  onClick={() => void toggleExpand(r.id)}
                >
                  <div
                    className={`w-12 h-12 rounded-xl flex items-center justify-center text-2xl shrink-0 ring-2 ${v.ring}`}
                  >
                    {v.emoji}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-bold text-white">{r.name}</span>
                      {r.is_system ? (
                        <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-300 border border-border">
                          System
                        </span>
                      ) : null}
                    </div>
                    <p className="text-sm text-slate-400 mt-1 line-clamp-2">{r.description || '—'}</p>
                    <div className="flex flex-wrap gap-3 mt-2 text-xs text-slate-500">
                      <span className="inline-flex items-center gap-1">
                        <Key className="w-3.5 h-3.5" /> {r.permission_count ?? 0} permissions
                      </span>
                      <span className="inline-flex items-center gap-1">
                        <Users className="w-3.5 h-3.5" /> {r.user_count ?? 0} users
                      </span>
                    </div>
                  </div>
                  <div className="flex flex-col sm:flex-row gap-2 shrink-0 items-end sm:items-center">
                    <button
                      type="button"
                      className="px-2 py-1 rounded-md bg-slate-800 text-xs text-white inline-flex items-center gap-1"
                      onClick={(e) => {
                        e.stopPropagation()
                        void toggleExpand(r.id)
                      }}
                    >
                      <Eye className="w-3.5 h-3.5" /> View
                    </button>
                    <button
                      type="button"
                      disabled={r.is_system}
                      className="px-2 py-1 rounded-md bg-slate-800 text-xs text-white disabled:opacity-40 inline-flex items-center gap-1"
                      onClick={(e) => {
                        e.stopPropagation()
                        void openEdit(r)
                      }}
                    >
                      <Edit2 className="w-3.5 h-3.5" /> Edit
                    </button>
                    <button
                      type="button"
                      disabled={r.is_system}
                      className="px-2 py-1 rounded-md bg-red-900/40 text-xs text-red-200 disabled:opacity-40 inline-flex items-center gap-1"
                      onClick={(e) => {
                        e.stopPropagation()
                        void deleteRole(r)
                      }}
                    >
                      <Trash2 className="w-3.5 h-3.5" /> Delete
                    </button>
                    <ChevronRight
                      className={`w-5 h-5 text-slate-500 transition-transform ${expanded ? 'rotate-90' : ''}`}
                    />
                  </div>
                </button>
                {expanded && <div className="px-4 pb-4 border-t border-border bg-slate-950/40">{renderExpandedPerms(r.id)}</div>}
              </div>
            )
          })}
        </div>
      )}

      {activeTab === 'permissions' && (
        <div className="overflow-x-auto rounded-xl border border-border">
          <p className="text-xs text-slate-500 px-4 py-2 border-b border-border flex items-center gap-2">
            <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
            Read-only matrix — which roles have any permission on each resource
          </p>
          <table className="w-full text-sm text-left min-w-[640px]">
            <thead>
              <tr className="bg-slate-900/80 text-slate-400 text-xs uppercase">
                <th className="px-4 py-3 font-semibold">Resource</th>
                {matrixColumns.map((col) => (
                  <th key={col.id} className="px-3 py-3 font-semibold text-center whitespace-nowrap">
                    {col.name}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {matrixResources.map((res) => (
                <tr key={res} className="border-t border-border">
                  <td className="px-4 py-2 text-white font-medium">{resourceTitle(res)}</td>
                  {matrixColumns.map((col) => (
                    <td key={`${res}-${col.id}`} className="px-3 py-2 text-center text-lg">
                      {roleHasResourceAccess(col.id, res) ? '✅' : '❌'}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {activeTab === 'users' && (
        <div className="space-y-4">
          <div className="relative max-w-md">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
            <input
              value={userSearch}
              onChange={(e) => setUserSearch(e.target.value)}
              placeholder="Filter by user id or name…"
              className="w-full pl-10 pr-3 py-2 rounded-lg bg-slate-900 border border-border text-sm text-white"
            />
          </div>
          <div className="space-y-3">
            {filteredUsers.map((u) => {
              const pack = userRolesMap[u.id] || { assignments: [] }
              const initials = (u.name || u.id).slice(0, 2).toUpperCase()
              return (
                <div
                  key={u.id}
                  className="rounded-xl border border-border bg-card/30 p-4 flex flex-col lg:flex-row lg:items-center gap-4"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <div className="w-10 h-10 rounded-full bg-indigo-600/40 text-indigo-100 font-bold flex items-center justify-center shrink-0">
                      {initials}
                    </div>
                    <div className="min-w-0">
                      <p className="font-semibold text-white">{u.id}</p>
                      <p className="text-xs text-slate-500">{u.name}</p>
                    </div>
                  </div>
                  <div className="flex-1 flex flex-wrap gap-2 items-center">
                    {(pack.assignments || []).map((a) => {
                      const scopeLabel =
                        a.scope_type === 'workspace' && a.scope_id
                          ? `Workspace: ${workspaces.find((w) => w.id === a.scope_id)?.name || a.scope_id}`
                          : 'Global'
                      return (
                        <span
                          key={a.id}
                          className="group inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full bg-slate-800 border border-border text-xs text-slate-200"
                        >
                          <span>
                            {a.role_name} · {scopeLabel}
                          </span>
                          <button
                            type="button"
                            className="p-0.5 rounded-full hover:bg-red-900/50 text-slate-500 hover:text-red-300 opacity-70 group-hover:opacity-100"
                            title="Remove role"
                            onClick={() => void removeUserRole(u.id, a.role_id)}
                          >
                            <UserX className="w-3.5 h-3.5" />
                          </button>
                        </span>
                      )
                    })}
                    {!(pack.assignments || []).length ? (
                      <span className="text-xs text-slate-600">No RBAC roles assigned</span>
                    ) : null}
                  </div>
                  <button
                    type="button"
                    onClick={() => openAssign(u.id)}
                    className="inline-flex items-center gap-2 px-3 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white text-sm font-semibold shrink-0"
                  >
                    <UserCheck className="w-4 h-4" /> Assign role
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {createRoleModal && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
          role="dialog"
          aria-modal="true"
          onClick={() => setCreateRoleModal(false)}
        >
          <div
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-slate-950 shadow-2xl p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white flex items-center gap-2">
                <Settings className="w-5 h-5 text-indigo-400" />
                New role
              </h2>
              <button type="button" className="p-2 text-slate-400 hover:text-white" onClick={() => setCreateRoleModal(false)}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase mb-1">Role name</label>
                <input
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  placeholder="e.g. Incident lead"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase mb-1">Description</label>
                <textarea
                  value={createForm.description}
                  onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm resize-none"
                />
              </div>
              <p className="text-xs text-slate-500">Select permissions by resource</p>
              <div className="space-y-4 max-h-[45vh] overflow-y-auto pr-1">
                {Object.keys(permissions)
                  .sort()
                  .map((resource) => {
                    const rows = permissions[resource] || []
                    const sorted = [...rows].sort(
                      (a, b) => ACTION_ORDER.indexOf(a.action) - ACTION_ORDER.indexOf(b.action)
                    )
                    return (
                      <div key={resource} className="rounded-lg border border-border/60 p-3 bg-slate-900/40">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-semibold text-white">{resourceTitle(resource)}</span>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              className="text-[10px] text-blue-400 hover:underline"
                              onClick={() => selectAllResource(resource, true)}
                            >
                              Select all
                            </button>
                            <button
                              type="button"
                              className="text-[10px] text-slate-500 hover:underline"
                              onClick={() => selectAllResource(resource, false)}
                            >
                              Clear
                            </button>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {sorted.map((row) => {
                            const key = `${resource}:${row.action}`
                            const on = createForm.permissions.has(key)
                            return (
                              <label
                                key={row.id}
                                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs cursor-pointer ${
                                  on ? 'border-blue-500/60 bg-blue-500/15 text-blue-100' : 'border-border text-slate-400'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="rounded border-slate-600"
                                  checked={on}
                                  onChange={() => toggleCreatePermission(key)}
                                />
                                {row.action}
                              </label>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg border border-border text-slate-300"
                  onClick={() => setCreateRoleModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void submitCreateRole()}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                >
                  Create role
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {editRoleModal && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
          role="dialog"
          aria-modal="true"
          onClick={() => setEditRoleModal(false)}
        >
          <div
            className="w-full max-w-lg max-h-[90vh] overflow-y-auto rounded-xl border border-border bg-slate-950 shadow-2xl p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">Edit role</h2>
              <button type="button" className="p-2 text-slate-400 hover:text-white" onClick={() => setEditRoleModal(false)}>
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="space-y-4">
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase mb-1">Role name</label>
                <input
                  value={createForm.name}
                  onChange={(e) => setCreateForm((f) => ({ ...f, name: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-400 uppercase mb-1">Description</label>
                <textarea
                  value={createForm.description}
                  onChange={(e) => setCreateForm((f) => ({ ...f, description: e.target.value }))}
                  rows={2}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm resize-none"
                />
              </div>
              <div className="space-y-4 max-h-[45vh] overflow-y-auto pr-1">
                {Object.keys(permissions)
                  .sort()
                  .map((resource) => {
                    const rows = permissions[resource] || []
                    const sorted = [...rows].sort(
                      (a, b) => ACTION_ORDER.indexOf(a.action) - ACTION_ORDER.indexOf(b.action)
                    )
                    return (
                      <div key={resource} className="rounded-lg border border-border/60 p-3 bg-slate-900/40">
                        <div className="flex items-center justify-between mb-2">
                          <span className="text-sm font-semibold text-white">{resourceTitle(resource)}</span>
                          <div className="flex gap-2">
                            <button
                              type="button"
                              className="text-[10px] text-blue-400 hover:underline"
                              onClick={() => selectAllResource(resource, true)}
                            >
                              Select all
                            </button>
                            <button
                              type="button"
                              className="text-[10px] text-slate-500 hover:underline"
                              onClick={() => selectAllResource(resource, false)}
                            >
                              Clear
                            </button>
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {sorted.map((row) => {
                            const key = `${resource}:${row.action}`
                            const on = createForm.permissions.has(key)
                            return (
                              <label
                                key={row.id}
                                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded-md border text-xs cursor-pointer ${
                                  on ? 'border-blue-500/60 bg-blue-500/15 text-blue-100' : 'border-border text-slate-400'
                                }`}
                              >
                                <input
                                  type="checkbox"
                                  className="rounded border-slate-600"
                                  checked={on}
                                  onChange={() => toggleCreatePermission(key)}
                                />
                                {row.action}
                              </label>
                            )
                          })}
                        </div>
                      </div>
                    )
                  })}
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  className="px-4 py-2 rounded-lg border border-border text-slate-300"
                  onClick={() => setEditRoleModal(false)}
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={() => void submitEditRole()}
                  className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                >
                  Save changes
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {assignRoleModal.open && assignRoleModal.userId && (
        <div
          className="fixed inset-0 z-[80] flex items-center justify-center p-4 bg-black/70"
          role="dialog"
          aria-modal="true"
          onClick={() => setAssignRoleModal({ open: false, userId: null })}
        >
          <div
            className="w-full max-w-md rounded-xl border border-border bg-slate-950 shadow-2xl p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <h2 className="text-lg font-bold text-white mb-1">Assign role to {assignRoleModal.userId}</h2>
            <p className="text-xs text-slate-500 mb-4">Choose a role and optional workspace scope</p>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-slate-400 mb-1">Role</label>
                <select
                  value={assignForm.roleId}
                  onChange={(e) => setAssignForm((f) => ({ ...f, roleId: e.target.value }))}
                  className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                >
                  <option value="">Select role…</option>
                  {roles.map((r) => (
                    <option key={r.id} value={r.id}>
                      {r.name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="scope"
                    checked={assignForm.scope === 'global'}
                    onChange={() => setAssignForm((f) => ({ ...f, scope: 'global', workspaceId: '' }))}
                  />
                  Global
                </label>
                <label className="flex items-center gap-2 text-sm text-slate-300 cursor-pointer">
                  <input
                    type="radio"
                    name="scope"
                    checked={assignForm.scope === 'workspace'}
                    onChange={() => setAssignForm((f) => ({ ...f, scope: 'workspace' }))}
                  />
                  Workspace-scoped
                </label>
                {assignForm.scope === 'workspace' ? (
                  <select
                    value={assignForm.workspaceId}
                    onChange={(e) => setAssignForm((f) => ({ ...f, workspaceId: e.target.value }))}
                    className="w-full px-3 py-2 rounded-lg bg-slate-900 border border-border text-white text-sm"
                  >
                    <option value="">Select workspace…</option>
                    {workspaces.map((w) => (
                      <option key={w.id} value={w.id}>
                        {w.name}
                      </option>
                    ))}
                  </select>
                ) : null}
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-6">
              <button
                type="button"
                className="px-4 py-2 rounded-lg border border-border text-slate-300"
                onClick={() => setAssignRoleModal({ open: false, userId: null })}
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void submitAssign()}
                className="px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-500 text-white font-semibold"
              >
                Assign
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
