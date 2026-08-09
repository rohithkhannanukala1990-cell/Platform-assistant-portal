import { describe, expect, it, vi } from 'vitest'
import {
  applyCompletions,
  createLineState,
  handleTerminalData,
} from '../utils/terminalLineEditor'

describe('terminal line editor', () => {
  it('moves cursor left/right without echoing escape codes into the buffer', () => {
    const state = createLineState()
    handleTerminalData(state, 'ab', { prompt: '$ ' })
    expect(state.buffer).toBe('ab')
    expect(state.cursor).toBe(2)

    const left = handleTerminalData(state, '\x1b[D', { prompt: '$ ' })
    expect(state.cursor).toBe(1)
    expect(state.buffer).toBe('ab')
    expect(left.writes.some((w) => w.includes('\x1b[D'))).toBe(true)
    expect(state.buffer.includes('\x1b')).toBe(false)

    const right = handleTerminalData(state, '\x1b[C', { prompt: '$ ' })
    expect(state.cursor).toBe(2)
    expect(right.writes.some((w) => w.includes('\x1b[C'))).toBe(true)
  })

  it('recalls previous command with up arrow', () => {
    const state = createLineState(['echo one', 'echo two'])
    const res = handleTerminalData(state, '\x1b[A', { prompt: '$ ' })
    expect(state.buffer).toBe('echo two')
    expect(state.cursor).toBe('echo two'.length)
    expect(res.writes.length).toBeGreaterThan(0)
  })

  it('backspace deletes at the cursor, not only at the end', () => {
    const state = createLineState()
    handleTerminalData(state, 'abcd', { prompt: '$ ' })
    handleTerminalData(state, '\x1b[D', { prompt: '$ ' }) // cursor between c and d
    handleTerminalData(state, '\x7f', { prompt: '$ ' }) // delete 'c'
    expect(state.buffer).toBe('abd')
    expect(state.cursor).toBe(2)
  })

  it('paste via onData inserts text correctly', () => {
    const state = createLineState()
    handleTerminalData(state, 'hello', { prompt: '$ ' })
    handleTerminalData(state, '\x1b[D', { prompt: '$ ' })
    handleTerminalData(state, '\x1b[D', { prompt: '$ ' })
    handleTerminalData(state, 'XX', { prompt: '$ ' })
    expect(state.buffer).toBe('helXXlo')
    expect(state.cursor).toBe(5)
  })

  it('Ctrl+U clears the line', () => {
    const state = createLineState()
    handleTerminalData(state, 'kubectl get pods', { prompt: '$ ' })
    const res = handleTerminalData(state, '\x15', { prompt: '$ ' })
    expect(state.buffer).toBe('')
    expect(state.cursor).toBe(0)
    expect(res.writes.join('')).toContain('\x1b[K')
  })

  it('Tab requests completion (does not mutate buffer alone)', () => {
    const state = createLineState()
    handleTerminalData(state, 'kubectl get po', { prompt: '$ ' })
    const res = handleTerminalData(state, '\t', { prompt: '$ ' })
    expect(res.complete).toBe('kubectl get po')
    expect(state.buffer).toBe('kubectl get po')
  })

  it('applyCompletions with one option completes inline', () => {
    const state = createLineState()
    state.buffer = 'kubectl get po'
    state.cursor = state.buffer.length
    const res = applyCompletions(state, ['pods'], { prompt: '$ ' })
    expect(state.buffer).toContain('pods')
    expect(res.writes.length).toBeGreaterThan(0)
  })

  it('Enter submits and pushes history', () => {
    const state = createLineState()
    handleTerminalData(state, 'ls', { prompt: '$ ' })
    const res = handleTerminalData(state, '\r', { prompt: '$ ' })
    expect(res.submit).toBe('ls')
    expect(state.history).toContain('ls')
    expect(state.buffer).toBe('')
  })
})

describe('Terminal WebSocket complete message shape', () => {
  it('documents that Tab sends a complete message', () => {
    const send = vi.fn()
    const state = createLineState()
    handleTerminalData(state, 'hel', { prompt: '$ ' })
    const res = handleTerminalData(state, '\t', { prompt: '$ ' })
    if (res.complete != null) {
      send(JSON.stringify({ type: 'complete', partial: res.complete }))
    }
    expect(send).toHaveBeenCalledWith(
      JSON.stringify({ type: 'complete', partial: 'hel' })
    )
  })
})
