import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { ChevronDown, ShieldCheck } from 'lucide-react'
import { useRole, ROLES } from '../contexts/RoleContext'

export default function PersonaSwitcher() {
  const { role, setRole, roleInfo } = useRole()
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const navigate = useNavigate()

  useEffect(() => {
    function handle(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handle)
    return () => document.removeEventListener('mousedown', handle)
  }, [])

  function switchTo(id) {
    setRole(id)
    setOpen(false)
    navigate(ROLES[id].portal)
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-border
          hover:bg-card transition-colors text-xs font-medium group"
        title="Switch Persona"
      >
        <ShieldCheck className="w-3.5 h-3.5 text-purple-400 shrink-0" />
        <span className={roleInfo.color}>{roleInfo.label}</span>
        <ChevronDown className={`w-3 h-3 text-slate-600 transition-transform duration-150 ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-2 w-52 rounded-xl border border-border
          bg-sidebar shadow-2xl shadow-black/60 overflow-hidden z-50">
          <div className="px-3 py-2 border-b border-border">
            <p className="text-[10px] font-semibold text-slate-500 uppercase tracking-widest">
              Switch Persona
            </p>
          </div>
          <div className="py-1.5">
            {Object.values(ROLES).map((r) => (
              <button
                key={r.id}
                onClick={() => switchTo(r.id)}
                className={`flex items-center gap-3 w-full px-4 py-2.5 text-xs transition-colors
                  ${role === r.id
                    ? 'bg-card text-white font-semibold'
                    : 'text-slate-400 hover:bg-card/60 hover:text-white'
                  }`}
              >
                <span className="text-base w-5 text-center">{r.emoji}</span>
                <span>{r.label}</span>
                {role === r.id && (
                  <span className={`ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded-md border ${r.bg} ${r.color}`}>
                    Active
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
