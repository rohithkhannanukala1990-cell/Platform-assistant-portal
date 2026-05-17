// src/hooks/usePortalWebSocket.js
import { useEffect, useRef, useCallback, useState } from 'react'

const MAX_RETRIES = 5
const BASE_DELAY_MS = 1000

export function usePortalWebSocket({ userId = 'anonymous', onMessage, onConnectedChange }) {
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
    const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const host = window.location.host
    const url = `${proto}://${host}/ws/portal?user_id=${encodeURIComponent(userId)}`
    const ws = new WebSocket(url)
    wsRef.current = ws

    ws.onopen = () => {
      retriesRef.current = 0
      setConnectionState(true)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        onMessage?.(data)
      } catch {
        // ignore malformed
      }
    }

    ws.onclose = () => {
      setConnectionState(false)
      if (unmountedRef.current) return
      if (retriesRef.current < MAX_RETRIES) {
        const delay = BASE_DELAY_MS * 2 ** retriesRef.current
        retriesRef.current += 1
        setTimeout(connect, delay)
      }
    }

    ws.onerror = () => ws.close()
  }, [userId, onMessage, setConnectionState])

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
