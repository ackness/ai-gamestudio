import { useGameStateStore } from '../../stores/gameStateStore'
import { useUiStore } from '../../stores/uiStore'

const worldStateText: Record<string, Record<string, string>> = {
  zh: {
    empty: '暂无世界状态数据',
    emptyHint: '游戏进行中将显示状态更新',
  },
  en: {
    empty: 'No world state data',
    emptyHint: 'State updates will appear during gameplay',
  },
}

export function WorldStatePanel() {
  const { worldState } = useGameStateStore()
  const language = useUiStore((s) => s.language)
  const t = worldStateText[language] ?? worldStateText.en

  const entries = Object.entries(worldState)

  if (entries.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8 text-sm">
        <p>{t.empty}</p>
        <p className="text-xs mt-1">{t.emptyHint}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => (
        <div key={key} className="rounded-lg border bg-card p-3">
          <div className="text-xs font-medium text-primary mb-1">{key}</div>
          <div className="text-xs text-foreground/80 font-mono whitespace-pre-wrap break-all">
            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
          </div>
        </div>
      ))}
    </div>
  )
}
