import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { X } from 'lucide-react'

const ToastContext = createContext(null)

let toastId = 0
let globalToast = null

export function registerGlobalToast(api) {
  globalToast = api
}

export function getGlobalToast() {
  return globalToast
}

const TYPE_STYLES = {
  success: 'bg-emerald-950/95 border-emerald-500/40 text-emerald-100',
  warning: 'bg-amber-950/95 border-amber-500/40 text-amber-100',
  error: 'bg-red-950/95 border-red-500/40 text-red-100',
  info: 'bg-blue-950/95 border-blue-500/40 text-blue-100',
}

const DURATIONS = { success: 4000, warning: 4000, info: 4000, error: 6000 }
const MAX_TOASTS = 5

function ToastItem({ message, type, onDismiss }) {
  const cls = TYPE_STYLES[type] || TYPE_STYLES.info
  return (
    <div
      className={`pointer-events-auto flex items-start gap-3 min-w-[240px] max-w-sm px-4 py-3 rounded-lg border shadow-lg ${cls}`}
      style={{ animation: 'portalToastSlideIn 0.25s ease-out forwards' }}
    >
      <p className="text-sm flex-1 leading-snug">{message}</p>
      <button
        type="button"
        onClick={onDismiss}
        className="p-0.5 rounded hover:bg-white/10 text-current shrink-0"
        aria-label="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const removeToast = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (message, type = 'info') => {
      const id = ++toastId
      const duration = DURATIONS[type] || 4000
      setToasts((list) => {
        const next = [...list, { id, message, type }]
        return next.length > MAX_TOASTS ? next.slice(-MAX_TOASTS) : next
      })
      window.setTimeout(() => removeToast(id), duration)
      return id
    },
    [removeToast]
  )

  const toast = useMemo(
    () => ({
      success: (msg) => push(msg, 'success'),
      error: (msg) => push(msg, 'error'),
      warning: (msg) => push(msg, 'warning'),
      info: (msg) => push(msg, 'info'),
    }),
    [push]
  )

  const value = useMemo(
    () => ({
      toast,
      addToast: push,
      showToast: (message, type = 'info') => push(message, type),
      dismiss: removeToast,
    }),
    [toast, push, removeToast]
  )

  useEffect(() => {
    registerGlobalToast(toast)
    return () => registerGlobalToast(null)
  }, [toast])

  return (
    <ToastContext.Provider value={value}>
      <style>{`
        @keyframes portalToastSlideIn {
          from { opacity: 0; transform: translateX(100%); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 items-end pointer-events-none"
        aria-live="polite"
      >
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            message={t.message}
            type={t.type}
            onDismiss={() => removeToast(t.id)}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}
