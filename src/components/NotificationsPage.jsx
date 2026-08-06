import { useState, useEffect, useCallback } from 'react'
import { Bell, Check, CheckCheck, Trash2 } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

export default function NotificationsPage() {
  const { authFetch } = useAuth()
  const [notifications, setNotifications] = useState([])
  const [loading, setLoading] = useState(true)
  const [filter, setFilter] = useState('all')

  const load = useCallback(async () => {
    setLoading(true)
    try {
      const res = await authFetch('/api/notifications')
      const data = res.ok ? await res.json() : []
      setNotifications(Array.isArray(data) ? data : [])
    } catch {
      setNotifications([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void load()
  }, [load])

  const filtered = filter === 'unread'
    ? notifications.filter(n => !n.read)
    : notifications

  const markAll = async () => {
    const unread = notifications.filter((n) => !n.read)
    await Promise.all(
      unread.map((n) =>
        authFetch(`/api/notifications/${n.id}/read`, { method: 'PUT' }).catch(() => null)
      )
    )
    setNotifications((ns) => ns.map((n) => ({ ...n, read: true })))
  }

  const dismiss = async (id) => {
    try {
      await authFetch(`/api/notifications/${id}/read`, { method: 'PUT' })
    } catch {
      /* local fallback */
    }
    setNotifications((ns) => ns.filter((n) => n.id !== id))
  }

  return (
    <div className="max-w-2xl mx-auto pt-8 px-4">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-3">
          <Bell className="w-6 h-6 text-indigo-400" />
          <h1 className="text-xl font-bold text-white">Notifications</h1>
          {notifications.filter(n => !n.read).length > 0 && (
            <span className="bg-indigo-600 text-white text-xs
                             rounded-full px-2 py-0.5 font-semibold">
              {notifications.filter(n => !n.read).length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <button onClick={() => setFilter(f => f==='all'?'unread':'all')}
            className="text-xs text-slate-400 hover:text-white px-3 py-1
                       rounded border border-slate-700 transition-colors">
            {filter === 'all' ? 'Show Unread' : 'Show All'}
          </button>
          <button onClick={() => void markAll()}
            className="text-xs text-slate-400 hover:text-white px-3 py-1
                       rounded border border-slate-700 transition-colors
                       flex items-center gap-1">
            <CheckCheck className="w-3.5 h-3.5" /> Mark All Read
          </button>
        </div>
      </div>

      {loading && (
        <div className="space-y-3">
          {[1,2,3].map(i => (
            <div key={i} className="h-16 bg-slate-800 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {!loading && filtered.length === 0 && (
        <div className="text-center py-16 text-slate-500">
          <Bell className="w-10 h-10 mx-auto mb-3 opacity-30" />
          <p className="text-sm">No notifications</p>
        </div>
      )}

      {!loading && (
        <ul className="space-y-2">
          {filtered.map(n => (
            <li key={n.id}
                className={`flex items-start gap-3 p-4 rounded-xl border
                  ${n.read
                    ? 'bg-slate-900 border-slate-800 opacity-60'
                    : 'bg-slate-800 border-slate-700'}`}>
              <div className={`w-2 h-2 rounded-full mt-1.5 shrink-0
                ${n.read ? 'bg-slate-600' : 'bg-indigo-400'}`} />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-white">{n.message || n.title || 'Notification'}</p>
                {n.created_at && (
                  <p className="text-xs text-slate-500 mt-1">{n.created_at}</p>
                )}
              </div>
              <button
                type="button"
                onClick={() => void dismiss(n.id)}
                className="p-1.5 text-slate-500 hover:text-white"
                aria-label="Dismiss notification"
              >
                <Trash2 className="w-3.5 h-3.5" />
              </button>
              {!n.read && (
                <Check className="w-3.5 h-3.5 text-slate-600 mt-1" aria-hidden />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
