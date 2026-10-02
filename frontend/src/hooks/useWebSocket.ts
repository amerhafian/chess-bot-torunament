import { useEffect, useRef, useState } from 'react'
import { wsUrl } from '../api'

export function useWebSocket<T>(path: string | null, onMessage: (data: T) => void) {
  const [connected, setConnected] = useState(false)
  const handler = useRef(onMessage)
  handler.current = onMessage

  useEffect(() => {
    if (!path) return
    const ws = new WebSocket(wsUrl(path))
    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (ev) => {
      try {
        handler.current(JSON.parse(ev.data) as T)
      } catch {
        /* ignore */
      }
    }
    const ping = window.setInterval(() => {
      if (ws.readyState === WebSocket.OPEN) ws.send('ping')
    }, 20000)
    return () => {
      window.clearInterval(ping)
      ws.close()
      setConnected(false)
    }
  }, [path])

  return connected
}
