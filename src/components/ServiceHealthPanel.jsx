import { useCallback, useEffect, useState } from 'react'

/**
 * Service details health panel backed by /api/standards/service/:id/health.
 */
export default function ServiceHealthPanel({ entityId, authFetch }) {
  const [health, setHealth] = useState(null)
  const [error, setError] = useState(null)
  const [loading, setLoading] = useState(false)

  const loadHealth = useCallback(async () => {
    if (!entityId) {
      setHealth(null)
      return
    }
    setLoading(true)
    setError(null)
    try {
      const res = await authFetch(
        `/api/standards/service/${encodeURIComponent(entityId)}/health`
      )
      if (!res.ok) {
        setError(`Unable to load service health (${res.status})`)
        setHealth(null)
        return
      }
      setHealth(await res.json())
    } catch (err) {
      setError(err?.message || 'Unable to load service health')
      setHealth(null)
    } finally {
      setLoading(false)
    }
  }, [authFetch, entityId])

  useEffect(() => {
    void loadHealth()
  }, [loadHealth])

  const standards = health?.standards || []
  const scorecards = health?.scorecards || []

  return (
    <div data-testid="service-health-panel">
      <h2>Service health</h2>
      {error && (
        <div role="alert" data-testid="service-health-error">
          {error}
        </div>
      )}
      {loading && <p>Loading health…</p>}
      {!loading && !error && health && (
        <>
          <p data-testid="overall-status">
            Overall: {health.overall_status}
          </p>
          <section>
            <h3>Standards</h3>
            {standards.length === 0 ? (
              <p data-testid="standards-empty">No standards evaluated</p>
            ) : (
              <ul data-testid="standards-list">
                {standards.map((row) => (
                  <li key={row.id}>
                    {row.name}: {row.status}
                  </li>
                ))}
              </ul>
            )}
          </section>
          <section>
            <h3>Scorecards</h3>
            {scorecards.length === 0 ? (
              <p data-testid="scorecards-empty">No scorecard results</p>
            ) : (
              <ul data-testid="scorecards-list">
                {scorecards.map((row) => (
                  <li key={row.id}>
                    {row.name}: {row.score}/{row.max_score}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  )
}
