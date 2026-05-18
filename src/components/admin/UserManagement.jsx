import { useCallback, useEffect, useMemo, useState } from 'react'
import { Key, Pencil, Plus, Trash2, X } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../ToastNotification'

function RoleBadge({ role }) {
  const isAdmin = role === 'Admin'
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded border ${
        isAdmin
          ? 'bg-violet-500/20 text-violet-300 border-violet-500/40'
          : 'bg-neutral-700/50 text-neutral-300 border-neutral-600'
      }`}
    >
      {role}
    </span>
  )
}

function StatusBadge({ active }) {
  return active ? (
    <span className="text-xs px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
      Active
    </span>
  ) : (
    <span className="text-xs px-2 py-0.5 rounded bg-red-500/20 text-red-300 border border-red-500/40">
      Inactive
    </span>
  )
}

export default function UserManagement() {
  const { authFetch } = useAuth()
  const { toast } = useToast()
  const [users, setUsers] = useState([])
  const [search, setSearch] = useState('')
  const [roleFilter, setRoleFilter] = useState('')
  const [modal, setModal] = useState(null)
  const [permUser, setPermUser] = useState(null)
  const [permissions, setPermissions] = useState([])
  const [agents, setAgents] = useState([])
  const [form, setForm] = useState({})
  const [permForm, setPermForm] = useState({ agent_name: '', permission_level: 'observe' })

  const loadUsers = useCallback(async () => {
    const res = await authFetch('/api/users/')
    if (res.ok) setUsers(await res.json())
  }, [authFetch])

  useEffect(() => {
    loadUsers()
    authFetch('/api/agents/').then((r) => r.ok && r.json().then(setAgents))
  }, [loadUsers, authFetch])

  const filtered = useMemo(() => {
    return users.filter((u) => {
      const q = search.toLowerCase()
      const matchSearch =
        !q || u.username.toLowerCase().includes(q) || (u.email || '').toLowerCase().includes(q)
      const matchRole = !roleFilter || u.role === roleFilter
      return matchSearch && matchRole
    })
  }, [users, search, roleFilter])

  async function openPermissions(user) {
    setPermUser(user)
    const res = await authFetch(`/api/users/${user.id}/permissions`)
    setPermissions(res.ok ? await res.json() : [])
  }

  async function saveUser(e) {
    e.preventDefault()
    if (modal === 'create') {
      const res = await authFetch('/api/users/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      })
      if (res.ok) {
        toast.success('User created')
        setModal(null)
        loadUsers()
      } else {
        const err = await res.json().catch(() => ({}))
        toast.error(err.detail || 'Failed to create user')
      }
    } else if (modal?.id) {
      const res = await authFetch(`/api/users/${modal.id}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          role: form.role,
          is_active: form.is_active,
          email: form.email,
        }),
      })
      if (res.ok) {
        toast.success('User updated')
        setModal(null)
        loadUsers()
      } else {
        toast.error('Failed to update user')
      }
    }
  }

  async function deleteUser(user) {
    if (!window.confirm(`Delete user ${user.username}? This cannot be undone.`)) return
    const res = await authFetch(`/api/users/${user.id}`, { method: 'DELETE' })
    if (res.ok) {
      toast.success('User deleted')
      loadUsers()
    } else {
      const err = await res.json().catch(() => ({}))
      toast.error(err.detail || 'Failed to delete user')
    }
  }

  async function addPermission() {
    if (!permUser || !permForm.agent_name) return
    const res = await authFetch(`/api/users/${permUser.id}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(permForm),
    })
    if (res.ok) {
      toast.success('Permission granted')
      openPermissions(permUser)
      setPermForm({ agent_name: '', permission_level: 'observe' })
    } else {
      toast.error('Failed to grant permission')
    }
  }

  async function removePermission(pid) {
    const res = await authFetch(`/api/users/${permUser.id}/permissions/${pid}`, {
      method: 'DELETE',
    })
    if (res.ok) {
      toast.success('Permission revoked')
      openPermissions(permUser)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap gap-3 items-center justify-between">
        <div className="flex gap-2">
          <input
            type="search"
            placeholder="Search username or email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white w-56"
          />
          <select
            value={roleFilter}
            onChange={(e) => setRoleFilter(e.target.value)}
            className="bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white"
          >
            <option value="">All roles</option>
            <option value="Admin">Admin</option>
            <option value="User">User</option>
          </select>
        </div>
        <button
          type="button"
          onClick={() => {
            setForm({ username: '', email: '', password: '', role: 'User' })
            setModal('create')
          }}
          className="flex items-center gap-2 px-4 py-2 bg-violet-600 hover:bg-violet-500 text-white text-sm rounded-lg"
        >
          <Plus className="w-4 h-4" />
          Create User
        </button>
      </div>

      <div className="rounded-xl border border-neutral-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900 text-neutral-500 text-xs">
            <tr>
              <th className="text-left px-4 py-2">Username</th>
              <th className="text-left px-4 py-2">Email</th>
              <th className="text-left px-4 py-2">Role</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Created</th>
              <th className="text-right px-4 py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((u) => (
              <tr key={u.id} className="border-t border-neutral-800">
                <td className="px-4 py-2 font-medium text-white">{u.username}</td>
                <td className="px-4 py-2 text-neutral-400">{u.email || '—'}</td>
                <td className="px-4 py-2">
                  <RoleBadge role={u.role} />
                </td>
                <td className="px-4 py-2">
                  <StatusBadge active={u.is_active} />
                </td>
                <td className="px-4 py-2 text-neutral-500 text-xs">
                  {u.created_at ? new Date(u.created_at).toLocaleDateString() : '—'}
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex justify-end gap-1">
                    <button
                      type="button"
                      title="Permissions"
                      onClick={() => openPermissions(u)}
                      className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400"
                    >
                      <Key className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      title="Edit"
                      onClick={() => {
                        setForm({
                          role: u.role,
                          is_active: u.is_active,
                          email: u.email,
                        })
                        setModal({ id: u.id, username: u.username })
                      }}
                      className="p-1.5 rounded hover:bg-neutral-800 text-neutral-400"
                    >
                      <Pencil className="w-4 h-4" />
                    </button>
                    <button
                      type="button"
                      title="Delete"
                      onClick={() => deleteUser(u)}
                      className="p-1.5 rounded hover:bg-neutral-800 text-red-400"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {modal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form
            onSubmit={saveUser}
            className="bg-neutral-900 border border-neutral-700 rounded-xl p-6 w-full max-w-md space-y-4"
          >
            <h3 className="text-lg font-semibold text-white">
              {modal === 'create' ? 'Create User' : `Edit ${modal.username}`}
            </h3>
            {modal === 'create' && (
              <>
                <input
                  required
                  placeholder="Username"
                  value={form.username || ''}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  className="w-full bg-neutral-950 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white"
                />
                <input
                  type="password"
                  required
                  placeholder="Password"
                  value={form.password || ''}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full bg-neutral-950 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white"
                />
              </>
            )}
            <input
              type="email"
              placeholder="Email"
              value={form.email || ''}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
              className="w-full bg-neutral-950 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white"
            />
            <select
              value={form.role || 'User'}
              onChange={(e) => setForm({ ...form, role: e.target.value })}
              className="w-full bg-neutral-950 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white"
            >
              <option value="User">User</option>
              <option value="Admin">Admin</option>
            </select>
            {modal !== 'create' && (
              <label className="flex items-center gap-2 text-sm text-neutral-300">
                <input
                  type="checkbox"
                  checked={form.is_active !== false}
                  onChange={(e) => setForm({ ...form, is_active: e.target.checked })}
                />
                Active
              </label>
            )}
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setModal(null)}
                className="px-4 py-2 text-sm text-neutral-400"
              >
                Cancel
              </button>
              <button type="submit" className="px-4 py-2 text-sm bg-violet-600 text-white rounded-lg">
                Save
              </button>
            </div>
          </form>
        </div>
      )}

      {permUser && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
          <div className="w-full max-w-md bg-neutral-900 border-l border-neutral-800 h-full p-6 overflow-auto">
            <div className="flex justify-between items-center mb-4">
              <h3 className="font-semibold text-white">Permissions — {permUser.username}</h3>
              <button type="button" onClick={() => setPermUser(null)} className="text-neutral-500">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex gap-2 mb-4">
              <select
                value={permForm.agent_name}
                onChange={(e) => setPermForm({ ...permForm, agent_name: e.target.value })}
                className="flex-1 bg-neutral-950 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
              >
                <option value="">Select agent…</option>
                {agents.map((a) => (
                  <option key={a.name} value={a.name}>
                    {a.name}
                  </option>
                ))}
              </select>
              <select
                value={permForm.permission_level}
                onChange={(e) => setPermForm({ ...permForm, permission_level: e.target.value })}
                className="bg-neutral-950 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
              >
                <option value="observe">observe</option>
                <option value="execute">execute</option>
                <option value="automate">automate</option>
              </select>
              <button
                type="button"
                onClick={addPermission}
                className="px-3 py-2 bg-violet-600 text-white text-sm rounded-lg"
              >
                Add
              </button>
            </div>
            <ul className="space-y-2">
              {permissions.map((p) => (
                <li
                  key={p.id}
                  className="flex justify-between items-center py-2 border-b border-neutral-800 text-sm"
                >
                  <span>
                    {p.agent_name}{' '}
                    <span className="text-neutral-500">({p.permission_level})</span>
                  </span>
                  <button
                    type="button"
                    onClick={() => removePermission(p.id)}
                    className="text-red-400 text-xs"
                  >
                    Remove
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </div>
  )
}
