// src/hooks/usePortalWebSocket.js
import { useEffect, useRef, useCallback, useState } from 'react'
import { API_BASE } from '../config/apiBase'

const MAX_RETRIES = 5
const BASE_MS = 1000

function buildPortalWsUrl(userId) {
  const qs = `user_id=${encodeURIComponent(userId)}`
  if (API_BASE) {
    try {
      const u = new URL(API_BASE.startsWith('http') ? API_BASE : `http://${API_BASE}`)
      u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:'
      u.pathname = '/ws/portal'
      u.search = qs
      u.hash = ''
      return u.toString()
    } catch {
      /* fall through */
    }
  }
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  return `${proto}://${window.location.host}/ws/portal?${qs}`
}

export function usePortalWebSocket({
  userId = 'anonymous',
  onMessage,
  onConnectedChange,
  onOpen,
  onClose,
}) {
  const wsRef = useRef(null)
  const retriesRef = useRef(0)
  const unmountedRef = useRef(false)
  const [connected, setConnected] = useState(false)

  const setConnectionState = useCallback(
    (value) => {
      setConnected(value)
      onConnectedChange?.(value)
    },
    [onConnectedChange]
  )

  const connect = useCallback(() => {
    if (unmountedRef.current) return
    const ws = new WebSocket(buildPortalWsUrl(userId))
    wsRef.current = ws

    ws.onopen = () => {
      retriesRef.current = 0
      setConnectionState(true)
      onOpen?.()
    }

    ws.onmessage = (e) => {
      try {
        onMessage?.(JSON.parse(e.data))
      } catch {
        /* ignore */
      }
    }

    ws.onclose = () => {
      setConnectionState(false)
      onClose?.()
      if (unmountedRef.current) return
      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_MS * 2 ** retriesRef.current
        retriesRef.current += 1
        setTimeout(connect, delay)
      }
    }

    ws.onerror = () => ws.close()
  }, [userId, onMessage, setConnectionState, onOpen, onClose])

  useEffect(() => {
    unmountedRef.current = false
    connect()
    return () => {
      unmountedRef.current = true
      wsRef.current?.close()
    }
  }, [connect])

  return { wsRef, connected }
}
