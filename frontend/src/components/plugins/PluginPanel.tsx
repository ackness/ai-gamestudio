import { useEffect } from 'react'
import { usePluginStore } from '../../stores/pluginStore'
import { useProjectStore } from '../../stores/projectStore'

export function PluginPanel() {
  const { plugins, blockConflicts, loading, fetchPlugins, togglePlugin } = usePluginStore()
  const currentProject = useProjectStore((s) => s.currentProject)

  useEffect(() => {
    fetchPlugins(currentProject?.id)
  }, [fetchPlugins, currentProject?.id])

  if (loading && plugins.length === 0) {
    return <div className="text-center text-slate-500 py-8 text-sm">Loading plugins...</div>
  }

  if (plugins.length === 0) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        <p>No plugins available</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {blockConflicts.length > 0 && (
        <div className="bg-amber-900/20 border border-amber-700/40 rounded-lg p-2.5">
          <p className="text-xs text-amber-300 font-medium">检测到 block type 冲突</p>
          <div className="mt-1 space-y-1">
            {blockConflicts.map((c, i) => (
              <p key={`${c.block_type}-${i}`} className="text-[11px] text-amber-200/90">
                <code>{c.block_type}</code>: {c.overridden_plugin} → {c.winner_plugin}
              </p>
            ))}
          </div>
        </div>
      )}

      {plugins.map((plugin) => (
        <div
          key={plugin.name}
          className="bg-slate-800 border border-slate-700 rounded-lg p-3 flex items-start justify-between gap-3"
        >
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-200">{plugin.name}</span>
              <span
                className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                  plugin.type === 'global'
                    ? 'bg-purple-900/50 text-purple-400'
                    : 'bg-amber-900/50 text-amber-400'
                }`}
              >
                {plugin.type}
              </span>
              {plugin.auto_enabled && (
                <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-cyan-900/50 text-cyan-300">
                  auto
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1 line-clamp-2">{plugin.description}</p>
            {plugin.required_by && plugin.required_by.length > 0 && (
              <p className="text-[11px] text-amber-300 mt-1">
                被依赖: {plugin.required_by.join(', ')}
              </p>
            )}
            {plugin.dependencies && plugin.dependencies.length > 0 && (
              <p className="text-[11px] text-slate-500 mt-0.5">
                依赖: {plugin.dependencies.join(', ')}
              </p>
            )}
          </div>
          <button
            onClick={() =>
              !plugin.required &&
              currentProject &&
              togglePlugin(plugin.name, currentProject.id, !plugin.enabled)
            }
            disabled={
              plugin.required ||
              !currentProject ||
              (!!plugin.required_by && plugin.required_by.length > 0)
            }
            className={`shrink-0 w-10 h-5 rounded-full transition-colors relative ${
              plugin.enabled ? 'bg-emerald-600' : 'bg-slate-600'
            } ${
              plugin.required || (!!plugin.required_by && plugin.required_by.length > 0)
                ? 'opacity-60 cursor-not-allowed'
                : 'cursor-pointer'
            }`}
          >
            <span
              className={`absolute top-0.5 w-4 h-4 bg-white rounded-full transition-transform ${
                plugin.enabled ? 'left-5.5 translate-x-0.5' : 'left-0.5'
              }`}
            />
          </button>
        </div>
      ))}
    </div>
  )
}
