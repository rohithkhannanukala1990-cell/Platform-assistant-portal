import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import CodeEditor from '../components/CodeEditor'

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  }
}

vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }) => (
    <textarea data-testid="monaco" value={value} onChange={(e) => onChange?.(e.target.value)} />
  ),
  DiffEditor: () => <div data-testid="diff-editor" />,
}))

vi.mock('../components/editor/EditorAgentPanel', () => ({
  default: () => null,
  SuggestedEditCard: () => null,
}))

let fetchImpl

vi.mock('../utils/api', () => ({
  authFetch: (...args) => fetchImpl(...args),
}))

afterEach(() => {
  cleanup()
})

describe('CodeEditor GitHub connection state', () => {
  it('shows a CTA card (not a raw error) when GitHub is not connected', async () => {
    fetchImpl = vi.fn(async (url) => {
      if (url === '/api/tools/github/accounts') return jsonResponse(200, [])
      if (url === '/api/editor/files') return jsonResponse(200, [])
      if (url === '/api/editor/templates') return jsonResponse(200, [])
      if (url === '/api/user-prefs/editor_hint_dismissed') return jsonResponse(200, { value: '1' })
      return jsonResponse(200, {})
    })

    render(
      <MemoryRouter>
        <CodeEditor />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.getByTestId('github-not-connected')).toBeTruthy()
    })
    expect(screen.getByText(/Repo browsing needs a GitHub connection/i)).toBeTruthy()
    expect(screen.getByText(/Local files above work fully/i)).toBeTruthy()
  })

  it('shows the normal repo browser when GitHub is connected', async () => {
    fetchImpl = vi.fn(async (url) => {
      if (url === '/api/tools/github/accounts') {
        return jsonResponse(200, [{ status: 'connected' }])
      }
      if (url === '/api/editor/files') return jsonResponse(200, [])
      if (url === '/api/editor/templates') return jsonResponse(200, [])
      if (url === '/api/user-prefs/editor_hint_dismissed') return jsonResponse(200, { value: '1' })
      return jsonResponse(200, {})
    })

    render(
      <MemoryRouter>
        <CodeEditor />
      </MemoryRouter>
    )

    await waitFor(() => {
      expect(screen.queryByTestId('github-not-connected')).toBeNull()
    })
    expect(screen.getByPlaceholderText('org/repo')).toBeTruthy()
  })
})
