import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useAuth } from './AuthContext'
import { setPortalContextHeaders } from '../utils/portalContextHeaders'

const LS_ACTIVE_WORKSPACE = 'active_workspace_id'

const PortalContext = createContext(null)

export function PortalProvider({ children }) {
  const { authFetch, isAuthenticated } = useAuth()
  const [activeWorkspace, setActiveWorkspaceState] = useState(null)
  const [pinnedWorkspaces, setPinnedWorkspaces] = useState([])
  const [currentEnvironment, setCurrentEnvironment] = useState('development')

  const refreshEnvironment = useCallback(async () => {
    try {
      const res = await authFetch('/api/context')
      if (!res.ok) return
      const data = await res.json()
      setCurrentEnvironment(String(data.active_environment || 'development').toLowerCase())
    } catch {
      /* noop */
    }
  }, [authFetch])

  const setEnvironment = useCallback(
    async (envId) => {
      const e = String(envId || 'development').toLowerCase()
      const res = await authFetch('/api/context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_environment: e }),
      })
      if (!res.ok) throw new Error('Failed to switch environment')
      const data = await res.json()
      setCurrentEnvironment(e)
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: { context: data, environment: e, source: 'portal-context' },
        })
      )
      return data
    },
    [authFetch]
  )

  const setActiveWorkspace = useCallback(
    async (workspace) => {
      if (!workspace) {
        setActiveWorkspaceState(null)
        try {
          localStorage.removeItem(LS_ACTIVE_WORKSPACE)
        } catch {
          /* noop */
        }
        setPortalContextHeaders({ activeWorkspaceId: null })
        window.dispatchEvent(new CustomEvent('active-workspace-changed', { detail: { workspace: null } }))
        return
      }

      let envNow = currentEnvironment
      try {
        const res = await authFetch('/api/context')
        if (res.ok) {
          const data = await res.json()
          envNow = String(data.active_environment || 'development').toLowerCase()
          setCurrentEnvironment(envNow)
        }
      } catch {
        /* use currentEnvironment */
      }

      const wenv = String(workspace.environment || 'development').toLowerCase()
      if (wenv !== envNow) {
        try {
          await setEnvironment(wenv)
        } catch {
          /* still activate workspace */
        }
      }

      setActiveWorkspaceState(workspace)
      try {
        localStorage.setItem(LS_ACTIVE_WORKSPACE, workspace.id)
      } catch {
        /* noop */
      }
      setPortalContextHeaders({ activeWorkspaceId: workspace.id })
      window.dispatchEvent(new CustomEvent('active-workspace-changed', { detail: { workspace } }))
    },
    [authFetch, setEnvironment]
  )

  useEffect(() => {
    const onCtx = (ev) => {
      const d = ev.detail || {}
      if (d.context?.active_environment) {
        setCurrentEnvironment(String(d.context.active_environment).toLowerCase())
      } else if (d.environment) {
        setCurrentEnvironment(String(d.environment).toLowerCase())
      }
    }
    window.addEventListener('context-changed', onCtx)
    return () => window.removeEventListener('context-changed', onCtx)
  }, [])

  useEffect(() => {
    if (!isAuthenticated) {
      setActiveWorkspaceState(null)
      setPinnedWorkspaces([])
      setPortalContextHeaders({ activeWorkspaceId: null })
      return undefined
    }

    let cancelled = false

    async function init() {
      await refreshEnvironment()

      try {
        const pinnedRes = await authFetch('/api/workspaces?pinned=true')
        if (pinnedRes.ok && !cancelled) {
          const list = await pinnedRes.json()
          setPinnedWorkspaces(Array.isArray(list) ? list : [])
        }
      } catch {
        if (!cancelled) setPinnedWorkspaces([])
      }

      let savedId = null
      try {
        savedId = localStorage.getItem(LS_ACTIVE_WORKSPACE)
      } catch {
        savedId = null
      }

      if (savedId && !cancelled) {
        try {
          const wr = await authFetch(`/api/workspaces/${encodeURIComponent(savedId)}`)
          if (wr.ok && !cancelled) {
            const ws = await wr.json()
            setActiveWorkspaceState(ws)
            setPortalContextHeaders({ activeWorkspaceId: ws.id })
          } else {
            try {
              localStorage.removeItem(LS_ACTIVE_WORKSPACE)
            } catch {
              /* noop */
            }
            setPortalContextHeaders({ activeWorkspaceId: null })
          }
        } catch {
          try {
            localStorage.removeItem(LS_ACTIVE_WORKSPACE)
          } catch {
            /* noop */
          }
          setPortalContextHeaders({ activeWorkspaceId: null })
        }
      }
    }

    void init()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, authFetch, refreshEnvironment])

  const refetchPinnedWorkspaces = useCallback(async () => {
    try {
      const pinnedRes = await authFetch('/api/workspaces?pinned=true')
      if (pinnedRes.ok) {
        const list = await pinnedRes.json()
        setPinnedWorkspaces(Array.isArray(list) ? list : [])
      }
    } catch {
      setPinnedWorkspaces([])
    }
  }, [authFetch])

  const value = useMemo(
    () => ({
      activeWorkspace,
      pinnedWorkspaces,
      currentEnvironment,
      setActiveWorkspace,
      setEnvironment,
      refetchPinnedWorkspaces,
    }),
    [
      activeWorkspace,
      pinnedWorkspaces,
      currentEnvironment,
      setActiveWorkspace,
      setEnvironment,
      refetchPinnedWorkspaces,
    ]
  )

  return <PortalContext.Provider value={value}>{children}</PortalContext.Provider>
}

export function usePortalContext() {
  const ctx = useContext(PortalContext)
  if (!ctx) throw new Error('usePortalContext must be used inside <PortalProvider>')
  return ctx
}
