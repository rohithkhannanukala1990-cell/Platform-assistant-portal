import { useState, useEffect, useCallback, useMemo } from 'react'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../components/ToastNotification'

const PRESET_CATEGORY_PILLS = ['operations', 'engineering', 'onboarding', 'finops']

function matchesTemplateSearch(t, q) {
  if (!q.trim()) return true
  const s = q.toLowerCase()
  const tags = Array.isArray(t.tags) ? t.tags.join(' ').toLowerCase() : ''
  return (
    (t.name || '').toLowerCase().includes(s) ||
    (t.description || '').toLowerCase().includes(s) ||
    tags.includes(s)
  )
}

/**
 * Fetches templates and exposes search/category filter state.
 */
export default function useTemplates() {
  const { authFetch } = useAuth()
  const { showToast } = useToast()

  const [templates, setTemplates] = useState([])
  const [categories, setCategories] = useState([])
  const [activeFilter, setActiveFilter] = useState('all')
  const [searchQuery, setSearchQuery] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)

  const categoryPills = useMemo(() => {
    const fromApi = (categories || []).map((c) => c.category).filter(Boolean)
    const merged = new Set(['all', ...PRESET_CATEGORY_PILLS, ...fromApi])
    return Array.from(merged)
  }, [categories])

  const loadCategories = useCallback(async () => {
    try {
      const res = await authFetch('/api/templates/categories')
      if (!res.ok) return
      setCategories(await res.json())
    } catch {
      setCategories([])
    }
  }, [authFetch])

  const loadTemplates = useCallback(async () => {
    setIsLoading(true)
    setError(null)
    try {
      const qs =
        activeFilter !== 'all' ? `?category=${encodeURIComponent(activeFilter)}` : ''
      const res = await authFetch(`/api/templates${qs}`)
      if (!res.ok) throw new Error(await res.text())
      setTemplates(await res.json())
    } catch (e) {
      const message = e.message || 'Failed to load templates'
      setError(message)
      showToast(message, 'error')
      setTemplates([])
    } finally {
      setIsLoading(false)
    }
  }, [authFetch, showToast, activeFilter])

  useEffect(() => {
    void loadCategories()
  }, [loadCategories])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  const filteredTemplates = useMemo(() => {
    return templates.filter((t) => matchesTemplateSearch(t, searchQuery))
  }, [templates, searchQuery])

  return {
    templates,
    filteredTemplates,
    isLoading,
    error,
    searchQuery,
    setSearchQuery,
    activeFilter,
    setActiveFilter,
    categories: categoryPills,
    loadTemplates,
  }
}
