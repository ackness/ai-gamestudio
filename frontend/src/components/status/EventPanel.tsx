import { useState } from 'react'
import { useGameStateStore } from '../../stores/gameStateStore'
import { useSessionStore } from '../../stores/sessionStore'
import type { GameEvent } from '../../types'
import { buildEventForest } from './eventTree'

const typeBadgeColors: Record<string, string> = {
  quest: 'bg-amber-900/50 text-amber-400',
  combat: 'bg-red-900/50 text-red-400',
  social: 'bg-blue-900/50 text-blue-400',
  world: 'bg-emerald-900/50 text-emerald-400',
  system: 'bg-slate-700 text-slate-400',
}

const statusIcons: Record<string, string> = {
  active: '\u25CF',
  resolved: '\u2713',
  ended: '\u25CB',
}

function EventCard({ event, depth = 0 }: { event: GameEvent; depth?: number }) {
  const [expanded, setExpanded] = useState(event.status === 'active')
  const hasChildren = event.children && event.children.length > 0
  const badgeClass = typeBadgeColors[event.event_type] || typeBadgeColors.system

  return (
    <div style={{ marginLeft: depth * 12 }}>
      <div
        className="flex items-start gap-2 py-1.5 cursor-pointer hover:bg-slate-800/50 rounded px-1 -mx-1"
        onClick={() => setExpanded(!expanded)}
      >
        <span
          className={`text-xs mt-0.5 ${
            event.status === 'active'
              ? 'text-emerald-400'
              : event.status === 'resolved'
                ? 'text-slate-400'
                : 'text-slate-600'
          }`}
        >
          {statusIcons[event.status] || statusIcons.ended}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-200 font-medium truncate">{event.name}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${badgeClass}`}>
              {event.event_type}
            </span>
          </div>
          {expanded && (
            <p className="text-xs text-slate-400 mt-0.5 line-clamp-2">{event.description}</p>
          )}
        </div>
      </div>

      {expanded && hasChildren && (
        <div className="border-l border-slate-700 ml-1.5">
          {event.children!.map((child) => (
            <EventCard key={child.id} event={child} depth={depth + 1} />
          ))}
        </div>
      )}
    </div>
  )
}

export function EventPanel() {
  const currentSession = useSessionStore((s) => s.currentSession)
  const allEvents = useGameStateStore((s) => s.events)
  const events = currentSession
    ? allEvents.filter((event) => event.session_id === currentSession.id)
    : []

  if (currentSession?.phase === 'init') {
    return <p className="text-slate-500 text-sm text-center py-4">冒险尚未开始，暂无事件</p>
  }

  const withChildren = buildEventForest(events)

  const active = withChildren.filter((e) => e.status === 'active')
  const ended = withChildren.filter((e) => e.status !== 'active')

  if (events.length === 0) {
    return <p className="text-slate-500 text-sm text-center py-4">暂无事件</p>
  }

  return (
    <div className="space-y-4">
      {active.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase mb-2">活跃事件</h4>
          <div className="space-y-0.5">
            {active.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}

      {ended.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-slate-500 uppercase mb-2">已结束事件</h4>
          <div className="space-y-0.5">
            {ended.map((event) => (
              <EventCard key={event.id} event={event} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
