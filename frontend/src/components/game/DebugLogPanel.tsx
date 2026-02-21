import { useState, useEffect, useRef, useCallback } from 'react'

interface LogEntry {
  ts: string
  dir: 'send' | 'recv'
  payload: Record<string, unknown>
}

interface Props {
  sessionId: string
  onClose: () => void
}

export function DebugLogPanel({ sessionId, onClose }: Props) {
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const bottomRef = useRef<HTMLDivElement>(null)
  const panelRef = useRef<HTMLDivElement>(null)
  const [autoScroll, setAutoScroll] = useState(true)

  // Dragging state
  const [pos, setPos] = useState({ x: window.innerWidth - 520, y: window.innerHeight - 420 })
  const [size, setSize] = useState({ w: 480, h: 380 })
  const dragRef = useRef<{ startX: number; startY: number; origX: number; origY: number } | null>(null)
  const resizeRef = useRef<{ startX: number; startY: number; origW: number; origH: number } | null>(null)

  const handleDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startY: e.clientY, origX: pos.x, origY: pos.y }
    const onMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      setPos({
        x: dragRef.current.origX + (ev.clientX - dragRef.current.startX),
        y: dragRef.current.origY + (ev.clientY - dragRef.current.startY),
      })
    }
    const onUp = () => {
      dragRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [pos])

  const handleResizeStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
    resizeRef.current = { startX: e.clientX, startY: e.clientY, origW: size.w, origH: size.h }
    const onMove = (ev: MouseEvent) => {
      if (!resizeRef.current) return
      setSize({
        w: Math.max(320, resizeRef.current.origW + (ev.clientX - resizeRef.current.startX)),
        h: Math.max(200, resizeRef.current.origH + (ev.clientY - resizeRef.current.startY)),
      })
    }
    const onUp = () => {
      resizeRef.current = null
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup', onUp)
  }, [size])

  // Fetch existing logs + connect to live stream
  useEffect(() => {
    const accessKey = String(import.meta.env.VITE_ACCESS_KEY || '').trim()
    const authHeaders = accessKey ? { 'X-Access-Key': accessKey } : undefined

    fetch(`/api/sessions/${sessionId}/debug-log`, {
      headers: authHeaders,
    })
      .then((r) => {
        if (!r.ok) {
          throw new Error(`HTTP ${r.status}`)
        }
        return r
      })
      .then((r) => r.json())
      .then((data: LogEntry[]) => setLogs(data))
      .catch(() => {})

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const query = accessKey ? `?access_key=${encodeURIComponent(accessKey)}` : ''
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws/debug-log/${sessionId}${query}`)
    wsRef.current = ws

    ws.onopen = () => setConnected(true)
    ws.onclose = () => setConnected(false)
    ws.onmessage = (event) => {
      try {
        const entry: LogEntry = JSON.parse(event.data)
        setLogs((prev) => [...prev.slice(-199), entry])
      } catch {
        // ignore
      }
    }

    return () => {
      ws.close()
      wsRef.current = null
    }
  }, [sessionId])

  // Auto scroll
  useEffect(() => {
    if (autoScroll && bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const formatPayload = (payload: Record<string, unknown>) => {
    try {
      return JSON.stringify(payload, null, 2)
    } catch {
      return String(payload)
    }
  }

  const formatTime = (ts: string) => {
    try {
      const d = new Date(ts)
      return d.toLocaleTimeString('en-US', { hour12: false, fractionalSecondDigits: 3 })
    } catch {
      return ts
    }
  }

  return (
    <div
      ref={panelRef}
      className="fixed z-[9999] flex flex-col bg-popover border rounded-lg shadow-2xl text-foreground text-xs font-mono"
      style={{ left: pos.x, top: pos.y, width: size.w, height: size.h }}
    >
      {/* Draggable header */}
      <div
        onMouseDown={handleDragStart}
        className="flex items-center justify-between px-3 py-1.5 bg-muted/50 border-b rounded-t-lg cursor-move select-none shrink-0"
      >
        <div className="flex items-center gap-2">
          <span className="text-foreground font-medium">Debug Log</span>
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-red-500'}`} />
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1 text-muted-foreground cursor-pointer">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="accent-emerald-500"
            />
            Auto
          </label>
          <button
            onClick={() => setLogs([])}
            className="px-2 py-0.5 text-muted-foreground hover:text-foreground hover:bg-muted rounded"
          >
            Clear
          </button>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">&times;</button>
        </div>
      </div>

      {/* Log entries */}
      <div className="flex-1 overflow-y-auto px-2 py-1 space-y-0.5">
        {logs.length === 0 && (
          <div className="text-muted-foreground/50 text-center py-4">No log entries yet. Send a message to see events.</div>
        )}
        {logs.map((entry, i) => {
          const isSend = entry.dir === 'send'
          const type = (entry.payload?.type as string) || '?'
          const preview = entry.payload?.preview
          const content = entry.payload?.content
          return (
            <details key={i} className="group">
              <summary className="flex items-center gap-2 py-0.5 px-1 rounded cursor-pointer hover:bg-muted/50">
                <span className="text-muted-foreground/50 w-20 shrink-0">{formatTime(entry.ts)}</span>
                <span className={`w-4 text-center ${isSend ? 'text-blue-400' : 'text-amber-400'}`}>
                  {isSend ? '\u2191' : '\u2193'}
                </span>
                <span className={`px-1.5 py-0 rounded text-[10px] font-medium ${
                  type === 'error' ? 'bg-red-900/50 text-red-400' :
                  type === 'done' ? 'bg-emerald-900/50 text-emerald-400' :
                  type === 'chunk' ? 'bg-muted text-muted-foreground' :
                  type === 'phase_change' ? 'bg-purple-900/50 text-purple-400' :
                  'bg-muted text-muted-foreground'
                }`}>
                  {type}
                </span>
                {type === 'done' && preview != null && (
                  <span className="text-muted-foreground/50 truncate">{String(preview).slice(0, 80)}</span>
                )}
                {type === 'message' && content != null && (
                  <span className="text-muted-foreground/50 truncate">{String(content).slice(0, 80)}</span>
                )}
              </summary>
              <pre className="ml-8 mr-2 mb-1 p-2 bg-muted/50 rounded text-[11px] text-foreground/70 overflow-x-auto whitespace-pre-wrap break-all">
                {formatPayload(entry.payload)}
              </pre>
            </details>
          )
        })}
        <div ref={bottomRef} />
      </div>

      {/* Resize handle */}
      <div
        onMouseDown={handleResizeStart}
        className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize"
        style={{ background: 'linear-gradient(135deg, transparent 50%, #475569 50%)' }}
      />
    </div>
  )
}
