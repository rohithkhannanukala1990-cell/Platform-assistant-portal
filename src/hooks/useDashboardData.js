import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

/**
 * Fetches GET /api/dashboard/summary and refetches when the active workspace changes.
 */
export default function useDashboardData() {
  const { authFetch } = useAuth()
  const [data, setData] = useState(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchSummary = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const response = await authFetch('/api/dashboard/summary')
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
  }, [authFetch])

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
