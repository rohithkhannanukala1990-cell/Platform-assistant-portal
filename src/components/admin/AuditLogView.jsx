import { useCallback, useEffect, useMemo, useState } from 'react'
import { Download, X } from 'lucide-react'
import { useAuth } from '../../contexts/AuthContext'

function StatusBadge({ status }) {
  const s = (status || '').toLowerCase()
  const cls =
    s === 'failed'
      ? 'bg-red-500/20 text-red-300'
      : s === 'pending_approval'
        ? 'bg-amber-500/20 text-amber-300'
        : 'bg-emerald-500/20 text-emerald-300'
  return <span className={`text-xs px-2 py-0.5 rounded ${cls}`}>{status}</span>
}

export default function AuditLogView() {
  const { authFetch } = useAuth()
  const [users, setUsers] = useState([])
  const [filters, setFilters] = useState({
    user_id: '',
    action: '',
    status: '',
    environment: '',
    from_date: '',
    to_date: '',
  })
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ total: 0, results: [] })
  const [drawer, setDrawer] = useState(null)
  const [pollError, setPollError] = useState(null)
  const pageSize = 50

  const queryString = useMemo(() => {
    const p = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    Object.entries(filters).forEach(([k, v]) => {
      if (v) p.set(k, v)
    })
    return p.toString()
  }, [filters, page])

  const load = useCallback(async () => {
    try {
      const res = await authFetch(`/api/audit/?${queryString}`)
      if (!res.ok) {
        setPollError('Connection lost — retrying…')
        return
      }
      setData(await res.json())
      setPollError(null)
    } catch {
      setPollError('Connection lost — retrying…')
    }
  }, [authFetch, queryString])

  useEffect(() => {
    authFetch('/api/users/')
      .then((r) => r.ok && r.json().then(setUsers))
      .catch(() => {
        /* keep empty users list */
      })
  }, [authFetch])

  useEffect(() => {
    void load()
    const t = setInterval(() => {
      void load()
    }, 60000)
    return () => clearInterval(t)
  }, [load])

  function clearFilters() {
    setFilters({
      user_id: '',
      action: '',
      status: '',
      environment: '',
      from_date: '',
      to_date: '',
    })
    setPage(1)
  }

  async function exportCsv() {
    const res = await authFetch(`/api/audit/export?${queryString}`)
    if (!res.ok) return
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'audit_export.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  async function openRow(row) {
    const res = await authFetch(`/api/audit/${row.id}`)
    if (res.ok) setDrawer(await res.json())
  }

  const start = data.total === 0 ? 0 : (page - 1) * pageSize + 1
  const end = Math.min(page * pageSize, data.total)

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <span className={`w-2 h-2 rounded-full ${pollError ? 'bg-amber-500' : 'bg-emerald-500'} animate-pulse`} />
        <span className="text-xs text-neutral-500">
          {pollError || 'Live — refreshes every 60s'}
        </span>
      </div>
      {pollError && (
        <div className="rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-200">
          Reconnecting…
        </div>
      )}

      <div className="flex flex-wrap gap-2 items-end">
        <select
          value={filters.user_id}
          onChange={(e) => {
            setFilters({ ...filters, user_id: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
        >
          <option value="">All users</option>
          {users.map((u) => (
            <option key={u.id} value={u.username}>
              {u.username}
            </option>
          ))}
        </select>
        <input
          placeholder="Action"
          value={filters.action}
          onChange={(e) => {
            setFilters({ ...filters, action: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white w-32"
        />
        <select
          value={filters.status}
          onChange={(e) => {
            setFilters({ ...filters, status: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
        >
          <option value="">All statuses</option>
          <option value="success">success</option>
          <option value="failed">failed</option>
          <option value="pending_approval">pending_approval</option>
        </select>
        <select
          value={filters.environment}
          onChange={(e) => {
            setFilters({ ...filters, environment: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
        >
          <option value="">All environments</option>
          <option value="production">production</option>
          <option value="staging">staging</option>
          <option value="dev">dev</option>
        </select>
        <input
          type="date"
          value={filters.from_date}
          onChange={(e) => {
            setFilters({ ...filters, from_date: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
        />
        <input
          type="date"
          value={filters.to_date}
          onChange={(e) => {
            setFilters({ ...filters, to_date: e.target.value })
            setPage(1)
          }}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-2 py-2 text-sm text-white"
        />
        <button
          type="button"
          onClick={clearFilters}
          className="px-3 py-2 text-sm text-neutral-400 border border-neutral-700 rounded-lg"
        >
          Clear Filters
        </button>
        <button
          type="button"
          onClick={exportCsv}
          className="flex items-center gap-1 px-3 py-2 text-sm bg-violet-600 text-white rounded-lg"
        >
          <Download className="w-4 h-4" />
          Export CSV
        </button>
      </div>

      <div className="rounded-xl border border-neutral-800 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-neutral-900 text-neutral-500 text-xs">
            <tr>
              <th className="text-left px-4 py-2">Timestamp</th>
              <th className="text-left px-4 py-2">User</th>
              <th className="text-left px-4 py-2">Role</th>
              <th className="text-left px-4 py-2">Action</th>
              <th className="text-left px-4 py-2">Resource</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Environment</th>
            </tr>
          </thead>
          <tbody>
            {(data.results || []).map((row) => (
              <tr
                key={row.id}
                onClick={() => openRow(row)}
                className="border-t border-neutral-800 cursor-pointer hover:bg-neutral-900/50"
              >
                <td className="px-4 py-2 text-neutral-400 text-xs">
                  {row.timestamp ? new Date(row.timestamp).toLocaleString() : '—'}
                </td>
                <td className="px-4 py-2">{row.user_id}</td>
                <td className="px-4 py-2 text-neutral-500">{row.role}</td>
                <td className="px-4 py-2">{row.action}</td>
                <td className="px-4 py-2 text-neutral-500 truncate max-w-[120px]">
                  {row.resource_id || row.resource}
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={row.status} />
                </td>
                <td className="px-4 py-2 text-neutral-500">{row.environment || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-neutral-500">
        <span>
          Showing {start}–{end} of {data.total} results
        </span>
        <div className="flex gap-2">
          <button
            type="button"
            disabled={page <= 1}
            onClick={() => setPage((p) => p - 1)}
            className="px-3 py-1 border border-neutral-700 rounded-lg disabled:opacity-40"
          >
            Previous
          </button>
          <button
            type="button"
            disabled={end >= data.total}
            onClick={() => setPage((p) => p + 1)}
            className="px-3 py-1 border border-neutral-700 rounded-lg disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>

      {drawer && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/40">
          <div className="w-full max-w-lg bg-neutral-900 border-l border-neutral-800 h-full p-6 overflow-auto">
            <div className="flex justify-between mb-4">
              <h3 className="font-semibold text-white">Audit #{drawer.id}</h3>
              <button type="button" onClick={() => setDrawer(null)}>
                <X className="w-5 h-5 text-neutral-500" />
              </button>
            </div>
            <pre className="text-xs text-neutral-300 whitespace-pre-wrap font-mono bg-neutral-950 p-4 rounded-lg border border-neutral-800">
              {JSON.stringify(drawer, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  )
}
