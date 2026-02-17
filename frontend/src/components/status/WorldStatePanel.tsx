import { useGameStateStore } from '../../stores/gameStateStore'

export function WorldStatePanel() {
  const { worldState } = useGameStateStore()

  const entries = Object.entries(worldState)

  if (entries.length === 0) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        <p>No world state data</p>
        <p className="text-xs mt-1">State updates will appear during gameplay</p>
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
