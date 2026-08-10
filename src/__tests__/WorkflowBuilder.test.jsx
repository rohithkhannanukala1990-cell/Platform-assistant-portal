import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import WorkflowBuilder from '../components/workflows/WorkflowBuilder'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

let authFetchMock

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({ authFetch: authFetchMock, role: 'Admin' }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

function renderBuilder(path = '/workflows/builder/new') {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/workflows/builder/:workflowId" element={<WorkflowBuilder />} />
      </Routes>
    </MemoryRouter>
  )
}

describe('WorkflowBuilder', () => {
  it('disables dry-run until the workflow has been saved', async () => {
    authFetchMock = vi.fn(async (url) => {
      if (String(url) === '/api/agents/') return jsonResponse(200, [])
      if (String(url) === '/api/connectors') return jsonResponse(200, [])
      return jsonResponse(200, {})
    })
    renderBuilder('/workflows/builder/new')

    await waitFor(() => expect(screen.getByText('New workflow')).toBeTruthy())
    const dryRunButton = screen.getByRole('button', { name: /dry-run/i })
    expect(dryRunButton).toBeDisabled()
  })

  it('maps validation errors from the API back to the specific step', async () => {
    authFetchMock = vi.fn(async (url, opts = {}) => {
      const method = (opts.method || 'GET').toUpperCase()
      if (String(url) === '/api/agents/') return jsonResponse(200, [])
      if (String(url) === '/api/connectors') return jsonResponse(200, [])
      if (String(url) === '/api/workflows/validate' && method === 'POST') {
        return {
          ok: false,
          status: 422,
          json: async () => ({
            detail: [
              "step s1: write connector method 'deploy' requires a preceding hitl gate",
            ],
          }),
        }
      }
      return jsonResponse(200, {})
    })
    renderBuilder('/workflows/builder/new')

    await waitFor(() => expect(screen.getByText('New workflow')).toBeTruthy())

    fireEvent.click(screen.getByRole('button', { name: /^validate$/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/requires a preceding hitl gate/i)
      ).toBeTruthy()
    })
    // Error is attached inline to the step card, not a bare top-level banner.
    expect(screen.queryAllByText(/requires a preceding hitl gate/i)).toHaveLength(1)
  })

  it('enables dry-run once the workflow has a saved id', async () => {
    authFetchMock = vi.fn(async (url) => {
      if (String(url) === '/api/agents/') return jsonResponse(200, [])
      if (String(url) === '/api/connectors') return jsonResponse(200, [])
      if (String(url) === '/api/workflows/existing-id') {
        return jsonResponse(200, {
          id: 'existing-id',
          name: 'Saved workflow',
          description: '',
          trigger_type: 'manual',
          trigger_config: {},
          enabled: true,
          risk: 'medium',
          max_runs_per_hour: 12,
          max_concurrent_runs: 1,
          on_concurrent_limit: 'drop',
          steps: [{ id: 's1', type: 'hitl', prompt: 'Approve?', depends_on: [] }],
          first_live_run_approved_at: null,
        })
      }
      return jsonResponse(200, {})
    })
    renderBuilder('/workflows/builder/existing-id')

    await waitFor(() => expect(screen.getByText(/Edit: Saved workflow/)).toBeTruthy())
    const dryRunButton = screen.getByRole('button', { name: /dry-run/i })
    expect(dryRunButton).not.toBeDisabled()
  })
})
