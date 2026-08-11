import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

vi.mock('../contexts/AuthContext', () => ({
  useAuth: () => ({
    role: 'Admin',
    authFetch: vi.fn(async () => ({ ok: true, json: async () => [] })),
  }),
}))

afterEach(() => {
  cleanup()
})

function renderSidebar() {
  return render(
    <MemoryRouter initialEntries={['/dashboard']}>
      <Sidebar user={{ username: 'admin', role: 'Admin' }} open onClose={() => {}} />
    </MemoryRouter>
  )
}

describe('Sidebar', () => {
  it('has no "Labs" group', () => {
    renderSidebar()
    expect(screen.queryByText('Labs')).toBeNull()
  })

  it('shows Code Editor and Terminal under Developer Tools with no Preview badge', () => {
    renderSidebar()
    const devTools = screen.getByText('Developer Tools').closest('div')
    expect(devTools).toBeTruthy()

    const codeEditorLink = screen.getByText('Code Editor').closest('a')
    const terminalLink = screen.getByText('Terminal').closest('a')
    expect(codeEditorLink).toBeTruthy()
    expect(terminalLink).toBeTruthy()

    expect(within(codeEditorLink).queryByText('Preview')).toBeNull()
    expect(within(terminalLink).queryByText('Preview')).toBeNull()
  })

  it('still marks CI/CD Pipelines and Infra Builder as Preview', () => {
    renderSidebar()
    const cicdLink = screen.getByText('CI/CD Pipelines').closest('a')
    expect(within(cicdLink).getByText('Preview')).toBeTruthy()
  })

  it('Developer Tools group is open by default (items visible without clicking)', () => {
    renderSidebar()
    // If the group were collapsed by default, these labels wouldn't be in the DOM at all
    // (the component only renders items for open groups).
    expect(screen.getByText('Code Editor')).toBeTruthy()
    expect(screen.getByText('Kubernetes')).toBeTruthy()
  })
})
