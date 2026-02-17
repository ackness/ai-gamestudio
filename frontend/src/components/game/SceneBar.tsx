import { useState } from 'react'
import type { Scene } from '../../types'

interface Props {
  currentScene: Scene
  scenes: Scene[]
  onSceneSwitch: (sceneId: string) => void
}

export function SceneBar({ currentScene, scenes, onSceneSwitch }: Props) {
  const [showDropdown, setShowDropdown] = useState(false)

  const otherScenes = scenes.filter((s) => s.id !== currentScene.id)

  return (
    <div className="flex items-center gap-3 px-4 py-2 bg-slate-800/80 border-b border-slate-700 text-sm">
      <div className="flex items-center gap-2 min-w-0 flex-1">
        <span className="text-emerald-400 font-medium truncate">{currentScene.name}</span>
        {currentScene.description && (
          <span className="text-slate-500 truncate hidden sm:inline">
            — {currentScene.description}
          </span>
        )}
      </div>

      {otherScenes.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded transition-colors whitespace-nowrap"
          >
            切换场景
          </button>
          {showDropdown && (
            <div className="absolute right-0 top-full mt-1 bg-slate-800 border border-slate-600 rounded-lg shadow-xl z-10 min-w-[160px]">
              {otherScenes.map((scene) => (
                <button
                  key={scene.id}
                  onClick={() => {
                    onSceneSwitch(scene.id)
                    setShowDropdown(false)
                  }}
                  className="block w-full text-left px-3 py-2 text-xs text-slate-300 hover:bg-slate-700 first:rounded-t-lg last:rounded-b-lg transition-colors"
                >
                  {scene.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}
