import { useState, useEffect, useCallback } from 'react'
import { useAuth } from '../contexts/AuthContext'

/**
 * Portal-wide active environment / account context (GET/PUT /api/context).
 */
export function usePortalContext() {
  const { authFetch } = useAuth()
  const [context, setContext] = useState(null)
  const [isLoading, setIsLoading] = useState(true)

  const fetchContext = useCallback(async () => {
    try {
      const res = await authFetch('/api/context')
      if (!res.ok) {
        setIsLoading(false)
        return
      }
      const data = await res.json()
      setContext(data)
    } catch {
      setContext(null)
    } finally {
      setIsLoading(false)
    }
  }, [authFetch])

  const onContextChanged = useCallback((event) => {
    const ctx = event.detail?.context
    if (ctx) setContext(ctx)
    else void fetchContext()
  }, [fetchContext])

  useEffect(() => {
    void fetchContext()
    window.addEventListener('context-changed', onContextChanged)
    return () => window.removeEventListener('context-changed', onContextChanged)
  }, [fetchContext, onContextChanged])

  const switchEnvironment = useCallback(
    async (envId) => {
      const res = await authFetch('/api/context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_environment: envId }),
      })
      if (!res.ok) throw new Error('Failed to switch environment')
      const data = await res.json()
      setContext(data)
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: { environment: envId, context: data },
        })
      )
      return data
    },
    [authFetch]
  )

  const switchAccount = useCallback(
    async (toolId, accountId) => {
      const res = await authFetch('/api/context', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_accounts: { [toolId]: accountId } }),
      })
      if (!res.ok) throw new Error('Failed to switch account')
      const data = await res.json()
      setContext(data)
      window.dispatchEvent(
        new CustomEvent('context-changed', {
          detail: {
            environment: data.active_environment,
            context: data,
            source: 'usePortalContext.switchAccount',
          },
        })
      )
      return data
    },
    [authFetch]
  )

  return {
    context,
    isLoading,
    activeEnvironment: context?.active_environment,
    activeAccounts: context?.active_accounts,
    refetch: fetchContext,
    switchEnvironment,
    switchAccount,
  }
}
