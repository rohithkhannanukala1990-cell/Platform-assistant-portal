import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useAuth } from './AuthContext'
import { usePortalContext } from './PortalContext'

const PlatformCtx = createContext(null)

const LS_ENV = 'portal_env'

export function PlatformContextProvider({ children }) {
  const { user, role: jwtRole } = useAuth()
  const { activeWorkspace, currentEnvironment } = usePortalContext()

  const [environment, setEnvironmentState] = useState(() => {
    try {
      return localStorage.getItem(LS_ENV) || 'production'
    } catch {
      return 'production'
    }
  })
  const [toolAccounts, setToolAccounts] = useState({})
  const [activeTool, setActiveTool] = useState(null)
  const [activeAccount, setActiveAccount] = useState(null)

  useEffect(() => {
    if (currentEnvironment) {
      setEnvironmentState(currentEnvironment)
    }
  }, [currentEnvironment])

  const setEnvironment = useCallback((env) => {
    const e = (env || 'development').toLowerCase()
    setEnvironmentState(e)
    try {
      localStorage.setItem(LS_ENV, e)
    } catch {
      /* ignore */
    }
  }, [])

  const userRole = useMemo(() => {
    const r = jwtRole || user?.role || 'User'
    return r === 'Admin' ? 'Admin' : 'User'
  }, [jwtRole, user?.role])

  const value = useMemo(
    () => ({
      workspace_id: activeWorkspace?.id || null,
      tenant_id: activeWorkspace?.tenant_id || null,
      workspace_name: activeWorkspace?.name || '',
      environment,
      tool_accounts: toolAccounts,
      user_id: user?.username || '',
      user_role: userRole,
      active_tool: activeTool,
      active_account: activeAccount,
      setEnvironment,
      setToolAccounts,
      setActiveTool,
      setActiveAccount,
      isProduction: () => ['production', 'prod', 'dr'].includes(environment),
      toDict: () => ({
        workspace_id: activeWorkspace?.id || null,
        tenant_id: activeWorkspace?.tenant_id || null,
        workspace_name: activeWorkspace?.name || '',
        environment,
        tool_accounts: toolAccounts,
        user_id: user?.username || '',
        user_role: userRole,
        active_tool: activeTool,
        active_account: activeAccount,
      }),
    }),
    [
      activeWorkspace,
      environment,
      toolAccounts,
      user,
      userRole,
      activeTool,
      activeAccount,
      setEnvironment,
    ]
  )

  return <PlatformCtx.Provider value={value}>{children}</PlatformCtx.Provider>
}

export function usePlatformContext() {
  const ctx = useContext(PlatformCtx)
  if (!ctx) throw new Error('usePlatformContext must be used inside PlatformContextProvider')
  return ctx
}
