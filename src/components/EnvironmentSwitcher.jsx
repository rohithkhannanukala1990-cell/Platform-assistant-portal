import { useState, useEffect, useRef, useCallback } from 'react'
import {
  Globe,
  ChevronDown,
  AlertTriangle,
  Lock,
  Server,
  TestTube,
  Wrench,
  Laptop,
  AlertCircle,
} from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from './ToastNotification'

const ENVIRONMENTS = [
  {
    id: 'local',
    label: 'Local',
    icon: '💻',
    color: 'gray',
    description: 'Local development machine',
    hitl_required: false,
    restricted: false,
  },
  {
    id: 'development',
    label: 'Development',
    icon: '🔧',
    color: 'blue',
    description: 'Shared development environment',
    hitl_required: false,
    restricted: false,
  },
  {
    id: 'test',
    label: 'Test',
    icon: '🧪',
    color: 'purple',
    description: 'QA and testing environment',
    hitl_required: false,
    restricted: false,
  },
  {
    id: 'staging',
    label: 'Staging',
    icon: '🔄',
    color: 'yellow',
    description: 'Pre-production staging environment',
    hitl_required: false,
    restricted: false,
  },
  {
    id: 'production',
    label: 'Production',
    icon: '🚀',
    color: 'red',
    description: 'Live production environment',
    hitl_required: true,
    restricted: true,
  },
  {
    id: 'dr',
    label: 'DR',
    icon: '🆘',
    color: 'orange',
    description: 'Disaster recovery environment',
    hitl_required: true,
    restricted: true,
  },
]

const COLOR_DOT = {
  gray: 'bg-slate-400',
  blue: 'bg-blue-500',
  purple: 'bg-purple-500',
  yellow: 'bg-amber-400',
  red: 'bg-red-500',
  orange: 'bg-orange-500',
}

function envById(id) {
  return ENVIRONMENTS.find((e) => e.id === id) || ENVIRONMENTS[1]
}

function RowLucide({ envId }) {
  const c = 'w-3.5 h-3.5 text-slate-500 shrink-0 mt-1'
  if (envId === 'local') return <Laptop className={c} aria-hidden />
  if (envId === 'development') return <Wrench className={c} aria-hidden />
  if (envId === 'test') return <TestTube className={c} aria-hidden />
  if (envId === 'staging') return <Server className={c} aria-hidden />
  if (envId === 'production') return <Lock className={c} aria-hidden />
  if (envId === 'dr') return <AlertCircle className={c} aria-hidden />
  return null
}

export default function EnvironmentSwitcher() {
  const { authFetch } = useAuth()
  const { showToast } = useToast()
  const [isOpen, setIsOpen] = useState(false)
  const [activeEnv, setActiveEnv] = useState('development')
  const [pendingEnv, setPendingEnv] = useState(null)
  const [showConfirmModal, setShowConfirmModal] = useState(false)

  const rootRef = useRef(null)

  const fetchContext = useCallback(async () => {
    try {
      const res = await authFetch('/api/context')
      if (!res.ok) return
      const data = await res.json()
      const env = (data.active_environment || 'development').toLowerCase()
      setActiveEnv(env)
    } catch {
      /* noop */
    }
  }, [authFetch])

  useEffect(() => {
    void fetchContext()
  }, [fetchContext])

  useEffect(() => {
    const onContextChanged = (ev) => {
      const d = ev.detail || {}
      if (d.context?.active_environment) {
        setActiveEnv(String(d.context.active_environment).toLowerCase())
        return
      }
      if (d.environment) {
        setActiveEnv(String(d.environment).toLowerCase())
        return
      }
      void fetchContext()
    }
    window.addEventListener('context-changed', onContextChanged)
    return () => window.removeEventListener('context-changed', onContextChanged)
  }, [fetchContext])

  useEffect(() => {
    if (!isOpen) return undefined
    function onDocMouseDown(ev) {
      if (rootRef.current && !rootRef.current.contains(ev.target)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocMouseDown)
    return () => document.removeEventListener('mousedown', onDocMouseDown)
  }, [isOpen])

  const switchEnvironment = useCallback(
    async (envId) => {
      try {
        const res = await authFetch('/api/context', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ active_environment: envId }),
        })
        if (!res.ok) {
          showToast('Could not switch environment', 'error')
          return false
        }
        const data = await res.json()
        setActiveEnv(envId)
        window.dispatchEvent(
          new CustomEvent('context-changed', {
            detail: {
              context: data,
              environment: envId,
              source: 'environment-switcher',
            },
          })
        )
        return true
      } catch {
        showToast('Could not switch environment', 'error')
        return false
      }
    },
    [authFetch, showToast]
  )

  const active = envById(activeEnv)

  async function onSelectEnv(env) {
    if (env.restricted) {
      setPendingEnv(env)
      setShowConfirmModal(true)
      setIsOpen(false)
      return
    }
    await switchEnvironment(env.id)
    setIsOpen(false)
  }

  async function confirmProduction() {
    if (!pendingEnv) return
    await switchEnvironment(pendingEnv.id)
    setShowConfirmModal(false)
    setPendingEnv(null)
  }

  function cancelProduction() {
    setShowConfirmModal(false)
    setPendingEnv(null)
  }

  return (
    <div className="relative" ref={rootRef}>
      <button
        type="button"
        onClick={() => setIsOpen((o) => !o)}
        className="inline-flex items-center gap-2 px-3 py-2 rounded-lg border border-gray-700 bg-gray-800 text-sm text-slate-200 hover:bg-gray-700/80 hover:border-gray-600 transition-colors"
        aria-expanded={isOpen}
        aria-haspopup="listbox"
      >
        <Globe className="w-4 h-4 text-slate-400 shrink-0" aria-hidden />
        <span className="text-base leading-none">{active.icon}</span>
        <span className="font-medium">{active.label}</span>
        <span
          className={`w-2 h-2 rounded-full shrink-0 ${COLOR_DOT[active.color] || 'bg-slate-500'}`}
          title={active.color}
        />
        <ChevronDown className={`w-4 h-4 text-slate-500 transition-transform ${isOpen ? 'rotate-180' : ''}`} />
      </button>

      {isOpen && (
        <div
          className="absolute left-0 top-full mt-1 z-50 w-[280px] rounded-lg border border-gray-700 bg-gray-800 shadow-xl py-1 max-h-[min(420px,70vh)] overflow-y-auto"
          role="listbox"
        >
          {ENVIRONMENTS.map((env) => {
            const isActive = env.id === activeEnv
            return (
              <button
                key={env.id}
                type="button"
                role="option"
                aria-selected={isActive}
                onClick={() => void onSelectEnv(env)}
                className={`w-full text-left px-3 py-2.5 flex gap-2 hover:bg-gray-700/80 transition-colors ${
                  isActive ? 'border-l-2 border-accent bg-gray-700/40' : 'border-l-2 border-transparent'
                }`}
              >
                <RowLucide envId={env.id} />
                <span className="text-lg shrink-0">{env.icon}</span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-1.5 flex-wrap">
                    <span className="text-sm font-medium text-white">{env.label}</span>
                    {env.restricted && (
                      <span title="Restricted" className="text-xs">
                        🔒
                      </span>
                    )}
                    {env.hitl_required && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-200 border border-amber-500/30">
                        HITL
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-0.5 leading-snug">{env.description}</p>
                </div>
                <span
                  className={`w-2 h-2 rounded-full shrink-0 mt-1 ${COLOR_DOT[env.color] || 'bg-slate-500'}`}
                />
              </button>
            )
          })}
        </div>
      )}

      {showConfirmModal && pendingEnv && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center p-4 bg-black/70">
          <div
            className="w-full max-w-md rounded-xl border border-gray-700 bg-gray-800 shadow-2xl p-6"
            role="dialog"
            aria-modal="true"
            aria-labelledby="prod-modal-title"
          >
            <div className="flex justify-center mb-4">
              <div className="rounded-full bg-amber-500/15 p-3 border border-amber-500/30">
                <AlertTriangle className="w-10 h-10 text-amber-400" />
              </div>
            </div>
            <h2 id="prod-modal-title" className="text-lg font-semibold text-center text-white">
              Entering {pendingEnv.label} Environment
            </h2>
            <p className="mt-3 text-sm text-slate-300 text-center leading-relaxed">
              All actions in this environment require human approval (HITL). Your session will be fully audited.
              Proceed with caution.
            </p>
            <div className="mt-6 flex flex-col sm:flex-row gap-2 justify-center">
              <button
                type="button"
                onClick={cancelProduction}
                className="px-4 py-2 rounded-lg border border-gray-600 text-sm text-slate-200 hover:bg-gray-700"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmProduction()}
                className="px-4 py-2 rounded-lg bg-red-600 hover:bg-red-500 text-white text-sm font-semibold"
              >
                I Understand — Continue
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
