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

export const PortalContext = createContext(null)

const DEFAULT_PORTAL_USER = {
  id: 'admin',
  name: 'Admin User',
  role: 'superadmin',
  permissions: ['*:*'],
}

export function PortalProvider({ children }) {
  const { authFetch, isAuthenticated } = useAuth()
  const [activeWorkspace, setActiveWorkspaceState] = useState(null)
  const [pinnedWorkspaces, setPinnedWorkspaces] = useState([])
  const [currentEnvironment, setCurrentEnvironment] = useState('development')
  const [currentUser, setCurrentUser] = useState(() => ({ ...DEFAULT_PORTAL_USER }))
  const [pendingApprovals, setPendingApprovals] = useState([])
  const [pendingApprovalCount, setPendingApprovalCount] = useState(0)

  const refreshApprovals = useCallback(async () => {
    try {
      const res = await authFetch('/api/ai/executions/pending')
      if (!res.ok) {
        setPendingApprovals([])
        setPendingApprovalCount(0)
        return
      }
      const data = await res.json()
      const list = Array.isArray(data) ? data : []
      setPendingApprovals(list)
      setPendingApprovalCount(list.length)
    } catch {
      setPendingApprovals([])
      setPendingApprovalCount(0)
    }
  }, [authFetch])

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
        setPortalContextHeaders({ activeWorkspaceId: null, activeTenantId: null })
        window.dispatchEvent(new CustomEvent('active-workspace-changed', { detail: { workspace: null } }))
        window.dispatchEvent(
          new CustomEvent('context-changed', {
            detail: {
              workspace: null,
              workspace_id: null,
              tenant_id: null,
              source: 'portal-workspace-clear',
            },
          })
        )
        return
      }

      let envNow = 'development'
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
      setPortalContextHeaders({
        activeWorkspaceId: workspace.id,
        activeTenantId: workspace.tenant_id || 'default',
      })
      // TODO(S2-P2.2): On selection, update global WorkspaceContext and trigger data reloads
      window.dispatchEvent(new CustomEvent('active-workspace-changed', { detail: { workspace } }))
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: {
            workspace,
            workspace_id: workspace.id,
            tenant_id: workspace.tenant_id || null,
            environment: wenv,
            source: 'portal-workspace-switch',
          },
        })
      )
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
      setPortalContextHeaders({ activeWorkspaceId: null, activeTenantId: null })
      setCurrentUser({ ...DEFAULT_PORTAL_USER })
      setPendingApprovals([])
      setPendingApprovalCount(0)
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
            setPortalContextHeaders({
              activeWorkspaceId: ws.id,
              activeTenantId: ws.tenant_id || 'default',
            })
          } else {
            try {
              localStorage.removeItem(LS_ACTIVE_WORKSPACE)
            } catch {
              /* noop */
            }
            setPortalContextHeaders({ activeWorkspaceId: null, activeTenantId: null })
          }
        } catch {
          try {
            localStorage.removeItem(LS_ACTIVE_WORKSPACE)
          } catch {
            /* noop */
          }
          setPortalContextHeaders({ activeWorkspaceId: null, activeTenantId: null })
        }
      }
    }

    void init()
    return () => {
      cancelled = true
    }
  }, [isAuthenticated, authFetch, refreshEnvironment])

  useEffect(() => {
    if (!isAuthenticated) return undefined
    void refreshApprovals()
    const t = setInterval(() => void refreshApprovals(), 60000)
    return () => clearInterval(t)
  }, [isAuthenticated, refreshApprovals])

  // Keep environment header in sync for authFetch consumers.
  useEffect(() => {
    setPortalContextHeaders({ activeEnvironment: currentEnvironment || 'development' })
  }, [currentEnvironment])

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
      currentUser,
      setCurrentUser,
      pendingApprovals,
      pendingApprovalCount,
      refreshApprovals,
      setActiveWorkspace,
      setEnvironment,
      refetchPinnedWorkspaces,
    }),
    [
      activeWorkspace,
      pinnedWorkspaces,
      currentEnvironment,
      currentUser,
      pendingApprovals,
      pendingApprovalCount,
      refreshApprovals,
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
