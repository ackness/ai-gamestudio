import type { BlockRendererProps } from '../services/blockRenderers'

interface QuestObjective {
  id: string
  text: string
  completed: boolean
}

interface QuestRewards {
  xp?: number
  gold?: number
  items?: string[]
}

interface QuestData {
  action: 'create' | 'update' | 'complete' | 'fail'
  quest_id: string
  title: string
  description?: string
  objectives?: QuestObjective[]
  rewards?: QuestRewards
  status: 'active' | 'completed' | 'failed'
}

const statusStyles: Record<string, { border: string; badge: string; badgeText: string; icon: string }> = {
  active: {
    border: 'border-cyan-700/50',
    badge: 'bg-cyan-900/40 text-cyan-300',
    badgeText: '\u8FDB\u884C\u4E2D',
    icon: '\uD83D\uDCDC',
  },
  completed: {
    border: 'border-emerald-700/50',
    badge: 'bg-emerald-900/40 text-emerald-300',
    badgeText: '\u5DF2\u5B8C\u6210',
    icon: '\u2705',
  },
  failed: {
    border: 'border-red-700/50',
    badge: 'bg-red-900/40 text-red-300',
    badgeText: '\u5DF2\u5931\u8D25',
    icon: '\u274C',
  },
}

export function QuestRenderer({ data }: BlockRendererProps) {
  const d = data as QuestData
  if (!d) return null

  const style = statusStyles[d.status] || statusStyles.active
  const completedCount = d.objectives?.filter((o) => o.completed).length ?? 0
  const totalCount = d.objectives?.length ?? 0

  return (
    <div className={`bg-card border ${style.border} rounded-xl px-4 py-3 max-w-[80%] space-y-2`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-sm">{style.icon}</span>
          <span className="text-sm font-medium">{d.title}</span>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full ${style.badge}`}>
          {style.badgeText}
        </span>
      </div>

      {d.description && (
        <p className="text-muted-foreground text-xs leading-relaxed">{d.description}</p>
      )}

      {d.objectives && d.objectives.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center justify-between">
            <span className="text-muted-foreground text-xs">{'\u76EE\u6807'}</span>
            <span className="text-muted-foreground text-xs">{completedCount}/{totalCount}</span>
          </div>
          {d.objectives.map((obj) => (
            <div key={obj.id} className="flex items-start gap-2">
              <span className={`text-xs mt-0.5 ${obj.completed ? 'text-emerald-400' : 'text-muted-foreground/40'}`}>
                {obj.completed ? '\u25C9' : '\u25CB'}
              </span>
              <span className={`text-xs ${obj.completed ? 'text-muted-foreground line-through' : 'text-foreground/80'}`}>
                {obj.text}
              </span>
            </div>
          ))}
        </div>
      )}

      {d.rewards && (
        <div className="flex items-center gap-3 pt-1 border-t">
          <span className="text-muted-foreground text-xs">{'\u5956\u52B1'}</span>
          {d.rewards.xp != null && (
            <span className="text-cyan-400 text-xs">{d.rewards.xp} XP</span>
          )}
          {d.rewards.gold != null && (
            <span className="text-yellow-400 text-xs">{'\uD83E\uDE99'} {d.rewards.gold}</span>
          )}
          {d.rewards.items && d.rewards.items.map((item, i) => (
            <span key={i} className="text-amber-300 text-xs">{item}</span>
          ))}
        </div>
      )}
    </div>
  )
}
