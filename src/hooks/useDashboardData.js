import { useCallback, useEffect, useState } from 'react'

/**
 * Fetches GET /api/dashboard/summary on mount and exposes a refetch helper.
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
      const response = await fetch('/api/dashboard/summary', {
        headers: { Authorization: `Bearer ${token}` },
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

  return { data, isLoading, error, refetch: fetchSummary }
}
