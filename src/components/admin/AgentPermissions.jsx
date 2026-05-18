import { useCallback, useEffect, useMemo, useState } from 'react'
import { useAuth } from '../../contexts/AuthContext'
import { useToast } from '../ToastNotification'

const LEVEL_STYLES = {
  observe: 'bg-blue-500/20 text-blue-300 border-blue-500/40',
  execute: 'bg-amber-500/20 text-amber-300 border-amber-500/40',
  automate: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
}

function LevelBadge({ level }) {
  if (!level) {
    return (
      <span className="text-[10px] px-2 py-0.5 rounded border bg-neutral-800 text-neutral-500 border-neutral-700">
        No Access
      </span>
    )
  }
  return (
    <span
      className={`text-[10px] px-2 py-0.5 rounded border ${LEVEL_STYLES[level] || LEVEL_STYLES.observe}`}
    >
      {level}
    </span>
  )
}

export default function AgentPermissions() {
  const { authFetch } = useAuth()
  const { toast } = useToast()
  const [users, setUsers] = useState([])
  const [agents, setAgents] = useState([])
  const [matrix, setMatrix] = useState({})
  const [agentFilter, setAgentFilter] = useState('')
  const [userFilter, setUserFilter] = useState('')
  const [menu, setMenu] = useState(null)

  const load = useCallback(async () => {
    const [uRes, aRes] = await Promise.all([
      authFetch('/api/users/'),
      authFetch('/api/agents/'),
    ])
    const uList = uRes.ok ? await uRes.json() : []
    const aList = aRes.ok ? await aRes.json() : []
    setUsers(uList)
    setAgents(aList)

    const m = {}
    await Promise.all(
      uList.map(async (u) => {
        const pr = await authFetch(`/api/users/${u.id}/permissions`)
        const perms = pr.ok ? await pr.json() : []
        m[u.id] = Object.fromEntries(perms.map((p) => [p.agent_name, p]))
      })
    )
    setMatrix(m)
  }, [authFetch])

  useEffect(() => {
    load()
  }, [load])

  const filteredAgents = useMemo(
    () =>
      agents.filter((a) => !agentFilter || a.name.toLowerCase().includes(agentFilter.toLowerCase())),
    [agents, agentFilter]
  )
  const filteredUsers = useMemo(
    () =>
      users.filter(
        (u) =>
          !userFilter ||
          u.username.toLowerCase().includes(userFilter.toLowerCase())
      ),
    [users, userFilter]
  )

  async function setPermission(userId, agentName, level) {
    const existing = matrix[userId]?.[agentName]
    if (!level) {
      if (existing?.id) {
        const res = await authFetch(`/api/users/${userId}/permissions/${existing.id}`, {
          method: 'DELETE',
        })
        if (res.ok) toast.success('Access removed')
        else toast.error('Failed to remove access')
      }
    } else {
      const res = await authFetch(`/api/users/${userId}/permissions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ agent_name: agentName, permission_level: level }),
      })
      if (res.ok) toast.success('Permission updated')
      else toast.error('Failed to update permission')
    }
    setMenu(null)
    load()
  }

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <input
          placeholder="Filter agent…"
          value={agentFilter}
          onChange={(e) => setAgentFilter(e.target.value)}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white w-48"
        />
        <input
          placeholder="Filter user…"
          value={userFilter}
          onChange={(e) => setUserFilter(e.target.value)}
          className="bg-neutral-900 border border-neutral-700 rounded-lg px-3 py-2 text-sm text-white w-48"
        />
      </div>

      <div className="overflow-auto rounded-xl border border-neutral-800 max-h-[70vh]">
        <table className="text-xs min-w-full">
          <thead className="bg-neutral-900 sticky top-0 z-10">
            <tr>
              <th className="text-left px-3 py-2 text-neutral-500 sticky left-0 bg-neutral-900">
                Agent
              </th>
              {filteredUsers.map((u) => (
                <th key={u.id} className="px-2 py-2 text-neutral-400 font-normal whitespace-nowrap">
                  {u.username}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredAgents.map((a) => (
              <tr key={a.name} className="border-t border-neutral-800">
                <td className="px-3 py-2 text-white sticky left-0 bg-neutral-950 font-medium">
                  {a.name}
                </td>
                {filteredUsers.map((u) => {
                  const perm = matrix[u.id]?.[a.name]
                  const open =
                    menu?.userId === u.id && menu?.agentName === a.name
                  return (
                    <td key={u.id} className="px-2 py-2 text-center relative">
                      <button
                        type="button"
                        onClick={() =>
                          setMenu(open ? null : { userId: u.id, agentName: a.name })
                        }
                        className="hover:bg-neutral-800 rounded p-1"
                      >
                        <LevelBadge level={perm?.permission_level} />
                      </button>
                      {open && (
                        <div className="absolute z-20 top-full left-1/2 -translate-x-1/2 mt-1 bg-neutral-900 border border-neutral-700 rounded-lg shadow-xl py-1 min-w-[120px]">
                          {['observe', 'execute', 'automate', null].map((lvl) => (
                            <button
                              key={String(lvl)}
                              type="button"
                              onClick={() => setPermission(u.id, a.name, lvl)}
                              className="block w-full text-left px-3 py-1.5 text-xs hover:bg-neutral-800 text-neutral-300"
                            >
                              {lvl || 'Remove access'}
                            </button>
                          ))}
                        </div>
                      )}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
