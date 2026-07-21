import { useCallback, useEffect, useState } from 'react'

/**
 * Minimal create-service onboarding surface:
 * loads templates, then applicable golden paths for the selected template.
 */
export default function CreateServiceOnboarding({ authFetch }) {
  const [templates, setTemplates] = useState([])
  const [selectedId, setSelectedId] = useState('')
  const [paths, setPaths] = useState([])
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadTemplates = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch('/api/templates')
      if (!res.ok) {
        setError(`Unable to load templates (${res.status})`)
        setTemplates([])
        return
      }
      setTemplates(await res.json())
    } catch (err) {
      setError(err?.message || 'Unable to load templates')
      setTemplates([])
    } finally {
      setLoading(false)
    }
  }, [authFetch])

  useEffect(() => {
    void loadTemplates()
  }, [loadTemplates])

  useEffect(() => {
    if (!selectedId) {
      setPaths([])
      return
    }

    let cancelled = false
    ;(async () => {
      setError(null)
      try {
        const res = await authFetch(
          `/api/golden-paths/applicable?template_id=${encodeURIComponent(selectedId)}`
        )
        if (!res.ok) {
          if (!cancelled) {
            setError(`Unable to load golden paths (${res.status})`)
            setPaths([])
          }
          return
        }
        const data = await res.json()
        if (!cancelled) setPaths(Array.isArray(data.items) ? data.items : [])
      } catch (err) {
        if (!cancelled) {
          setError(err?.message || 'Unable to load golden paths')
          setPaths([])
        }
      }
    })()

    return () => {
      cancelled = true
    }
  }, [authFetch, selectedId])

  const selected = templates.find((t) => t.id === selectedId)
  const recommendedKeys = selected?.recommended_golden_path_keys || []

  return (
    <div data-testid="create-service-onboarding">
      <h2>Create service</h2>
      {error && (
        <div role="alert" data-testid="create-service-error">
          {error}
        </div>
      )}
      {loading && <p>Loading templates…</p>}
      <label>
        Template
        <select
          aria-label="Template"
          value={selectedId}
          onChange={(e) => setSelectedId(e.target.value)}
        >
          <option value="">Select a template</option>
          {templates.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </label>

      {selected && (
        <section data-testid="recommended-paths">
          <h3>Recommended golden paths</h3>
          {recommendedKeys.length > 0 && (
            <ul data-testid="recommended-keys">
              {recommendedKeys.map((key) => (
                <li key={key}>{key}</li>
              ))}
            </ul>
          )}
          {paths.length === 0 ? (
            <p>No applicable golden paths</p>
          ) : (
            <ul data-testid="applicable-paths">
              {paths.map((path) => (
                <li key={path.id || path.key}>
                  {path.name} ({path.key})
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </div>
  )
}
