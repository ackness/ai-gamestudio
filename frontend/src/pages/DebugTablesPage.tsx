import { useState, useEffect } from 'react'
import { useParams, Link } from 'react-router-dom'

interface TableData {
  [key: string]: unknown
}

interface SessionTables {
  session: TableData
  tables: Record<string, TableData[]>
}

const tableLabels: Record<string, string> = {
  characters: '角色 Characters',
  messages: '消息 Messages',
  scenes: '场景 Scenes',
  scene_npcs: '场景NPC Scene NPCs',
  events: '事件 Events',
  plugin_storage: '插件存储 Plugin Storage',
  game_logs: '游戏日志 Game Logs',
  game_kvs: '键值存储 Game KV',
  game_graphs: '关系图 Game Graph',
}

function JsonCell({ value }: { value: unknown }) {
  const [expanded, setExpanded] = useState(false)
  const toggle = () => setExpanded((v) => !v)

  if (value === null || value === undefined) {
    return <span className="text-muted-foreground/40">null</span>
  }
  if (typeof value === 'boolean') {
    return <span className={value ? 'text-emerald-400' : 'text-red-400'}>{String(value)}</span>
  }
  if (typeof value === 'number') {
    return <span className="text-cyan-400">{value}</span>
  }
  if (typeof value === 'string') {
    if (value.length > 80) {
      return (
        <div onDoubleClick={toggle} className="cursor-pointer select-none" title="双击展开/收起">
          <span className="break-all">{expanded ? value : value.slice(0, 80) + '…'}</span>
        </div>
      )
    }
    return <span className="break-all">{value}</span>
  }
  if (typeof value === 'object') {
    const compact = JSON.stringify(value)
    if (compact.length > 60) {
      return (
        <div onDoubleClick={toggle} className="cursor-pointer select-none" title="双击展开/收起">
          {expanded ? (
            <pre className="text-[11px] whitespace-pre-wrap break-all">{JSON.stringify(value, null, 2)}</pre>
          ) : (
            <span className="text-[11px] text-muted-foreground truncate block max-w-xs">{compact.slice(0, 60)}…</span>
          )}
        </div>
      )
    }
    return <pre className="text-[11px] whitespace-pre-wrap break-all">{compact}</pre>
  }
  return <span>{String(value)}</span>
}

function DataTable({ rows }: { rows: TableData[] }) {
  if (rows.length === 0) {
    return <p className="text-muted-foreground text-sm py-4 text-center">空表</p>
  }

  const columns = Object.keys(rows[0])

  return (
    <div className="overflow-x-auto border rounded-lg">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-muted/50 border-b">
            {columns.map((col) => (
              <th key={col} className="px-3 py-2 text-left font-medium text-muted-foreground whitespace-nowrap">
                {col}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i} className="border-b last:border-0 hover:bg-muted/30">
              {columns.map((col) => (
                <td key={col} className="px-3 py-2 align-top max-w-xs">
                  <JsonCell value={row[col]} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export function DebugTablesPage() {
  const { sessionId } = useParams<{ sessionId: string }>()
  const [data, setData] = useState<SessionTables | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTable, setActiveTable] = useState<string>('characters')

  useEffect(() => {
    if (!sessionId) return
    setLoading(true)
    fetch(`/api/debug/session/${sessionId}/tables`)
      .then((res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        return res.json()
      })
      .then((d) => {
        if (d.error) {
          setError(d.error)
        } else {
          setData(d)
          const firstNonEmpty = Object.entries(d.tables).find(
            ([, rows]) => (rows as TableData[]).length > 0,
          )
          if (firstNonEmpty) setActiveTable(firstNonEmpty[0])
        }
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [sessionId])

  if (loading) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    )
  }

  if (error) {
    return (
      <div className="min-h-screen bg-background flex items-center justify-center">
        <div className="bg-card border border-red-700/50 rounded-xl p-6 max-w-lg space-y-3">
          <p className="text-red-400">错误: {error}</p>
          <p className="text-muted-foreground text-xs">
            确保后端已启用 DEBUG_ENDPOINTS_ENABLED=true
          </p>
          <Link to="/" className="text-primary text-sm hover:underline block">返回首页</Link>
        </div>
      </div>
    )
  }

  if (!data) return null

  const tableNames = Object.keys(data.tables)
  const currentRows = data.tables[activeTable] || []

  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="border-b bg-card px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-muted-foreground hover:text-foreground text-sm">
            ← 返回
          </Link>
          <h1 className="text-sm font-medium">数据库浏览器</h1>
          <span className="text-xs text-muted-foreground font-mono">
            session: {sessionId?.slice(0, 8)}...
          </span>
        </div>
        <div className="text-xs text-muted-foreground">
          phase: {String((data.session as Record<string, unknown>).phase || '')} |
          status: {String((data.session as Record<string, unknown>).status || '')}
        </div>
      </div>

      <div className="flex h-[calc(100vh-49px)]">
        {/* Sidebar */}
        <div className="w-48 border-r bg-muted/10 p-2 space-y-0.5 overflow-y-auto shrink-0">
          {tableNames.map((name) => {
            const count = data.tables[name].length
            return (
              <button
                key={name}
                onClick={() => setActiveTable(name)}
                className={`w-full text-left px-3 py-2 rounded-lg text-xs transition-colors flex items-center justify-between ${
                  activeTable === name
                    ? 'bg-primary/10 text-primary'
                    : 'text-muted-foreground hover:bg-muted/50 hover:text-foreground'
                }`}
              >
                <span>{tableLabels[name] || name}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded-full ${
                  count > 0 ? 'bg-primary/20 text-primary' : 'bg-muted text-muted-foreground'
                }`}>
                  {count}
                </span>
              </button>
            )
          })}
        </div>

        {/* Content */}
        <div className="flex-1 overflow-auto p-4">
          <div className="flex items-center justify-between mb-3">
            <h2 className="text-sm font-medium">
              {tableLabels[activeTable] || activeTable}
              <span className="text-muted-foreground ml-2">({currentRows.length} 行)</span>
            </h2>
          </div>
          <DataTable rows={currentRows} />
        </div>
      </div>
    </div>
  )
}
