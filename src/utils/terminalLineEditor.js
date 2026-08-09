/**
 * Pure terminal line-editing state machine (no xterm dependency).
 * Used by Terminal.jsx and unit tests.
 */

export function createLineState(history = []) {
  return {
    buffer: '',
    cursor: 0,
    history: Array.isArray(history) ? [...history] : [],
    historyIdx: -1,
    stash: '',
  }
}

export function redrawPayload(prompt, buffer, cursor) {
  const back = Math.max(0, buffer.length - cursor)
  return {
    clearLine: '\r\x1b[K' + prompt + buffer,
    cursorBack: back > 0 ? `\x1b[${back}D` : '',
  }
}

function pushHistory(state, cmd) {
  const trimmed = (cmd || '').trim()
  if (!trimmed) return
  const next = state.history.filter((h) => h !== trimmed)
  next.push(trimmed)
  state.history = next.slice(-100)
  state.historyIdx = -1
  state.stash = ''
}

/**
 * Apply one onData chunk. Returns list of side-effect intents.
 * @returns {{ writes: string[], submit?: string, complete?: string, cancelApproval?: boolean, activity?: boolean }}
 */
export function handleTerminalData(state, data, { prompt = '$ ' } = {}) {
  const out = { writes: [], activity: true }

  // Multi-char paste / CSI sequences
  if (data.length > 1 && !data.startsWith('\x1b')) {
    // Plain paste
    const before = state.buffer.slice(0, state.cursor)
    const after = state.buffer.slice(state.cursor)
    const cleaned = data.replace(/\r\n/g, '\n').replace(/\r/g, '\n')
    if (cleaned.includes('\n')) {
      // Paste with newlines: take first line as buffer append, ignore rest for simplicity
      const [first, ...rest] = cleaned.split('\n')
      state.buffer = before + first + after
      state.cursor = before.length + first.length
      const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
      out.writes.push(clearLine + cursorBack)
      if (rest.some((r) => r.length)) {
        // ignore remaining lines in paste (shell-like)
      }
      return out
    }
    state.buffer = before + cleaned + after
    state.cursor = before.length + cleaned.length
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }

  // Escape sequences (arrows, home/end, delete)
  if (data.startsWith('\x1b')) {
    if (data === '\x1b[A') {
      // Up — history
      if (!state.history.length) return out
      if (state.historyIdx === -1) {
        state.stash = state.buffer
        state.historyIdx = state.history.length - 1
      } else if (state.historyIdx > 0) {
        state.historyIdx -= 1
      }
      state.buffer = state.history[state.historyIdx] || ''
      state.cursor = state.buffer.length
      const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
      out.writes.push(clearLine + cursorBack)
      return out
    }
    if (data === '\x1b[B') {
      // Down
      if (state.historyIdx === -1) return out
      if (state.historyIdx < state.history.length - 1) {
        state.historyIdx += 1
        state.buffer = state.history[state.historyIdx] || ''
      } else {
        state.historyIdx = -1
        state.buffer = state.stash || ''
      }
      state.cursor = state.buffer.length
      const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
      out.writes.push(clearLine + cursorBack)
      return out
    }
    if (data === '\x1b[D') {
      // Left
      if (state.cursor > 0) {
        state.cursor -= 1
        out.writes.push('\x1b[D')
      }
      return out
    }
    if (data === '\x1b[C') {
      // Right
      if (state.cursor < state.buffer.length) {
        state.cursor += 1
        out.writes.push('\x1b[C')
      }
      return out
    }
    if (data === '\x1b[H' || data === '\x1b[1~') {
      // Home
      if (state.cursor > 0) {
        out.writes.push(`\x1b[${state.cursor}D`)
        state.cursor = 0
      }
      return out
    }
    if (data === '\x1b[F' || data === '\x1b[4~') {
      // End
      const dist = state.buffer.length - state.cursor
      if (dist > 0) {
        out.writes.push(`\x1b[${dist}C`)
        state.cursor = state.buffer.length
      }
      return out
    }
    if (data === '\x1b[3~') {
      // Delete forward
      if (state.cursor < state.buffer.length) {
        state.buffer = state.buffer.slice(0, state.cursor) + state.buffer.slice(state.cursor + 1)
        const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
        out.writes.push(clearLine + cursorBack)
      }
      return out
    }
    // Unknown escape — ignore (do not echo)
    return out
  }

  // Ctrl keys / specials
  if (data === '\r' || data === '\n') {
    const cmd = state.buffer
    pushHistory(state, cmd)
    state.buffer = ''
    state.cursor = 0
    out.writes.push('\r\n')
    out.submit = cmd
    return out
  }

  if (data === '\x7f' || data === '\b') {
    // Backspace
    if (state.cursor > 0) {
      state.buffer = state.buffer.slice(0, state.cursor - 1) + state.buffer.slice(state.cursor)
      state.cursor -= 1
      const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
      out.writes.push(clearLine + cursorBack)
    }
    return out
  }

  if (data === '\t') {
    out.complete = state.buffer
    return out
  }

  if (data === '\x01') {
    // Ctrl+A
    if (state.cursor > 0) {
      out.writes.push(`\x1b[${state.cursor}D`)
      state.cursor = 0
    }
    return out
  }

  if (data === '\x05') {
    // Ctrl+E
    const dist = state.buffer.length - state.cursor
    if (dist > 0) {
      out.writes.push(`\x1b[${dist}C`)
      state.cursor = state.buffer.length
    }
    return out
  }

  if (data === '\x15') {
    // Ctrl+U clear line
    state.buffer = ''
    state.cursor = 0
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }

  if (data === '\x17') {
    // Ctrl+W delete previous word
    if (state.cursor === 0) return out
    let i = state.cursor - 1
    while (i >= 0 && state.buffer[i] === ' ') i -= 1
    while (i >= 0 && state.buffer[i] !== ' ') i -= 1
    const cut = i + 1
    state.buffer = state.buffer.slice(0, cut) + state.buffer.slice(state.cursor)
    state.cursor = cut
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }

  if (data === '\x0c') {
    // Ctrl+L clear screen, keep buffer
    out.writes.push('\x1b[2J\x1b[H')
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }

  if (data === '\x03') {
    // Ctrl+C
    out.writes.push('^C\r\n')
    state.buffer = ''
    state.cursor = 0
    state.historyIdx = -1
    out.cancelApproval = true
    out.prompt = true
    return out
  }

  // Printable single char
  if (data.length === 1 && data >= ' ') {
    state.buffer = state.buffer.slice(0, state.cursor) + data + state.buffer.slice(state.cursor)
    state.cursor += 1
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }

  return out
}

export function applyCompletions(state, options, { prompt = '$ ' } = {}) {
  const opts = (options || []).filter(Boolean)
  const out = { writes: [] }
  if (!opts.length) return out
  if (opts.length === 1) {
    const parts = state.buffer.split(/\s+/)
    const partial = parts[parts.length - 1] || ''
    const match = opts[0]
    const completed = match.startsWith(partial) ? match.slice(partial.length) : match
    // Replace last token
    const prefix = state.buffer.slice(0, state.buffer.length - partial.length)
    state.buffer = prefix + match + (match.endsWith('/') ? '' : '')
    if (!state.buffer.endsWith(' ') && !match.endsWith('/')) {
      // leave as-is; user can continue typing
    }
    state.cursor = state.buffer.length
    void completed
    const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
    out.writes.push(clearLine + cursorBack)
    return out
  }
  out.writes.push('\r\n' + opts.join('  ') + '\r\n')
  const { clearLine, cursorBack } = redrawPayload(prompt, state.buffer, state.cursor)
  out.writes.push(clearLine + cursorBack)
  return out
}
