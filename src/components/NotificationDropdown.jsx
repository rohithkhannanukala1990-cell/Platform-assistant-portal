import { useEffect, useRef, useState, useCallback } from 'react'
import {
  Bell, X, CheckCheck, Inbox,
  AlertTriangle, AlertCircle, Info, Zap,
} from 'lucide-react'

const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000'
const API_NOTIFICATIONS = `${API_BASE}/api/notifications`

const TYPE_CONFIG = {
  critical: { icon: AlertTriangle, color: 'text-red-400',    bg: 'bg-red-500/10 border-red-500/30',    dot: 'bg-red-500' },
  warning:  { icon: AlertCircle,   color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30', dot: 'bg-orange-500' },
  info:     { icon: Info,          color: 'text-blue-400',   bg: 'bg-blue-500/10 border-blue-500/30',  dot: 'bg-blue-400' },
  error:    { icon: Zap,           color: 'text-red-500',    bg: 'bg-red-600/10 border-red-600/30',    dot: 'bg-red-600' },
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1)  return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function NotificationDropdown({ onSelectIncident }) {
  const [open, setOpen]           = useState(false)
  const [notifications, setNots]  = useState([])
  const ref                       = useRef(null)

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await fetch(API_NOTIFICATIONS)
      if (res.ok) {
        const data = await res.json()
        setNots(data)
      }
    } catch (_err) { /* backend not running yet */ }
  }, [])

  // Poll every 30 s
  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  // Re-fetch when dropdown opens
  useEffect(() => { if (open) fetchNotifications() }, [open, fetchNotifications])

  // Close on outside click
  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const unread = notifications.filter((n) => !n.is_read).length

  async function markRead(id) {
    try {
      await fetch(`${API_BASE}/${id}/read`, { method: 'PUT' })
      setNots((prev) => prev.map((n) => n.id === id ? { ...n, is_read: true } : n))
    } catch (_err) { /* noop */ }
  }

  async function markAllRead() {
    const unreadOnes = notifications.filter((n) => !n.is_read)
    await Promise.all(unreadOnes.map((n) => fetch(`${API_BASE}/${n.id}/read`, { method: 'PUT' })))
    setNots((prev) => prev.map((n) => ({ ...n, is_read: true })))
  }

  function handleClick(n) {
    if (!n.is_read) markRead(n.id)
    if (n.incident_id && onSelectIncident) {
      onSelectIncident(n.incident_id)
      setOpen(false)
    }
  }

  return (
    <div ref={ref} className="relative">
      {/* Bell button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg hover:bg-card transition-colors group"
        title="Notifications"
      >
        <Bell className="w-4 h-4 text-slate-400 group-hover:text-white transition-colors" />
        {unread > 0 && (
          <span className="absolute top-1 right-1 flex items-center justify-center w-4 h-4 rounded-full bg-red-500 text-[9px] font-bold text-white leading-none">
            {unread > 9 ? '9+' : unread}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 z-50 rounded-xl border border-border bg-surface shadow-2xl overflow-hidden animate-fade-in">

          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-border bg-sidebar">
            <div className="flex items-center gap-2">
              <Bell className="w-3.5 h-3.5 text-accent" />
              <span className="text-sm font-semibold text-white">Notifications</span>
              {unread > 0 && (
                <span className="px-1.5 py-0.5 rounded-full bg-red-500/20 border border-red-500/40 text-red-400 text-[10px] font-bold">
                  {unread} new
                </span>
              )}
            </div>
            <div className="flex items-center gap-1">
              {unread > 0 && (
                <button
                  onClick={markAllRead}
                  className="flex items-center gap-1 px-2 py-1 text-[10px] text-slate-500 hover:text-slate-300 transition-colors"
                  title="Mark all read"
                >
                  <CheckCheck className="w-3 h-3" />All read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="p-1 text-slate-600 hover:text-white transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* List */}
          <div className="overflow-y-auto max-h-96">
            {notifications.length === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-slate-600">
                <Inbox className="w-8 h-8 opacity-30" />
                <p className="text-xs">No notifications yet</p>
              </div>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {notifications.map((n) => {
                  const cfg = TYPE_CONFIG[n.type] ?? TYPE_CONFIG.info
                  const Icon = cfg.icon
                  return (
                    <li key={n.id}>
                      <button
                        onClick={() => handleClick(n)}
                        className={`w-full text-left flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-card/60
                          ${n.is_read ? 'opacity-50' : ''}`}
                      >
                        {/* Unread dot */}
                        <div className="flex flex-col items-center gap-1 shrink-0 pt-0.5">
                          <div className={`w-2 h-2 rounded-full ${n.is_read ? 'bg-transparent' : cfg.dot}`} />
                        </div>
                        {/* Icon */}
                        <div className={`flex items-center justify-center w-7 h-7 rounded-lg border shrink-0 ${cfg.bg}`}>
                          <Icon className={`w-3.5 h-3.5 ${cfg.color}`} strokeWidth={2.5} />
                        </div>
                        {/* Text */}
                        <div className="flex-1 min-w-0">
                          <p className={`text-xs leading-relaxed ${n.is_read ? 'text-slate-500' : 'text-slate-200'}`}>
                            {n.message}
                          </p>
                          <p className="text-[10px] text-slate-600 mt-0.5">{timeAgo(n.timestamp)}</p>
                        </div>
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </div>

          {/* Footer */}
          {notifications.length > 0 && (
            <div className="px-4 py-2.5 border-t border-border bg-sidebar text-center">
              <span className="text-[10px] text-slate-600">
                {notifications.length} total · {unread} unread
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
