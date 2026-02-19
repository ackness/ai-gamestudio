import { useState, useRef, useEffect } from 'react'
import type { Session } from '../../types'
import { useUiStore } from '../../stores/uiStore'

interface Props {
  sessions: Session[]
  currentSession: Session | null
  onSwitch: (session: Session) => void
  onNew: () => void
  onDelete: (sessionId: string) => void
}

function formatTime(iso: string): string {
  const d = new Date(iso)
  const now = new Date()
  const isToday = d.toDateString() === now.toDateString()
  if (isToday) {
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  }
  return d.toLocaleDateString([], { month: '2-digit', day: '2-digit' }) +
    ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
}

const phaseLabels: Record<string, Record<string, string>> = {
  zh: { init: '未开始', character_creation: '创建角色', playing: '进行中', ended: '已结束' },
  en: { init: 'Not Started', character_creation: 'Creating', playing: 'Playing', ended: 'Ended' },
}

const uiText: Record<string, Record<string, string>> = {
  zh: {
    sessions: '存档',
    noSessions: '暂无存档',
    newSession: '+ 新存档',
    confirm: '确认?',
    deleteTitle: '删除存档',
    confirmTitle: '再次点击确认',
  },
  en: {
    sessions: 'Sessions',
    noSessions: 'No sessions yet',
    newSession: '+ New Session',
    confirm: 'Confirm?',
    deleteTitle: 'Delete session',
    confirmTitle: 'Click again to confirm',
  },
}

export function SessionSelector({ sessions, currentSession, onSwitch, onNew, onDelete }: Props) {
  const [open, setOpen] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  const language = useUiStore((s) => s.language)
  const t = uiText[language] ?? uiText.en
  const phases = phaseLabels[language] ?? phaseLabels.en

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        setOpen(false)
        setConfirmDelete(null)
      }
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleDelete = (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation()
    if (confirmDelete === sessionId) {
      onDelete(sessionId)
      setConfirmDelete(null)
    } else {
      setConfirmDelete(sessionId)
    }
  }

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen(!open)}
        className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors flex items-center gap-1"
      >
        {t.sessions}
        <span className="text-slate-500">({sessions.length})</span>
        <span className="text-[10px] text-slate-500">{open ? '\u25B2' : '\u25BC'}</span>
      </button>

      {open && (
        <div className="absolute top-full right-0 mt-1 w-72 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-50 overflow-hidden">
          <div className="max-h-64 overflow-y-auto">
            {sessions.length === 0 && (
              <div className="px-3 py-4 text-center text-slate-500 text-xs">
                {t.noSessions}
              </div>
            )}
            {sessions.map((s) => {
              const isCurrent = s.id === currentSession?.id
              return (
                <div
                  key={s.id}
                  onClick={() => {
                    if (!isCurrent) {
                      onSwitch(s)
                      setOpen(false)
                    }
                  }}
                  className={`flex items-center justify-between px-3 py-2 text-xs border-b border-slate-700/50 last:border-b-0 transition-colors ${
                    isCurrent
                      ? 'bg-emerald-900/30 text-slate-200'
                      : 'text-slate-300 hover:bg-slate-700/50 cursor-pointer'
                  }`}
                >
                  <div className="flex flex-col gap-0.5 min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {isCurrent && (
                        <span className="w-1.5 h-1.5 bg-emerald-400 rounded-full shrink-0" />
                      )}
                      <span className="truncate font-mono text-slate-400">
                        {s.id.slice(0, 8)}
                      </span>
                      <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] ${
                        s.phase === 'playing'
                          ? 'bg-cyan-900/50 text-cyan-300'
                          : s.phase === 'ended'
                            ? 'bg-slate-700 text-slate-400'
                            : 'bg-slate-700 text-slate-400'
                      }`}>
                        {phases[s.phase] || s.phase}
                      </span>
                    </div>
                    <span className="text-[10px] text-slate-500 pl-0.5">
                      {formatTime(s.created_at)}
                    </span>
                  </div>
                  <button
                    onClick={(e) => handleDelete(e, s.id)}
                    className={`shrink-0 ml-2 px-1.5 py-0.5 rounded text-[10px] transition-colors ${
                      confirmDelete === s.id
                        ? 'bg-red-700 text-white'
                        : 'text-slate-500 hover:text-red-400 hover:bg-red-900/30'
                    }`}
                    title={confirmDelete === s.id ? t.confirmTitle : t.deleteTitle}
                  >
                    {confirmDelete === s.id ? t.confirm : '\u2715'}
                  </button>
                </div>
              )
            })}
          </div>
          <div className="border-t border-slate-700 px-3 py-2">
            <button
              onClick={() => {
                onNew()
                setOpen(false)
              }}
              className="w-full text-xs py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded transition-colors"
            >
              {t.newSession}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
