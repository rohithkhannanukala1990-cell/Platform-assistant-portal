import { useEffect, useRef, useState } from 'react'
import { useAuth } from '../contexts/AuthContext'

/**
 * Debounced catalog search against GET /api/catalog/search.
 * @param {{ query?: string, type?: string, page?: number }} params
 */
export default function useCatalogSearch({ query = '', type = '', page = 1 } = {}) {
  const { authFetch } = useAuth()
  const [results, setResults] = useState([])
  const [total, setTotal] = useState(0)
  const [pages, setPages] = useState(1)
  const [isLoading, setIsLoading] = useState(false)
  const [error, setError] = useState(null)
  const debounceRef = useRef(null)

  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current)
    }

    debounceRef.current = setTimeout(async () => {
      setIsLoading(true)
      setError(null)
      try {
        const params = new URLSearchParams()
        if (query) params.set('q', query)
        if (type) params.set('type', type)
        params.set('page', String(page || 1))
        const url = `/api/catalog/search?${params.toString()}`
        const response = await authFetch(url)
        if (!response.ok) {
          throw new Error(`Server error ${response.status}`)
        }
        const json = await response.json()
        setResults(Array.isArray(json.items) ? json.items : [])
        setTotal(Number(json.total) || 0)
        setPages(Number(json.pages) || 1)
      } catch (err) {
        setError(err.message)
        setResults([])
        setTotal(0)
        setPages(1)
      } finally {
        setIsLoading(false)
      }
    }, 300)

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query, type, page, authFetch])

  return { results, total, pages, isLoading, error }
}
