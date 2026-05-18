import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'

function KpiCard({ label, value, sub }) {
  return (
    <div className="rounded-xl border border-neutral-800 bg-neutral-900/60 p-4">
      <p className="text-xs text-neutral-500 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-semibold text-white mt-1">{value}</p>
      {sub && <p className="text-xs text-neutral-600 mt-1">{sub}</p>}
    </div>
  )
}

function StatusBadge({ status }) {
  const s = (status || 'success').toLowerCase()
  const cls =
    s === 'failed'
      ? 'bg-red-500/20 text-red-300 border-red-500/40'
      : s === 'pending_approval'
        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
        : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
  return (
    <span className={`text-[10px] px-2 py-0.5 rounded border ${cls}`}>{status || 'success'}</span>
  )
}

export default function AdminOverview() {
  const { authFetch } = useAuth()
  const [kpis, setKpis] = useState({})
  const [activity, setActivity] = useState([])
  const [agentHealth, setAgentHealth] = useState([])
  const [loading, setLoading] = useState(true)

  const load = useCallback(async () => {
    try {
      const [usersRes, agentsRes, statsRes, auditRes, approvalsRes] = await Promise.all([
        authFetch('/api/users/'),
        authFetch('/api/agents/'),
        authFetch('/api/audit/stats'),
        authFetch('/api/audit/?page_size=10'),
        authFetch('/api/agents/approvals'),
      ])
      const users = usersRes.ok ? await usersRes.json() : []
      const agents = agentsRes.ok ? await agentsRes.json() : []
      const stats = statsRes.ok ? await statsRes.json() : {}
      const audit = auditRes.ok ? await auditRes.json() : { results: [] }
      const approvals = approvalsRes.ok ? await approvalsRes.json() : []

      setKpis({
        totalUsers: Array.isArray(users) ? users.length : 0,
        activeAgents: Array.isArray(agents) ? agents.length : 0,
        actionsToday: stats.actions_today ?? 0,
        pendingApprovals: Array.isArray(approvals) ? approvals.length : 0,
        failedActions: stats.failed_actions ?? 0,
        approvalRate: stats.approval_rate != null ? `${Math.round(stats.approval_rate * 100)}%` : '—',
      })
      setActivity(audit.results || [])

      const health = await Promise.all(
        (agents || []).map(async (a) => {
          const name = a.name
          try {
            const r = await authFetch(`/api/agents/${encodeURIComponent(name)}`)
            if (!r.ok) return { name, status: 'unknown', time: '—' }
            const meta = await r.json()
            const recent = meta.recent_audit?.[0]
            const runStatus = recent?.event_type?.includes('reject')
              ? 'failed'
              : recent?.event_type?.includes('pending')
                ? 'pending_approval'
                : 'success'
            return {
              name,
              status: runStatus,
              time: recent?.timestamp ? new Date(recent.timestamp).toLocaleString() : '—',
            }
          } catch {
            return { name, status: 'unknown', time: '—' }
          }
        })
      )
      setAgentHealth(health)
    } catch {
      /* ignore */
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    load()
    const t = setInterval(load, 30000)
    return () => clearInterval(t)
  }, [load])

  if (loading) {
    return <p className="text-neutral-500 text-sm">Loading overview…</p>
  }

  return (
    <div className="space-y-8">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
        <KpiCard label="Total Users" value={kpis.totalUsers ?? '—'} />
        <KpiCard label="Active Agents" value={kpis.activeAgents ?? '—'} />
        <KpiCard label="Actions Today" value={kpis.actionsToday ?? '—'} />
        <KpiCard label="Pending Approvals" value={kpis.pendingApprovals ?? '—'} />
        <KpiCard label="Failed Actions" value={kpis.failedActions ?? '—'} />
        <KpiCard label="Approval Rate" value={kpis.approvalRate ?? '—'} />
      </div>

      <section>
        <h2 className="text-sm font-semibold text-neutral-300 mb-3">Recent Activity</h2>
        <div className="rounded-xl border border-neutral-800 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-neutral-900 text-neutral-500 text-xs">
              <tr>
                <th className="text-left px-4 py-2">Time</th>
                <th className="text-left px-4 py-2">User</th>
                <th className="text-left px-4 py-2">Action</th>
                <th className="text-left px-4 py-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {activity.length === 0 ? (
                <tr>
                  <td colSpan={4} className="px-4 py-6 text-neutral-600 text-center">
                    No recent activity
                  </td>
                </tr>
              ) : (
                activity.map((row) => (
                  <tr key={row.id} className="border-t border-neutral-800">
                    <td className="px-4 py-2 text-neutral-400">
                      {row.timestamp ? new Date(row.timestamp).toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-2">{row.user_id || row.actor}</td>
                    <td className="px-4 py-2">{row.action || row.event_type}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={row.status} />
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="text-sm font-semibold text-neutral-300 mb-3">Agent Health</h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          {agentHealth.map((a) => {
            const dot =
              a.status === 'failed'
                ? 'bg-red-500'
                : a.status === 'pending_approval'
                  ? 'bg-amber-500'
                  : 'bg-emerald-500'
            return (
              <div
                key={a.name}
                className="rounded-lg border border-neutral-800 bg-neutral-900/50 p-3"
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${dot}`} />
                  <span className="text-sm font-medium text-white truncate">{a.name}</span>
                </div>
                <p className="text-xs text-neutral-500 mt-2">{a.status}</p>
                <p className="text-[10px] text-neutral-600 mt-1">{a.time}</p>
              </div>
            )
          })}
        </div>
      </section>
    </div>
  )
}
