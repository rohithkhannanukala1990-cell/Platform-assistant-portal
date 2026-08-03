import { useEffect, useRef, useState, useCallback } from 'react'
import {
  Bell,
  X,
  CheckCheck,
  Inbox,
  AlertTriangle,
  AlertCircle,
  Info,
  Zap,
  Heart as HeartIcon,
  ShieldCheck,
  ChevronRight,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { API_BASE } from '../config/apiBase'

const API_NOTIFICATIONS = `${API_BASE}/api/notifications`
const API_MARK_READ = (id) => `${API_BASE}/api/notifications/${id}/read`

const TYPE_CONFIG = {
  critical: { icon: AlertTriangle, color: 'text-red-400', bg: 'bg-red-500/10 border-red-500/30', dot: 'bg-red-500' },
  warning: { icon: AlertCircle, color: 'text-orange-400', bg: 'bg-orange-500/10 border-orange-500/30', dot: 'bg-orange-500' },
  info: { icon: Info, color: 'text-blue-400', bg: 'bg-blue-500/10 border-blue-500/30', dot: 'bg-blue-400' },
  error: { icon: Zap, color: 'text-red-500', bg: 'bg-red-600/10 border-red-600/30', dot: 'bg-red-600' },
}

function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime()
  const m = Math.floor(diff / 60000)
  if (m < 1) return 'just now'
  if (m < 60) return `${m}m ago`
  const h = Math.floor(m / 60)
  if (h < 24) return `${h}h ago`
  return `${Math.floor(h / 24)}d ago`
}

export default function NotificationDropdown({
  onSelectIncident,
  onOpenHealthDashboard,
  pendingApprovalCount = 0,
  onOpenApprovals,
}) {
  const { authFetch } = useAuth()
  const [open, setOpen] = useState(false)
  const [notifications, setNots] = useState([])
  const [healthAlerts, setHealthAlerts] = useState([])
  const ref = useRef(null)

  const fetchNotifications = useCallback(async () => {
    try {
      const res = await authFetch(API_NOTIFICATIONS)
      if (res.ok) {
        const data = await res.json()
        setNots(data)
      }
    } catch (_err) {
      /* backend not running */
    }
  }, [authFetch])

  useEffect(() => {
    fetchNotifications()
    const interval = setInterval(fetchNotifications, 30000)
    return () => clearInterval(interval)
  }, [fetchNotifications])

  useEffect(() => {
    if (open) fetchNotifications()
  }, [open, fetchNotifications])

  useEffect(() => {
    function onHealthAlert(ev) {
      const d = ev.detail || {}
      if (d.type && d.type !== 'health_alert') return
      const id = `health-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      setHealthAlerts((prev) =>
        [
          {
            id,
            message: d.message || 'Health alert',
            severity: d.severity || 'info',
            timestamp: d.timestamp || new Date().toISOString(),
            is_read: false,
            _kind: 'health_alert',
          },
          ...prev,
        ].slice(0, 50)
      )
    }
    window.addEventListener('portal-health-alert', onHealthAlert)
    return () => window.removeEventListener('portal-health-alert', onHealthAlert)
  }, [])

  useEffect(() => {
    function handler(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const healthUnread = healthAlerts.filter((h) => !h.is_read).length
  const notifUnread = notifications.filter((n) => !n.is_read).length
  const unread = healthUnread + notifUnread + pendingApprovalCount

  async function markRead(id) {
    try {
      await authFetch(API_MARK_READ(id), { method: 'PUT' })
      setNots((prev) => prev.map((n) => (n.id === id ? { ...n, is_read: true } : n)))
    } catch (_err) {
      /* noop */
    }
  }

  async function markAllRead() {
    const unreadOnes = notifications.filter((n) => !n.is_read)
    await Promise.all(unreadOnes.map((n) => authFetch(API_MARK_READ(n.id), { method: 'PUT' })))
    setNots((prev) => prev.map((n) => ({ ...n, is_read: true })))
    setHealthAlerts((prev) => prev.map((h) => ({ ...h, is_read: true })))
  }

  function handleClick(n) {
    if (!n.is_read) markRead(n.id)
    if (n.incident_id && onSelectIncident) {
      onSelectIncident(n.incident_id)
      setOpen(false)
    }
  }

  const healthPreview = healthAlerts.slice(0, 3)

  return (
    <div ref={ref} className="relative">
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

      {open && (
        <div className="absolute right-0 top-full mt-2 w-96 z-50 rounded-xl border border-border bg-surface shadow-2xl overflow-hidden animate-fade-in">
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
                  <CheckCheck className="w-3 h-3" />
                  All read
                </button>
              )}
              <button onClick={() => setOpen(false)} className="p-1 text-slate-600 hover:text-white transition-colors">
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          <div className="overflow-y-auto max-h-96">
            {pendingApprovalCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  onOpenApprovals?.()
                  setOpen(false)
                }}
                className="w-full flex items-center gap-3 px-4 py-3 border-b border-border bg-amber-500/5 hover:bg-amber-500/10 transition-colors text-left"
              >
                <div className="flex items-center justify-center w-7 h-7 rounded-lg border shrink-0 bg-amber-500/10 border-amber-500/30">
                  <ShieldCheck className="w-3.5 h-3.5 text-amber-400" strokeWidth={2.5} />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold text-amber-300">
                    {pendingApprovalCount} agent {pendingApprovalCount === 1 ? 'run' : 'runs'} awaiting approval
                  </p>
                  <p className="text-[10px] text-slate-500 mt-0.5">Review in the AI Assistant</p>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-600 shrink-0" />
              </button>
            )}
            {healthAlerts.length > 0 && (
              <div className="border-b border-border bg-sidebar/80">
                <div className="flex items-center justify-between px-4 py-2">
                  <span className="text-[10px] font-bold text-slate-500 uppercase tracking-wider">🏥 System Health</span>
                  {onOpenHealthDashboard && (
                    <button
                      type="button"
                      onClick={() => {
                        onOpenHealthDashboard()
                        setOpen(false)
                      }}
                      className="text-[10px] font-semibold text-accent hover:text-accent/80"
                    >
                      View All
                    </button>
                  )}
                </div>
                <ul className="flex flex-col">
                  {healthPreview.map((h) => (
                    <li key={h.id} className="border-t border-border/60">
                      <div
                        className={`w-full text-left flex items-start gap-3 px-4 py-3 transition-colors hover:bg-card/60 ${
                          h.is_read ? 'opacity-50' : ''
                        }`}
                      >
                        <div className="flex flex-col items-center gap-1 shrink-0 pt-0.5">
                          <div className={`w-2 h-2 rounded-full ${h.is_read ? 'bg-transparent' : 'bg-red-500'}`} />
                        </div>
                        <div className="flex items-center justify-center w-7 h-7 rounded-lg border shrink-0 bg-red-500/10 border-red-500/30">
                          <HeartIcon className="w-3.5 h-3.5 text-red-400" strokeWidth={2.5} />
                        </div>
                        <div className="flex-1 min-w-0">
                          <p className="text-[10px] font-semibold text-slate-500 mb-0.5">System Health</p>
                          <p className={`text-xs leading-relaxed ${h.is_read ? 'text-slate-500' : 'text-slate-200'}`}>
                            {h.message}
                          </p>
                          <p className="text-[10px] text-slate-600 mt-0.5">
                            {timeAgo(h.timestamp)} · <span className="capitalize">{h.severity}</span>
                          </p>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              </div>
            )}

            {notifications.length === 0 && healthAlerts.length === 0 && pendingApprovalCount === 0 ? (
              <div className="flex flex-col items-center justify-center gap-2 py-12 text-slate-600">
                <Inbox className="w-8 h-8 opacity-30" />
                <p className="text-xs">No notifications yet</p>
              </div>
            ) : (
              notifications.length > 0 && (
                <ul className="flex flex-col divide-y divide-border">
                  {notifications.map((n) => {
                    const cfg = TYPE_CONFIG[n.type] ?? TYPE_CONFIG.info
                    const Icon = cfg.icon
                    return (
                      <li key={n.id}>
                        <button
                          type="button"
                          onClick={() => handleClick(n)}
                          className={`w-full text-left flex items-start gap-3 px-4 py-3.5 transition-colors hover:bg-card/60 ${
                            n.is_read ? 'opacity-50' : ''
                          }`}
                        >
                          <div className="flex flex-col items-center gap-1 shrink-0 pt-0.5">
                            <div className={`w-2 h-2 rounded-full ${n.is_read ? 'bg-transparent' : cfg.dot}`} />
                          </div>
                          <div className={`flex items-center justify-center w-7 h-7 rounded-lg border shrink-0 ${cfg.bg}`}>
                            <Icon className={`w-3.5 h-3.5 ${cfg.color}`} strokeWidth={2.5} />
                          </div>
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
              )
            )}
          </div>

          {(notifications.length > 0 || healthAlerts.length > 0) && (
            <div className="px-4 py-2.5 border-t border-border bg-sidebar text-center">
              <span className="text-[10px] text-slate-600">
                {notifications.length + healthAlerts.length} total · {unread} unread
              </span>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
