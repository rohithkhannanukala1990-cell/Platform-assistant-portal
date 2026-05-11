import {
  createContext,
  useCallback,
  useContext,
  useMemo,
  useState,
} from 'react'
import { X } from 'lucide-react'

const ToastContext = createContext(null)

let toastId = 0

const TYPE_STYLES = {
  success: 'bg-emerald-950/95 border-emerald-500/40 text-emerald-100',
  warning: 'bg-amber-950/95 border-amber-500/40 text-amber-100',
  error: 'bg-red-950/95 border-red-500/40 text-red-100',
  info: 'bg-blue-950/95 border-blue-500/40 text-blue-100',
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const dismiss = useCallback((id) => {
    setToasts((list) => list.filter((t) => t.id !== id))
  }, [])

  const showToast = useCallback(
    (message, type = 'info') => {
      const id = ++toastId
      setToasts((list) => [...list, { id, message, type }])
      window.setTimeout(() => dismiss(id), 3000)
      return id
    },
    [dismiss]
  )

  const value = useMemo(() => ({ showToast, dismiss }), [showToast, dismiss])

  return (
    <ToastContext.Provider value={value}>
      <style>{`
        @keyframes portalToastSlideIn {
          from { opacity: 0; transform: translateX(100%); }
          to { opacity: 1; transform: translateX(0); }
        }
      `}</style>
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used inside ToastProvider')
  return ctx
}

export function ToastContainer({ toasts, onDismiss }) {
  if (!toasts?.length) return null
  return (
    <div
      className="fixed bottom-4 right-4 z-[60] flex flex-col gap-2 items-end pointer-events-none"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <ToastItem key={t.id} message={t.message} type={t.type} onDismiss={() => onDismiss(t.id)} />
      ))}
    </div>
  )
}

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
