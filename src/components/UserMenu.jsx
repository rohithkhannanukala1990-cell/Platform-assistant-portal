import { useState, useRef, useEffect, useMemo } from 'react'
import { User, Settings, LogOut, ChevronDown, ShieldCheck, Zap, Wifi } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'

function initialsFrom(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean)
  if (!parts.length) return '?'
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase()
  return `${parts[0][0]}${parts[1][0]}`.toUpperCase()
}

export default function UserMenu({ onOpenSettings, llmLabel, wsConnected = true }) {
  const { isAuthenticated, logout, user, role } = useAuth()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  const displayName = user?.username || user?.name || 'User'
  const initials = useMemo(() => initialsFrom(displayName), [displayName])
  const roleLabel = role || user?.role || 'User'

  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (!isAuthenticated) return null

  return (
    <div className="relative shrink-0" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        title={`${displayName} — account & logout`}
        className="flex items-center gap-1.5 pl-1 pr-2 py-1 rounded-lg border border-neutral-700
          bg-neutral-800/60 hover:bg-neutral-800 hover:border-neutral-600
          transition-colors cursor-pointer"
      >
        <div className="relative shrink-0">
          <div className="flex items-center justify-center w-8 h-8 rounded-full bg-accent text-white">
            <span className="text-xs font-bold leading-none">{initials}</span>
          </div>
          {!wsConnected && (
            <span
              className="absolute -bottom-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-warning border-2 border-neutral-900 animate-pulse"
              title="Live updates reconnecting"
            />
          )}
        </div>
        <span className="hidden md:inline text-xs font-semibold text-white max-w-[6rem] truncate">
          {displayName}
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-400 transition-transform duration-200
            ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {open && (
        <div
          className="absolute right-0 top-full mt-2 w-56 rounded-xl border border-neutral-700
            bg-neutral-950 shadow-2xl shadow-black/60 overflow-hidden z-50"
        >
          <div className="flex items-center gap-3 px-4 py-3 border-b border-neutral-800 bg-neutral-900/80">
            <div className="flex items-center justify-center w-9 h-9 rounded-full shrink-0 bg-accent text-white">
              <span className="text-sm font-bold">{initials}</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">{displayName}</p>
              <p className="text-[10px] text-neutral-400 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-accent-hover" />
                {roleLabel}
              </p>
            </div>
          </div>

          <div className="px-4 py-2 border-b border-neutral-800 flex flex-col gap-1.5">
            {llmLabel && (
              <p className="flex items-center gap-2 text-[11px] text-neutral-400">
                <Zap className="w-3 h-3 text-accent-hover shrink-0" />
                <span className="truncate">Model: {llmLabel}</span>
              </p>
            )}
            <p className="flex items-center gap-2 text-[11px] text-neutral-400">
              <Wifi className={`w-3 h-3 shrink-0 ${wsConnected ? 'text-success' : 'text-warning'}`} />
              {wsConnected ? 'Live updates active' : 'Reconnecting…'}
            </p>
          </div>

          <div className="py-1.5">
            <MenuItem icon={User} label="Profile" onClick={() => setOpen(false)} />
            <MenuItem
              icon={Settings}
              label="Platform Settings"
              onClick={() => {
                setOpen(false)
                onOpenSettings?.()
              }}
            />
          </div>

          <div className="border-t border-neutral-800 py-1.5">
            <MenuItem
              icon={LogOut}
              label="Logout"
              danger
              onClick={() => {
                setOpen(false)
                void logout()
              }}
            />
          </div>
        </div>
      )}
    </div>
  )
}

function MenuItem({ icon: Icon, label, onClick, danger }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex items-center gap-3 w-full px-4 py-2 text-xs font-medium
        transition-colors cursor-pointer
        ${
          danger
            ? 'text-red-400 hover:bg-red-500/10 hover:text-red-300'
            : 'text-neutral-300 hover:bg-neutral-800 hover:text-white'
        }`}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" />
      {label}
    </button>
  )
}
