import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from 'react'
import { X } from 'lucide-react'

const ToastContext = createContext(null)

const MAX_TOASTS = 5
const EXIT_MS = 280

const DURATION_MS = {
  success: 4000,
  warning: 4000,
  info: 4000,
  error: 6000,
}

const TYPE_STYLES = {
  success: 'bg-emerald-950/95 border-emerald-500/50 text-emerald-100',
  error: 'bg-red-950/95 border-red-500/50 text-red-100',
  warning: 'bg-amber-950/95 border-amber-500/50 text-amber-100',
  info: 'bg-blue-950/95 border-blue-500/50 text-blue-100',
}

let globalToastApi = null

/** For authFetch and other modules outside the React tree */
export function getGlobalToast() {
  return globalToastApi
}

function ToastItem({ id, message, type, exiting, onDismiss }) {
  const [entered, setEntered] = useState(false)
  const styles = TYPE_STYLES[type] || TYPE_STYLES.info

  useEffect(() => {
    const frame = requestAnimationFrame(() => setEntered(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  const slideIn = entered && !exiting

  return (
    <div
      role="status"
      className={`pointer-events-auto flex items-start gap-3 min-w-[260px] max-w-sm px-4 py-3 rounded-lg border shadow-lg ${styles}`}
      style={{
        transform: slideIn ? 'translateX(0)' : 'translateX(calc(100% + 1rem))',
        opacity: slideIn ? 1 : 0,
        transition: `transform ${EXIT_MS}ms ease-out, opacity ${EXIT_MS}ms ease-out`,
      }}
    >
      <p className="text-sm flex-1 leading-snug">{message}</p>
      <button
        type="button"
        onClick={() => onDismiss(id)}
        className="p-0.5 rounded hover:bg-white/10 shrink-0"
        aria-label="Dismiss notification"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  )
}

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timersRef = useRef(new Map())
  const idRef = useRef(0)

  const clearTimer = useCallback((id) => {
    const t = timersRef.current.get(id)
    if (t) {
      clearTimeout(t)
      timersRef.current.delete(id)
    }
  }, [])

  const removeToast = useCallback(
    (id) => {
      clearTimer(id)
      setToasts((list) => list.filter((t) => t.id !== id))
    },
    [clearTimer]
  )

  const dismiss = useCallback(
    (id) => {
      clearTimer(id)
      setToasts((list) =>
        list.map((t) => (t.id === id ? { ...t, exiting: true } : t))
      )
      window.setTimeout(() => removeToast(id), EXIT_MS)
    },
    [clearTimer, removeToast]
  )

  const push = useCallback(
    (message, type = 'info') => {
      const id = ++idRef.current
      const duration = DURATION_MS[type] ?? DURATION_MS.info

      setToasts((list) => {
        const next = [...list, { id, message, type, exiting: false }]
        if (next.length <= MAX_TOASTS) return next
        const dropped = next.slice(0, next.length - MAX_TOASTS)
        dropped.forEach((t) => clearTimer(t.id))
        return next.slice(-MAX_TOASTS)
      })

      const timer = window.setTimeout(() => dismiss(id), duration)
      timersRef.current.set(id, timer)
      return id
    },
    [clearTimer, dismiss]
  )

  const toast = useMemo(
    () => ({
      success: (message) => push(message, 'success'),
      error: (message) => push(message, 'error'),
      warning: (message) => push(message, 'warning'),
      info: (message) => push(message, 'info'),
    }),
    [push]
  )

  useEffect(() => {
    globalToastApi = toast
    return () => {
      globalToastApi = null
      timersRef.current.forEach((t) => clearTimeout(t))
      timersRef.current.clear()
    }
  }, [toast])

  const value = useMemo(() => ({
    toast,
    showToast: (message, type = 'info') => push(message, type),
  }), [toast, push])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        className="fixed bottom-4 right-4 z-[9999] flex flex-col gap-2 items-end pointer-events-none"
        aria-live="polite"
        aria-relevant="additions"
      >
        {toasts.map((t) => (
          <ToastItem
            key={t.id}
            id={t.id}
            message={t.message}
            type={t.type}
            exiting={t.exiting}
            onDismiss={dismiss}
          />
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const ctx = useContext(ToastContext)
  if (!ctx) {
    throw new Error('useToast must be used inside <ToastProvider>')
  }
  return ctx
}
