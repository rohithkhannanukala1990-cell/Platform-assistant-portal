import { useCallback, useEffect, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

/** Admin + Operator (canonical role "User") may view health; Admin mutates. */
export function canViewHealth(role) {
  return role === 'Admin' || role === 'User'
}

export function canMutateHealth(role) {
  return role === 'Admin'
}

/** Fetch summary + full health probes for dashboard cards / drill-downs. */
export default function useHealthDashboard({ enabled = true } = {}) {
  const { authFetch, role } = useAuth()
  const [healthData, setHealthData] = useState(null)
  const [summary, setSummary] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [isLoading, setIsLoading] = useState(Boolean(enabled))
  const [fetchError, setFetchError] = useState(false)
  const [lastChecked, setLastChecked] = useState(null)
  const [autoRefreshTimer, setAutoRefreshTimer] = useState(60)
  const fetchRef = useRef(async () => {})

  const allowed = enabled && canViewHealth(role)

  const fetchHealth = useCallback(async () => {
    if (!canViewHealth(role)) {
      setIsLoading(false)
      return
    }
    setFetchError(false)
    try {
      const [fullRes, alertsRes, summaryRes] = await Promise.all([
        authFetch('/api/health/full'),
        authFetch('/api/health/alerts'),
        authFetch('/api/health/summary'),
      ])
      if (!fullRes.ok || !alertsRes.ok) {
        setFetchError(true)
        setHealthData(null)
        setAlerts([])
        return
      }
      const full = await fullRes.json()
      const list = await alertsRes.json()
      const sum = summaryRes.ok ? await summaryRes.json() : null
      setHealthData(full)
      setSummary(sum)
      setAlerts(Array.isArray(list) ? list : [])
      setLastChecked(new Date().toLocaleString())
      setAutoRefreshTimer(60)
    } catch {
      setFetchError(true)
      setHealthData(null)
      setAlerts([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch, role])

  fetchRef.current = fetchHealth

  useEffect(() => {
    if (!allowed) {
      setIsLoading(false)
      return undefined
    }
    setIsLoading(true)
    void fetchHealth()
    return undefined
  }, [allowed, fetchHealth])

  useEffect(() => {
    if (!allowed) return undefined
    const onWorkspace = () => {
      void fetchRef.current()
    }
    window.addEventListener('active-workspace-changed', onWorkspace)
    window.addEventListener('context-changed', onWorkspace)
    return () => {
      window.removeEventListener('active-workspace-changed', onWorkspace)
      window.removeEventListener('context-changed', onWorkspace)
    }
  }, [allowed])

  useEffect(() => {
    if (!allowed) return undefined
    const id = window.setInterval(() => {
      setAutoRefreshTimer((c) => {
        if (c <= 1) {
          window.queueMicrotask(() => {
            void fetchRef.current()
          })
          return 60
        }
        return c - 1
      })
    }, 1000)
    return () => window.clearInterval(id)
  }, [allowed])

  return {
    role,
    canView: canViewHealth(role),
    canMutate: canMutateHealth(role),
    healthData,
    summary,
    alerts,
    setAlerts,
    isLoading,
    fetchError,
    lastChecked,
    autoRefreshTimer,
    fetchHealth,
    refresh: () => {
      setIsLoading(true)
      return fetchHealth()
    },
  }
}
