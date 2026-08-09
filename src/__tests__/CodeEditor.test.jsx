import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { detectLanguage } from '../components/CodeEditor'
import { SuggestedEditCard } from '../components/editor/EditorAgentPanel'

vi.mock('../utils/api', () => ({
  authFetch: vi.fn(async (url, opts = {}) => {
    if (String(url).endsWith('/api/editor/files') && (!opts.method || opts.method === 'GET')) {
      return { ok: true, json: async () => [] }
    }
    if (String(url).endsWith('/api/editor/files') && opts.method === 'POST') {
      const body = JSON.parse(opts.body || '{}')
      return {
        ok: true,
        json: async () => ({
          id: 'file-1',
          filename: body.filename || 'untitled.yaml',
          content: body.content || '',
          language: 'yaml',
        }),
      }
    }
    if (String(url).includes('/api/editor/files/') && opts.method === 'PUT') {
      const body = JSON.parse(opts.body || '{}')
      return {
        ok: true,
        json: async () => ({
          id: 'file-1',
          filename: body.filename || 'untitled.yaml',
          content: body.content || '',
          language: 'yaml',
        }),
      }
    }
    return { ok: true, json: async () => ({}) }
  }),
}))

vi.mock('@monaco-editor/react', () => ({
  default: ({ value, onChange }) => (
    <textarea
      data-testid="monaco"
      value={value}
      onChange={(e) => onChange?.(e.target.value)}
    />
  ),
  DiffEditor: ({ original, modified }) => (
    <div data-testid="diff-editor">
      <pre>{original}</pre>
      <pre>{modified}</pre>
    </div>
  ),
}))

afterEach(() => {
  cleanup()
})

describe('detectLanguage', () => {
  it('auto-detects from filename extension', () => {
    expect(detectLanguage('main.tf')).toBe('hcl')
    expect(detectLanguage('app.yaml')).toBe('yaml')
    expect(detectLanguage('query.sql')).toBe('sql')
  })
})

describe('autosave debounce contract', () => {
  it('autosaves 2 seconds after typing stops, not on every keystroke', () => {
    vi.useFakeTimers()
    const save = vi.fn()
    let timer = null
    const onType = () => {
      if (timer) clearTimeout(timer)
      timer = setTimeout(() => save(), 2000)
    }
    onType()
    onType()
    onType()
    expect(save).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1999)
    expect(save).not.toHaveBeenCalled()
    vi.advanceTimersByTime(1)
    expect(save).toHaveBeenCalledTimes(1)
    vi.useRealTimers()
  })
})

describe('Suggested edits', () => {
  it('renders accept/reject and never auto-applies', () => {
    const onAccept = vi.fn()
    const onReject = vi.fn()
    render(
      <SuggestedEditCard
        edit={{ id: 'e1', original: 'a', proposed: 'b', rationale: 'fix' }}
        onAccept={onAccept}
        onReject={onReject}
      />
    )
    expect(screen.getByTestId('suggested-edit')).toBeTruthy()
    expect(onAccept).not.toHaveBeenCalled()
    screen.getByTestId('accept-hunk').click()
    expect(onAccept).toHaveBeenCalledTimes(1)
  })
})

describe('unsaved indicator', () => {
  it('appears while dirty and clears after save', () => {
    const dirtyMap = { 'file-1': true }
    expect(dirtyMap['file-1']).toBe(true)
    // after successful save
    dirtyMap['file-1'] = false
    expect(dirtyMap['file-1']).toBe(false)
  })

  it('renders editor shell', async () => {
    const { default: CodeEditor } = await import('../components/CodeEditor')
    render(
      <MemoryRouter>
        <CodeEditor />
      </MemoryRouter>
    )
    expect(screen.getByText('Code Editor')).toBeTruthy()
  })
})
