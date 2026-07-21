import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ServiceHealthPanel from '../components/ServiceHealthPanel'

afterEach(() => {
  cleanup()
})

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

describe('ServiceHealthPanel', () => {
  it('calls service health and renders standards and scorecards', async () => {
    const authFetch = vi.fn(async () =>
      jsonResponse(200, {
        entity_id: 'ent-1',
        overall_status: 'degraded',
        standards: [{ id: 's1', name: 'Prod Ready', status: 'warn' }],
        scorecards: [{ id: 'c1', name: 'Docs', score: 70, max_score: 100 }],
      })
    )

    render(<ServiceHealthPanel entityId="ent-1" authFetch={authFetch} />)

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith(
        '/api/standards/service/ent-1/health'
      )
    })

    expect(screen.getByTestId('overall-status')).toHaveTextContent('degraded')
    expect(screen.getByTestId('standards-list')).toHaveTextContent('Prod Ready: warn')
    expect(screen.getByTestId('scorecards-list')).toHaveTextContent('Docs: 70/100')
  })

  it('renders empty states when health payload has no rows', async () => {
    const authFetch = vi.fn(async () =>
      jsonResponse(200, {
        entity_id: 'ent-2',
        overall_status: 'good',
        standards: [],
        scorecards: [],
      })
    )

    render(<ServiceHealthPanel entityId="ent-2" authFetch={authFetch} />)

    await waitFor(() => {
      expect(screen.getByTestId('standards-empty')).toBeInTheDocument()
      expect(screen.getByTestId('scorecards-empty')).toBeInTheDocument()
    })
    expect(screen.getByTestId('overall-status')).toHaveTextContent('good')
  })

  it.each([401, 403, 500])(
    'shows an error banner for health status %s',
    async (status) => {
      const authFetch = vi.fn(async () => jsonResponse(status, { detail: 'nope' }))
      render(<ServiceHealthPanel entityId="ent-x" authFetch={authFetch} />)

      await waitFor(() => {
        expect(screen.getByTestId('service-health-error')).toHaveTextContent(
          `Unable to load service health (${status})`
        )
      })
    }
  )
})
