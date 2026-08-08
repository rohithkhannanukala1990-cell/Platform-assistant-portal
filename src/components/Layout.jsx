import { useCallback, useEffect, useState } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import TopBar from './TopBar'
import CommandPalette from './CommandPalette'
import ChatBot from './ChatBot'
import { API_BASE } from '../config/apiBase'
import { useAuth } from '../contexts/AuthContext'

function buildPortalWsUrl() {
  // JWT is sent in the first message after open — never in the URL (proxy logs).
  if (!API_BASE) {
    const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const host = typeof window !== 'undefined' ? window.location.host : 'localhost:5173'
    return `${proto}//${host}/ws/portal`
  }
  try {
    const u = new URL(API_BASE.startsWith('http') ? API_BASE : `http://${API_BASE}`)
    u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
    u.pathname = '/ws/portal'
    u.search = ''
    u.hash = ''
    return u.toString()
  } catch {
    return 'ws://localhost:8000/ws/portal'
  }
}

export default function Layout({ user }) {
  const { role } = useAuth()
  const navigate = useNavigate()
  const [criticalHealthBanner, setCriticalHealthBanner] = useState(null)
  const [healthWsToast, setHealthWsToast] = useState(null)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)

  const openHealthDashboard = useCallback(() => {
    navigate('/health')
  }, [navigate])

  useEffect(() => {
    const onOpenPalette = () => setPaletteOpen(true)
    window.addEventListener('open-command-palette', onOpenPalette)
    return () => window.removeEventListener('open-command-palette', onOpenPalette)
  }, [])

  useEffect(() => {
    function onKey(e) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setPaletteOpen((v) => !v)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [paletteOpen])

  useEffect(() => {
    if (role !== 'Admin' && role !== 'User') return undefined
    let ws
    try {
      ws = new WebSocket(buildPortalWsUrl())
      ws.onopen = () => {
        const token = localStorage.getItem('aiops_access_token') || ''
        ws.send(JSON.stringify({ token }))
      }
      ws.onmessage = (ev) => {
        let data
        try {
          data = JSON.parse(ev.data)
        } catch {
          return
        }
        if (data.type !== 'health_alert') return
        window.dispatchEvent(new CustomEvent('portal-health-alert', { detail: data }))
        if (data.severity === 'critical') {
          setCriticalHealthBanner(data.message || 'Critical system alert')
        } else if (data.severity === 'warning') {
          setHealthWsToast(data.message || 'Health warning')
          window.setTimeout(() => setHealthWsToast(null), 8000)
        }
      }
    } catch {
      /* WS optional */
    }
    return () => {
      if (ws && ws.readyState <= 1) ws.close()
    }
  }, [role])

  return (
    <div className="flex h-screen bg-neutral-950 text-white overflow-hidden">
      <Sidebar user={user} open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex flex-col flex-1 overflow-hidden">
        {criticalHealthBanner && (role === 'Admin' || role === 'User') && (
          <div className="shrink-0 flex flex-wrap items-center justify-between gap-3 px-4 py-2.5 bg-red-950/80 border-b border-red-700/50 text-red-100 text-sm">
            <span>Critical system alert: {criticalHealthBanner}</span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                className="px-3 py-1 rounded-lg bg-white/10 hover:bg-white/20 text-white text-xs font-semibold"
                onClick={openHealthDashboard}
              >
                View Health Dashboard
              </button>
              <button
                type="button"
                className="px-2 py-1 text-xs text-red-200/80 hover:text-white"
                onClick={() => setCriticalHealthBanner(null)}
                aria-label="Dismiss critical alert"
              >
                Dismiss
              </button>
            </div>
          </div>
        )}
        {healthWsToast && (role === 'Admin' || role === 'User') && (
          <div className="fixed bottom-6 left-6 z-[60] max-w-sm px-4 py-3 rounded-lg border border-amber-500/40 bg-amber-950/90 text-amber-100 text-sm shadow-xl">
            {healthWsToast}
          </div>
        )}
        <TopBar
          user={user}
          onOpenCommandPalette={() => setPaletteOpen(true)}
          onMenuOpen={() => setSidebarOpen(true)}
        />
        <main className="flex-1 overflow-auto">
          <div className="max-w-7xl mx-auto w-full px-4 sm:px-6 py-6">
            <Outlet />
          </div>
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
      <ChatBot />
    </div>
  )
}
