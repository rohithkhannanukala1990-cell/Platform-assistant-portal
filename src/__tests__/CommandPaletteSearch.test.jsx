import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CommandPalette from '../components/CommandPalette'

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
  useAuth: () => ({ authFetch: authFetchMock }),
}))

afterEach(() => {
  cleanup()
})

describe('CommandPalette search', () => {
  it('shows Workspace and Agent groups from the backend search endpoint', async () => {
    authFetchMock = vi.fn(async (url) => {
      if (String(url).startsWith('/api/search')) {
        return jsonResponse(200, [
          { type: 'Workspace', id: 'ws-incident', title: 'Incident Response', subtitle: 'production', url: '/workspaces' },
          { type: 'Agent', id: 'incident_agent', title: 'incident_agent', subtitle: 'Triage', url: '/agents' },
        ])
      }
      return jsonResponse(200, [])
    })

    render(
      <MemoryRouter>
        <CommandPalette open onClose={() => {}} />
      </MemoryRouter>
    )

    const input = screen.getByPlaceholderText('Search pages or anything...')
    fireEvent.change(input, { target: { value: 'incident' } })

    await waitFor(() => {
      expect(screen.getAllByText('Workspace').length).toBeGreaterThan(0)
      expect(screen.getAllByText('Agent').length).toBeGreaterThan(0)
    })
    expect(screen.getByText('Incident Response')).toBeTruthy()
    expect(screen.getByText('incident_agent')).toBeTruthy()
  })

  it('static nav list no longer groups Code Editor/Terminal under Labs', () => {
    authFetchMock = vi.fn(async () => jsonResponse(200, []))
    render(
      <MemoryRouter>
        <CommandPalette open onClose={() => {}} />
      </MemoryRouter>
    )
    expect(screen.queryByText('Labs')).toBeNull()
    expect(screen.getByText('Code Editor')).toBeTruthy()
    expect(screen.getByText('Terminal')).toBeTruthy()
  })
})
