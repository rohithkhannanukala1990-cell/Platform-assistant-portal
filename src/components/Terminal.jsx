import { useEffect, useRef, useCallback } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { API_BASE } from '../config/apiBase'

const TOKEN_KEY = 'aiops_access_token'

function buildTerminalWsUrl(token) {
  const qs = `token=${encodeURIComponent(token || '')}`
  if (API_BASE) {
    try {
      const u = new URL(API_BASE.startsWith('http') ? API_BASE : `http://${API_BASE}`)
      u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
      u.pathname = '/ws/terminal'
      u.search = qs
      u.hash = ''
      return u.toString()
    } catch {
      /* fall through */
    }
  }
  const proto = typeof window !== 'undefined' && window.location.protocol === 'https:' ? 'wss' : 'ws'
  const host = typeof window !== 'undefined' ? window.location.host : 'localhost:8000'
  return `${proto}://${host}/ws/terminal?${qs}`
}

export default function Terminal() {
  const containerRef = useRef(null)
  const termRef = useRef(null)
  const wsRef = useRef(null)
  const fitAddonRef = useRef(null)
  const inputBufferRef = useRef('')

  const getToken = useCallback(() => {
    try {
      return localStorage.getItem(TOKEN_KEY) || ''
    } catch {
      return ''
    }
  }, [])

  useEffect(() => {
    const term = new XTerm({
      theme: {
        background: '#0d1117',
        foreground: '#c9d1d9',
        cursor: '#58a6ff',
        selectionBackground: '#264f78',
      },
      fontSize: 14,
      fontFamily: '"Fira Code", "Cascadia Code", monospace',
      cursorBlink: true,
      scrollback: 1000,
    })
    const fitAddon = new FitAddon()
    term.loadAddon(fitAddon)
    if (containerRef.current) {
      term.open(containerRef.current)
      fitAddon.fit()
    }
    termRef.current = term
    fitAddonRef.current = fitAddon

    const token = getToken()
    const ws = new WebSocket(buildTerminalWsUrl(token))
    wsRef.current = ws

    ws.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data)
        if (msg.type === 'output' || msg.type === 'error') {
          term.write(msg.data || msg.message || '')
        }
      } catch {
        term.write(event.data)
      }
    }

    ws.onclose = () => {
      term.write('\r\n\x1b[31mDisconnected.\x1b[0m\r\n')
    }

    ws.onerror = () => {
      term.write('\r\n\x1b[31mConnection error.\x1b[0m\r\n')
    }

    term.onKey(({ key, domEvent }) => {
      const code = domEvent.keyCode
      if (code === 13) {
        const cmd = inputBufferRef.current
        inputBufferRef.current = ''
        term.write('\r\n')
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(cmd)
        }
      } else if (code === 8) {
        if (inputBufferRef.current.length > 0) {
          inputBufferRef.current = inputBufferRef.current.slice(0, -1)
          term.write('\b \b')
        }
      } else if (code === 67 && domEvent.ctrlKey) {
        inputBufferRef.current = ''
        term.write('^C\r\n$ ')
      } else {
        inputBufferRef.current += key
        term.write(key)
      }
    })

    const ro = new ResizeObserver(() => {
      try {
        fitAddon.fit()
      } catch {
        /* ignore */
      }
    })
    if (containerRef.current) ro.observe(containerRef.current)

    return () => {
      ro.disconnect()
      try {
        ws.close()
      } catch {
        /* ignore */
      }
      term.dispose()
    }
  }, [getToken])

  return (
    <div className="flex flex-col h-full bg-[#0d1117] rounded-xl overflow-hidden">
      <div className="flex items-center gap-2 px-4 py-2 bg-gray-800 border-b border-gray-700">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500" />
          <div className="w-3 h-3 rounded-full bg-yellow-500" />
          <div className="w-3 h-3 rounded-full bg-green-500" />
        </div>
        <span className="text-gray-400 text-xs ml-2">Platform Terminal</span>
        <div className="flex-1" />
        <button
          type="button"
          onClick={() => {
            if (wsRef.current) {
              try {
                wsRef.current.close()
              } catch {
                /* ignore */
              }
            }
            window.location.reload()
          }}
          className="text-xs text-gray-400 hover:text-white px-2 py-1"
        >
          ↺ Reconnect
        </button>
      </div>
      <div ref={containerRef} className="flex-1 min-h-0 p-2" />
    </div>
  )
}
