import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import CreateServiceOnboarding from '../components/CreateServiceOnboarding'

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

describe('CreateServiceOnboarding', () => {
  it('loads templates and applicable golden paths for a selected template', async () => {
    const authFetch = vi.fn(async (url) => {
      if (url === '/api/templates') {
        return jsonResponse(200, [
          {
            id: 'tmpl-1',
            name: 'Service Starter',
            recommended_golden_path_keys: ['create-new-service'],
          },
        ])
      }
      if (url.includes('/api/golden-paths/applicable')) {
        return jsonResponse(200, {
          items: [
            {
              id: '1',
              key: 'create-new-service',
              name: 'Create New Service',
            },
          ],
        })
      }
      return jsonResponse(404, { detail: 'not found' })
    })

    const user = userEvent.setup()
    render(<CreateServiceOnboarding authFetch={authFetch} />)

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith('/api/templates')
    })

    await user.selectOptions(screen.getByLabelText('Template'), 'tmpl-1')

    await waitFor(() => {
      expect(authFetch).toHaveBeenCalledWith(
        '/api/golden-paths/applicable?template_id=tmpl-1'
      )
    })

    expect(screen.getByTestId('recommended-keys')).toHaveTextContent(
      'create-new-service'
    )
    expect(screen.getByTestId('applicable-paths')).toHaveTextContent(
      'Create New Service'
    )
  })

  it.each([401, 403, 500])(
    'shows an error banner when templates return %s',
    async (status) => {
      const authFetch = vi.fn(async () => jsonResponse(status, { detail: 'nope' }))
      render(<CreateServiceOnboarding authFetch={authFetch} />)

      await waitFor(() => {
        expect(screen.getByTestId('create-service-error')).toHaveTextContent(
          `Unable to load templates (${status})`
        )
      })
    }
  )

  it('shows an error banner when applicable golden paths fail', async () => {
    const authFetch = vi.fn(async (url) => {
      if (url === '/api/templates') {
        return jsonResponse(200, [
          { id: 'tmpl-1', name: 'Service Starter', recommended_golden_path_keys: [] },
        ])
      }
      return jsonResponse(403, { detail: 'Forbidden' })
    })

    const user = userEvent.setup()
    render(<CreateServiceOnboarding authFetch={authFetch} />)
    await waitFor(() => expect(screen.getByLabelText('Template')).toBeInTheDocument())
    await user.selectOptions(screen.getByLabelText('Template'), 'tmpl-1')

    await waitFor(() => {
      expect(screen.getByTestId('create-service-error')).toHaveTextContent(
        'Unable to load golden paths (403)'
      )
    })
  })
})
