import { useState, useRef, useEffect } from 'react'
import { User, Settings, LogOut, ChevronDown, LogIn, ShieldCheck } from 'lucide-react'

export default function UserMenu({ isLoggedIn, onLogin, onLogout, onOpenSettings }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)

  // Close dropdown when clicking outside
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [])

  if (!isLoggedIn) {
    return (
      <button
        onClick={onLogin}
        className="flex items-center gap-2 px-4 py-1.5 rounded-lg bg-accent hover:bg-green-400
          text-black text-xs font-semibold transition-all hover:scale-105 shadow-md shadow-accent/20"
      >
        <LogIn className="w-3.5 h-3.5" />
        Login
      </button>
    )
  }

  return (
    <div className="relative pl-2 border-l border-border" ref={ref}>
      {/* Trigger */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 px-2 py-1.5 rounded-lg hover:bg-card
          transition-colors cursor-pointer group"
      >
        {/* Avatar */}
        <div className="flex items-center justify-center w-7 h-7 rounded-full
          bg-accent/20 border border-accent/30 group-hover:border-accent/60 transition-colors">
          <span className="text-[11px] font-bold text-accent leading-none">OE</span>
        </div>
        <span className="text-xs font-medium text-slate-300 group-hover:text-white transition-colors">
          Ops Engineer
        </span>
        <ChevronDown
          className={`w-3.5 h-3.5 text-slate-500 transition-transform duration-200
            ${open ? 'rotate-180' : ''}`}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-52 rounded-xl border border-border
          bg-sidebar shadow-2xl shadow-black/60 overflow-hidden z-50
          animate-in fade-in slide-in-from-top-2 duration-150">

          {/* User info header */}
          <div className="flex items-center gap-3 px-4 py-3 border-b border-border bg-card/40">
            <div className="flex items-center justify-center w-9 h-9 rounded-full
              bg-accent/20 border border-accent/30 shrink-0">
              <span className="text-sm font-bold text-accent">OE</span>
            </div>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-white truncate">Ops Engineer</p>
              <p className="text-[10px] text-slate-500 flex items-center gap-1">
                <ShieldCheck className="w-3 h-3 text-accent" />
                Admin
              </p>
            </div>
          </div>

          {/* Menu items */}
          <div className="py-1.5">
            <MenuItem icon={User} label="Profile" onClick={() => setOpen(false)} />
            <MenuItem
              icon={Settings}
              label="Platform Settings"
              onClick={() => { setOpen(false); onOpenSettings?.() }}
            />
          </div>

          <div className="border-t border-border py-1.5">
            <MenuItem
              icon={LogOut}
              label="Logout"
              danger
              onClick={() => { setOpen(false); onLogout() }}
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
      onClick={onClick}
      className={`flex items-center gap-3 w-full px-4 py-2 text-xs font-medium
        transition-colors cursor-pointer
        ${danger
          ? 'text-red-400 hover:bg-red-500/10 hover:text-red-300'
          : 'text-slate-300 hover:bg-card hover:text-white'
        }`}
    >
      <Icon className="w-3.5 h-3.5 shrink-0" />
      {label}
    </button>
  )
}
