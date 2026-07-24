import { Users } from 'lucide-react'

/**
 * Presentational members summary for a workspace.
 * Accepts either an array of member objects or a numeric member_count.
 */
export default function WorkspaceMemberList({ members, memberCount, className = '' }) {
  const list = Array.isArray(members) ? members : []
  const count = list.length > 0 ? list.length : Number(memberCount) || 0

  if (list.length === 0) {
    return (
      <section className={`rounded-xl border border-dashed border-border bg-card/20 px-4 py-6 ${className}`}>
        <div className="flex items-center gap-2 text-slate-300 font-medium text-sm mb-2">
          <Users className="w-4 h-4" />
          Members
        </div>
        <p className="text-sm text-slate-500">
          {count > 0
            ? `${count} member${count === 1 ? '' : 's'} on this workspace`
            : 'No members listed yet'}
        </p>
      </section>
    )
  }

  return (
    <section className={`rounded-xl border border-border bg-card/30 ${className}`}>
      <div className="flex items-center gap-2 px-4 py-3 border-b border-border text-sm font-medium text-white">
        <Users className="w-4 h-4 text-slate-400" />
        Members ({list.length})
      </div>
      <ul className="divide-y divide-border">
        {list.map((m) => (
          <li key={m.id || m.user_id || m.username} className="px-4 py-3 flex items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm text-white truncate">{m.username || m.user_id || m.name || 'Member'}</p>
              {m.role ? <p className="text-xs text-slate-500 capitalize">{m.role}</p> : null}
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
