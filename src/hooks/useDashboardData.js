import { useCallback, useEffect, useState } from 'react'
import { getPortalContextHeaders } from '../utils/portalContextHeaders'

/**
 * Fetches GET /api/dashboard/summary and refetches when the active workspace changes.
 * Workspace/tenant headers are included via portal context (authFetch pattern).
 */
export default function useDashboardData() {
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchSummary = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const token = localStorage.getItem('token') || localStorage.getItem('aiops_access_token')
      const portalHeaders = getPortalContextHeaders()
      const response = await fetch('/api/dashboard/summary', {
        headers: {
          Authorization: `Bearer ${token}`,
          ...portalHeaders,
        },
      })
      if (response.ok) {
        setData(await response.json())
      } else {
        setError(`Server error ${response.status}`)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    void fetchSummary()
  }, [fetchSummary])

  useEffect(() => {
    const onWorkspace = () => {
      void fetchSummary()
    }
    window.addEventListener('active-workspace-changed', onWorkspace)
    window.addEventListener('context-changed', onWorkspace)
    return () => {
      window.removeEventListener('active-workspace-changed', onWorkspace)
      window.removeEventListener('context-changed', onWorkspace)
    }
  }, [fetchSummary])

  return { data, isLoading, error, refetch: fetchSummary }
}
