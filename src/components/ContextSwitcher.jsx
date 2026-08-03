import { useState, useRef, useEffect } from 'react'
import { SlidersHorizontal, ChevronDown } from 'lucide-react'
import EnvironmentSwitcher from './EnvironmentSwitcher'
import AccountSwitcher from './AccountSwitcher'

function readEnvLabel() {
  try {
    const env = localStorage.getItem('portal_env') || 'production'
    return env.charAt(0).toUpperCase() + env.slice(1)
  } catch {
    return 'Production'
  }
}

/**
 * Single compact dropdown that groups the environment switcher and the
 * per-tool account switcher, so the top bar shows one button instead of two.
 */
export default function ContextSwitcher({ toolId }) {
  const [open, setOpen] = useState(false)
  const [envLabel, setEnvLabel] = useState(readEnvLabel)
  const ref = useRef(null)

  useEffect(() => {
    const sync = () => setEnvLabel(readEnvLabel())
    window.addEventListener('context-changed', sync)
    return () => window.removeEventListener('context-changed', sync)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    function onDoc(ev) {
      if (ref.current && !ref.current.contains(ev.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDoc)
    return () => document.removeEventListener('mousedown', onDoc)
  }, [open])

  const isProd = envLabel.toLowerCase() === 'production' || envLabel.toLowerCase() === 'dr'

  return (
    <div className="relative" ref={ref}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-neutral-700 bg-neutral-800 text-sm text-slate-200 hover:bg-neutral-700/80 hover:border-neutral-600 transition-colors"
        aria-expanded={open}
        aria-haspopup="true"
        title="Environment & account context"
      >
        <SlidersHorizontal className="w-4 h-4 text-slate-400 shrink-0" />
        <span className={`w-2 h-2 rounded-full shrink-0 ${isProd ? 'bg-danger' : 'bg-success'}`} />
        <span className="font-medium hidden lg:inline max-w-[7rem] truncate">{envLabel}</span>
        <ChevronDown className={`w-4 h-4 text-slate-500 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-[90] w-[320px] rounded-xl border border-border bg-surface shadow-2xl p-3 flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Environment</p>
            <EnvironmentSwitcher />
          </div>
          {toolId && (
            <div className="flex flex-col gap-1.5 border-t border-border pt-3">
              <p className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Tool account</p>
              <AccountSwitcher toolId={toolId} onAccountChanged={() => {}} />
            </div>
          )}
        </div>
      )}
    </div>
  )
}
