import { useGameStateStore } from '../../stores/gameStateStore'
import { useUiStore } from '../../stores/uiStore'

export function WorldStatePanel() {
  const { worldState } = useGameStateStore()
  const language = useUiStore((s) => s.language)

  const entries = Object.entries(worldState)

  if (entries.length === 0) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        <p>{language === 'zh' ? '暂无世界状态数据' : 'No world state data'}</p>
        <p className="text-xs mt-1">{language === 'zh' ? '游戏进行中将显示状态更新' : 'State updates will appear during gameplay'}</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {entries.map(([key, value]) => (
        <div key={key} className="bg-slate-800 border border-slate-700 rounded-lg p-3">
          <div className="text-xs font-medium text-cyan-400 mb-1">{key}</div>
          <div className="text-xs text-slate-300 font-mono whitespace-pre-wrap break-all">
            {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
          </div>
        </div>
      ))}
    </div>
  )
}
