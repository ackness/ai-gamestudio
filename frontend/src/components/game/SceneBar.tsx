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
    <div
      className="flex items-center gap-3 px-4 py-2 text-sm"
      style={{
        background: 'rgba(10, 20, 37, 0.8)',
        borderBottom: '1px solid rgba(148, 163, 184, 0.08)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div className="flex items-center gap-2 min-w-0 flex-1">
        {/* Scene indicator dot */}
        <span
          className="w-1.5 h-1.5 rounded-full shrink-0"
          style={{
            background: '#10b981',
            boxShadow: '0 0 6px rgba(16, 185, 129, 0.6)',
          }}
        />
        <span className="font-medium truncate" style={{ color: '#67c4a0', fontSize: '0.8rem' }}>
          {currentScene.name}
        </span>
        {currentScene.description && (
          <span
            className="truncate hidden sm:inline text-xs"
            style={{ color: 'rgba(127, 168, 196, 0.4)' }}
          >
            — {currentScene.description}
          </span>
        )}
      </div>

      {otherScenes.length > 0 && (
        <div className="relative">
          <button
            onClick={() => setShowDropdown(!showDropdown)}
            className="flex items-center gap-1.5 text-xs px-2.5 py-1 rounded-lg transition-colors"
            style={{
              background: 'rgba(148, 163, 184, 0.07)',
              border: '1px solid rgba(148, 163, 184, 0.12)',
              color: 'rgba(127, 168, 196, 0.7)',
            }}
          >
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8">
              <path d="M2 4l3 3 3-3" />
            </svg>
            切换场景
          </button>
          {showDropdown && (
            <div
              className="absolute right-0 top-full mt-1.5 rounded-xl z-10 min-w-[160px] overflow-hidden"
              style={{
                background: 'rgba(16, 28, 46, 0.96)',
                border: '1px solid rgba(148, 163, 184, 0.12)',
                boxShadow: '0 8px 32px rgba(0, 0, 0, 0.4)',
                backdropFilter: 'blur(16px)',
              }}
            >
              {otherScenes.map((scene) => (
                <button
                  key={scene.id}
                  onClick={() => {
                    onSceneSwitch(scene.id)
                    setShowDropdown(false)
                  }}
                  className="block w-full text-left px-3 py-2 text-xs transition-colors"
                  style={{ color: 'rgba(223, 240, 247, 0.7)' }}
                  onMouseEnter={(e) => {
                    e.currentTarget.style.background = 'rgba(16, 185, 129, 0.08)'
                    e.currentTarget.style.color = '#67c4a0'
                  }}
                  onMouseLeave={(e) => {
                    e.currentTarget.style.background = 'transparent'
                    e.currentTarget.style.color = 'rgba(223, 240, 247, 0.7)'
                  }}
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
