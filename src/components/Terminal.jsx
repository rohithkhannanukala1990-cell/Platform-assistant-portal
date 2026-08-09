import { useEffect, useRef, useCallback } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import {
  applyCompletions,
  createLineState,
  handleTerminalData,
  redrawPayload,
} from '../utils/terminalLineEditor'

const WS_BASE = import.meta.env.VITE_WS_URL || 'ws://localhost:8000'
const TOKEN_KEY = 'aiops_access_token'
const SESSION_KEY = 'aiops_terminal_session_id'

function loadSessionId() {
  try {
    return localStorage.getItem(SESSION_KEY) || ''
  } catch {
    return ''
  }
}

function saveSessionId(id) {
  try {
    if (id) localStorage.setItem(SESSION_KEY, id)
  } catch {
    /* ignore */
  }
}

export default function Terminal() {
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const wsRef = useRef(null)
  const fitRef = useRef(null)
  const stateRef = useRef(createLineState())
  const promptRef = useRef('$ ')
  const pendingApprovalRef = useRef(null)
  const awaitingCompleteRef = useRef(false)

  const redraw = useCallback((term, prompt, buffer, cursor) => {
    const { clearLine, cursorBack } = redrawPayload(prompt, buffer, cursor)
    term.write(clearLine + cursorBack)
  }, [])

  const sendJson = useCallback((payload) => {
    const ws = wsRef.current
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(payload))
    }
  }, [])

  const connect = useCallback(() => {
    const term = termRef.current
    if (!term || !containerRef.current) return
    const token = localStorage.getItem(TOKEN_KEY) ?? ''
    const sessionId = loadSessionId()
    const ws = new WebSocket(`${WS_BASE}/ws/terminal`)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({ token, session_id: sessionId || undefined }))
    }

    ws.onmessage = (ev) => {
      let msg
      try {
        msg = JSON.parse(ev.data)
      } catch {
        term.write(ev.data)
        return
      }

      if (msg.type === 'error') {
        term.write(`\r\n\x1b[31m${msg.message || 'Unauthorized'}\x1b[0m\r\n`)
        return
      }

      if (msg.type === 'session') {
        if (msg.session_id) saveSessionId(msg.session_id)
        if (msg.cwd) promptRef.current = `${msg.cwd} $ `
        if (msg.scrollback) term.write(msg.scrollback)
        return
      }

      if (msg.type === 'history' && Array.isArray(msg.data)) {
        stateRef.current.history = msg.data.slice(-100)
        return
      }

      if (msg.type === 'prompt') {
        promptRef.current = msg.prompt || promptRef.current
        const st = stateRef.current
        redraw(term, promptRef.current, st.buffer, st.cursor)
        return
      }

      if (msg.type === 'completions') {
        awaitingCompleteRef.current = false
        const applied = applyCompletions(stateRef.current, msg.options || [], {
          prompt: promptRef.current,
        })
        for (const w of applied.writes) term.write(w)
        return
      }

      if (msg.type === 'approval_required') {
        pendingApprovalRef.current = msg.approval_id
        term.write(
          `\r\n\x1b[33m⏸ Requires approval — request sent (id: ${msg.approval_id}). Waiting… [Ctrl+C to cancel]\x1b[0m\r\n`
        )
        if (Array.isArray(msg.reasons) && msg.reasons.length) {
          term.write(`\x1b[90m${msg.reasons.join('; ')}\x1b[0m\r\n`)
        }
        return
      }

      if (msg.type === 'approval_granted') {
        pendingApprovalRef.current = null
        term.write(`\r\n\x1b[32m✓ Approval granted (${msg.approval_id}). Executing…\x1b[0m\r\n`)
        return
      }

      if (msg.type === 'approval_denied') {
        pendingApprovalRef.current = null
        term.write(
          `\r\n\x1b[31m✗ Approval denied (${msg.approval_id}): ${msg.reason || 'rejected'}\x1b[0m\r\n`
        )
        term.write(promptRef.current)
        return
      }

      if (msg.type === 'idle_warn') {
        term.write(
          `\r\n\x1b[33mSession expires in 60s — press any key to stay connected\x1b[0m\r\n`
        )
        term.write(promptRef.current)
        return
      }

      if (msg.type === 'output' || msg.data != null) {
        term.write(msg.data || '')
        return
      }
    }

    ws.onclose = () => term.write('\r\n\x1b[31mDisconnected. Click Reconnect.\x1b[0m\r\n')
    ws.onerror = () => term.write('\r\n\x1b[31mConnection error.\x1b[0m\r\n')
  }, [redraw])

  useEffect(() => {
    if (!containerRef.current) return
    const term = new XTerm({
      theme: {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#58a6ff',
        selectionBackground: '#264f78',
      },
      fontSize: 14,
      fontFamily: '"Fira Code","Cascadia Code",monospace',
      cursorBlink: true,
      scrollback: 5000,
      allowProposedApi: true,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(containerRef.current)
    fit.fit()
    termRef.current = term
    fitRef.current = fit
    stateRef.current = createLineState()

    const disposable = term.onData((data) => {
      // Ctrl+Shift+V is typically handled by the browser as paste → onData receives text.
      const result = handleTerminalData(stateRef.current, data, {
        prompt: promptRef.current,
      })
      for (const w of result.writes) term.write(w)

      if (result.activity) {
        sendJson({ type: 'activity' })
      }

      if (result.cancelApproval && pendingApprovalRef.current) {
        sendJson({ type: 'cancel_approval', approval_id: pendingApprovalRef.current })
        pendingApprovalRef.current = null
      }

      if (result.prompt) {
        term.write(promptRef.current)
      }

      if (result.submit != null) {
        sendJson({ type: 'command', command: result.submit })
      }

      if (result.complete != null && !awaitingCompleteRef.current) {
        awaitingCompleteRef.current = true
        sendJson({ type: 'complete', partial: result.complete })
      }
    })

    // Copy on selection (standard terminal UX)
    const onSel = term.onSelectionChange(() => {
      const sel = term.getSelection()
      if (sel && navigator.clipboard?.writeText) {
        void navigator.clipboard.writeText(sel).catch(() => {})
      }
    })

    const ro = new ResizeObserver(() => fitRef.current?.fit())
    ro.observe(containerRef.current)
    connect()

    return () => {
      disposable.dispose()
      onSel.dispose()
      ro.disconnect()
      wsRef.current?.close()
      term.dispose()
    }
  }, [connect, sendJson])

  return (
    <div className="flex flex-col h-[calc(100vh-120px)] bg-[#0d1117] rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 bg-card border-b border-border shrink-0">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div className="w-3 h-3 rounded-full bg-green-500" />
        </div>
        <span className="text-gray-400 text-xs ml-2 font-mono">Platform Terminal</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => {
            wsRef.current?.close()
            termRef.current?.clear()
            stateRef.current = createLineState(stateRef.current.history)
            connect()
          }}
          className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
        >
          ↺ Reconnect
        </button>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0 p-1" />
    </div>
  )
}
