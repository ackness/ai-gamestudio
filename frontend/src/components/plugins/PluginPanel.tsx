import { useEffect, useState } from 'react'
import { usePluginStore } from '../../stores/pluginStore'
import { useProjectStore } from '../../stores/projectStore'
import { useUiStore } from '../../stores/uiStore'
import { getPluginDetail } from '../../services/api'
import type { Plugin, PluginDetail } from '../../types'

function getLocalizedField(
  plugin: Plugin,
  field: 'name' | 'description',
  language: string,
): string {
  return plugin.i18n?.[language]?.[field] || plugin[field] || ''
}

function PluginDetailPanel({ name }: { name: string }) {
  const [detail, setDetail] = useState<PluginDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'prompt' | 'blocks'>('prompt')

  useEffect(() => {
    setLoading(true)
    getPluginDetail(name)
      .then(setDetail)
      .catch(() => setDetail(null))
      .finally(() => setLoading(false))
  }, [name])

  if (loading) {
    return <div className="text-[11px] text-slate-500 py-2">加载中...</div>
  }
  if (!detail) {
    return <div className="text-[11px] text-red-400 py-2">无法加载详情</div>
  }

  const blockNames = Object.keys(detail.blocks)
  const hasTabs = detail.prompt && blockNames.length > 0

  return (
    <div className="mt-2 border-t border-slate-700/60 pt-2 space-y-2">
      {hasTabs && (
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('prompt')}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
              activeTab === 'prompt'
                ? 'bg-slate-600 text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            Prompt
          </button>
          <button
            onClick={() => setActiveTab('blocks')}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
              activeTab === 'blocks'
                ? 'bg-slate-600 text-slate-100'
                : 'text-slate-500 hover:text-slate-300'
            }`}
          >
            Blocks ({blockNames.length})
          </button>
        </div>
      )}

      {/* Prompt tab */}
      {(activeTab === 'prompt' || !hasTabs) && detail.prompt && (
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-slate-500">position:</span>
            <code className="text-[10px] text-sky-400">{detail.prompt.position ?? '—'}</code>
            <span className="text-[10px] text-slate-500 ml-1">priority:</span>
            <code className="text-[10px] text-sky-400">{detail.prompt.priority ?? '—'}</code>
          </div>
          {detail.prompt.content ? (
            <pre className="text-[10px] text-slate-300 bg-slate-900/60 border border-slate-700/50 rounded p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
              {detail.prompt.content}
            </pre>
          ) : (
            <p className="text-[10px] text-slate-500 italic">无模板内容</p>
          )}
        </div>
      )}

      {/* Blocks tab */}
      {(activeTab === 'blocks' || !hasTabs) && blockNames.length > 0 && (
        <div className="space-y-2">
          {blockNames.map((blockType) => {
            const block = detail.blocks[blockType]
            return (
              <div key={blockType}>
                <code className="text-[10px] text-emerald-400">json:{blockType}</code>
                {block.instruction && (
                  <pre className="mt-1 text-[10px] text-slate-300 bg-slate-900/60 border border-slate-700/50 rounded p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-36 overflow-y-auto">
                    {block.instruction}
                  </pre>
                )}
              </div>
            )
          })}
        </div>
      )}

      {/* Supersedes notice */}
      {detail.supersedes && detail.supersedes.length > 0 && (
        <p className="text-[10px] text-violet-400">
          启用时抑制: {detail.supersedes.join(', ')}
        </p>
      )}
    </div>
  )
}

export function PluginPanel() {
  const { plugins, blockConflicts, loading, fetchPlugins, togglePlugin } = usePluginStore()
  const currentProject = useProjectStore((s) => s.currentProject)
  const language = useUiStore((s) => s.language)
  const [expandedPlugin, setExpandedPlugin] = useState<string | null>(null)

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

      {plugins.map((plugin) => {
        const displayName = getLocalizedField(plugin, 'name', language)
        const displayDescription = getLocalizedField(plugin, 'description', language)
        const isExpanded = expandedPlugin === plugin.name

        return (
          <div
            key={plugin.name}
            className="bg-slate-800 border border-slate-700 rounded-lg p-3"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-200">{displayName}</span>
                  {displayName !== plugin.name && (
                    <span className="text-[10px] text-slate-500 font-mono">{plugin.name}</span>
                  )}
                  {plugin.version && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-slate-700 text-slate-400">
                      v{plugin.version}
                    </span>
                  )}
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
                  {plugin.manifest_source === 'v1_fallback' && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded font-medium bg-orange-900/50 text-orange-400">
                      v1
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 mt-1 line-clamp-2">{displayDescription}</p>
                {plugin.capabilities && plugin.capabilities.length > 0 && (
                  <div className="mt-1 flex gap-1 flex-wrap">
                    {plugin.capabilities.map((cap) => (
                      <span
                        key={cap}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-900/30 text-emerald-400 border border-emerald-800/40"
                      >
                        {cap}
                      </span>
                    ))}
                  </div>
                )}
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
              <div className="flex items-center gap-2 shrink-0">
                {/* Detail toggle */}
                <button
                  onClick={() => setExpandedPlugin(isExpanded ? null : plugin.name)}
                  className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${
                    isExpanded
                      ? 'text-slate-300 bg-slate-700'
                      : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50'
                  }`}
                  title="查看提示词与 Schema"
                >
                  {'</>'}
                </button>
                {/* Enable toggle */}
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
                  className={`w-10 h-5 rounded-full transition-colors relative ${
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
            </div>

            {/* Expandable detail panel */}
            {isExpanded && <PluginDetailPanel name={plugin.name} />}
          </div>
        )
      })}
    </div>
  )
}
