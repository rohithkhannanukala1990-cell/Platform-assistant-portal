import { useEffect, useRef, useCallback } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'

const WS_BASE = (import.meta.env.VITE_WS_URL || 'ws://localhost:8000')
const TOKEN_KEY = 'aiops_access_token'

export default function Terminal() {
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const wsRef = useRef(null)
  const fitRef = useRef(null)
  const inputRef = useRef('')

  const connect = useCallback(() => {
    const term = termRef.current
    if (!term || !containerRef.current) return
    const token = localStorage.getItem(TOKEN_KEY) ?? ''
    // JWT is sent in the first message after open — never in the URL (proxy logs).
    const ws = new WebSocket(`${WS_BASE}/ws/terminal`)
    wsRef.current = ws
    ws.onopen = () => {
      ws.send(JSON.stringify({ token }))
      term.write('\x1b[32mConnected\x1b[0m\r\n')
    }
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data)
        if (msg.type === 'error') {
          term.write(`\r\n\x1b[31m${msg.message || 'Unauthorized'}\x1b[0m\r\n`)
          return
        }
        term.write(msg.data || ev.data)
      } catch {
        term.write(ev.data)
      }
    }
    ws.onclose = () => term.write('\r\n\x1b[31mDisconnected. Click Reconnect.\x1b[0m\r\n')
    ws.onerror = () => term.write('\r\n\x1b[31mConnection error.\x1b[0m\r\n')
  }, [])

  useEffect(() => {
    if (!containerRef.current) return
    const term = new XTerm({
      theme: { background:'#0d1117', foreground:'#c9d1d9',
               cursor:'#58a6ff', selectionBackground:'#264f78' },
      fontSize: 14,
      fontFamily: '"Fira Code","Cascadia Code",monospace',
      cursorBlink: true,
      scrollback: 1000,
    })
    const fit = new FitAddon()
    term.loadAddon(fit)
    term.open(containerRef.current)
    fit.fit()
    termRef.current = term
    fitRef.current = fit

    term.onKey(({ key, domEvent }) => {
      const code = domEvent.keyCode
      if (code === 13) {
        const cmd = inputRef.current
        inputRef.current = ''
        term.write('\r\n')
        if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(cmd)
      } else if (code === 8) {
        if (inputRef.current.length > 0) {
          inputRef.current = inputRef.current.slice(0, -1)
          term.write('\b \b')
        }
      } else if (code === 67 && domEvent.ctrlKey) {
        inputRef.current = ''
        term.write('^C\r\n$ ')
      } else {
        inputRef.current += key
        term.write(key)
      }
    })

    const ro = new ResizeObserver(() => fitRef.current?.fit())
    ro.observe(containerRef.current)
    connect()

    return () => { ro.disconnect(); wsRef.current?.close(); term.dispose() }
  }, [connect])

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
          onClick={() => { wsRef.current?.close(); termRef.current?.clear(); connect() }}
          className="text-xs text-gray-400 hover:text-white px-2 py-1 rounded hover:bg-gray-700 transition-colors"
        >
          ↺ Reconnect
        </button>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0 p-1" />
    </div>
  )
}
