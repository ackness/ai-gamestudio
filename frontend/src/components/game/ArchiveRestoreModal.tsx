import { useState } from 'react'
import type { ArchiveVersion } from '../../types'

interface Props {
  versions: ArchiveVersion[]
  onSelect: (version: number, mode: 'hard' | 'fork') => void
  onClose: () => void
}

export function ArchiveRestoreModal({ versions, onSelect, onClose }: Props) {
  const [mode, setMode] = useState<'hard' | 'fork'>('fork')

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60"
      onClick={onClose}
    >
      <div
        className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl max-w-md w-full mx-4 max-h-[70vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-slate-700">
          <h3 className="text-sm font-medium text-slate-200">恢复存档</h3>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        <div className="px-4 py-3 border-b border-slate-700 space-y-2">
          <p className="text-[11px] text-slate-400">恢复模式</p>
          <div className="flex gap-2">
            <button
              onClick={() => setMode('fork')}
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                mode === 'fork'
                  ? 'bg-emerald-900/40 border-emerald-700 text-emerald-300'
                  : 'bg-slate-800 border-slate-600 text-slate-400 hover:text-slate-200'
              }`}
            >
              Fork（推荐，保留当前会话）
            </button>
            <button
              onClick={() => setMode('hard')}
              className={`text-xs px-2 py-1 rounded border transition-colors ${
                mode === 'hard'
                  ? 'bg-amber-900/40 border-amber-700 text-amber-300'
                  : 'bg-slate-800 border-slate-600 text-slate-400 hover:text-slate-200'
              }`}
            >
              Hard（覆盖当前会话）
            </button>
          </div>
          <p className="text-[10px] text-slate-500">
            {mode === 'fork'
              ? '将创建一个新会话分支并跳转过去，当前会话保持不变。'
              : '会清空并覆盖当前会话内容，请谨慎使用。'}
          </p>
        </div>

        {/* Version list */}
        <div className="flex-1 overflow-y-auto p-2">
          {versions.map((v) => (
            <button
              key={v.version}
              onClick={() => onSelect(v.version, mode)}
              className="w-full text-left px-3 py-2.5 rounded-lg hover:bg-slate-700/60 transition-colors group"
            >
              <div className="flex items-center gap-2 mb-1">
                <span className="text-xs font-mono font-medium text-emerald-400">
                  v{v.version}
                </span>
                {v.active && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300">
                    当前
                  </span>
                )}
                <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">
                  {v.trigger === 'auto' ? 'auto' : 'manual'}
                </span>
                <span className="text-[10px] text-slate-500">Turn {v.turn}</span>
              </div>
              <div className="text-xs text-slate-300 truncate">{v.title}</div>
              {v.summary_excerpt && v.summary_excerpt !== v.title && (
                <div className="text-[11px] text-slate-500 truncate mt-0.5">
                  {v.summary_excerpt}
                </div>
              )}
              <div className="text-[10px] text-slate-600 mt-1">
                {new Date(v.created_at).toLocaleString()}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  )
}
