import { useEffect, useState } from 'react'
import { usePluginStore } from '../../stores/pluginStore'
import { useProjectStore } from '../../stores/projectStore'
import { useUiStore } from '../../stores/uiStore'
import { getPluginDetail } from '../../services/api'
import type { Plugin, PluginDetail } from '../../types'
import { Badge } from '@/components/ui/badge'
import { Switch } from '@/components/ui/switch'
import { Alert, AlertDescription } from '@/components/ui/alert'
import { AlertTriangle, Code2, Loader2 } from 'lucide-react'

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
    return <div className="flex items-center gap-2 py-2 text-xs text-muted-foreground"><Loader2 className="w-3 h-3 animate-spin" />加载中...</div>
  }
  if (!detail) {
    return <div className="text-xs text-destructive py-2">无法加载详情</div>
  }

  const blockNames = Object.keys(detail.blocks)
  const hasTabs = detail.prompt && blockNames.length > 0

  return (
    <div className="mt-2 border-t pt-2 space-y-2">
      {hasTabs && (
        <div className="flex gap-1">
          <button
            onClick={() => setActiveTab('prompt')}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
              activeTab === 'prompt'
                ? 'bg-muted text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Prompt
          </button>
          <button
            onClick={() => setActiveTab('blocks')}
            className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
              activeTab === 'blocks'
                ? 'bg-muted text-foreground'
                : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            Blocks ({blockNames.length})
          </button>
        </div>
      )}

      {(activeTab === 'prompt' || !hasTabs) && detail.prompt && (
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="text-[10px] text-muted-foreground">position:</span>
            <code className="text-[10px] text-primary">{detail.prompt.position ?? '—'}</code>
            <span className="text-[10px] text-muted-foreground ml-1">priority:</span>
            <code className="text-[10px] text-primary">{detail.prompt.priority ?? '—'}</code>
          </div>
          {detail.prompt.content ? (
            <pre className="text-[10px] text-foreground/80 bg-muted/50 border rounded p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-48 overflow-y-auto">
              {detail.prompt.content}
            </pre>
          ) : (
            <p className="text-[10px] text-muted-foreground italic">无模板内容</p>
          )}
        </div>
      )}

      {(activeTab === 'blocks' || !hasTabs) && blockNames.length > 0 && (
        <div className="space-y-2">
          {blockNames.map((blockType) => {
            const block = detail.blocks[blockType]
            return (
              <div key={blockType}>
                <code className="text-[10px] text-primary">json:{blockType}</code>
                {block.instruction && (
                  <pre className="mt-1 text-[10px] text-foreground/80 bg-muted/50 border rounded p-2 overflow-x-auto whitespace-pre-wrap leading-relaxed max-h-36 overflow-y-auto">
                    {block.instruction}
                  </pre>
                )}
              </div>
            )
          })}
        </div>
      )}

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
    return (
      <div className="flex items-center justify-center gap-2 py-8 text-sm text-muted-foreground">
        <Loader2 className="w-4 h-4 animate-spin" />
        Loading plugins...
      </div>
    )
  }

  if (plugins.length === 0) {
    return (
      <div className="text-center text-muted-foreground py-8 text-sm">
        <p>No plugins available</p>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      {blockConflicts.length > 0 && (
        <Alert variant="destructive" className="py-2">
          <AlertTriangle className="h-3.5 w-3.5" />
          <AlertDescription className="text-xs">
            <span className="font-medium">检测到 block type 冲突</span>
            <div className="mt-1 space-y-0.5">
              {blockConflicts.map((c, i) => (
                <p key={`${c.block_type}-${i}`} className="text-[11px]">
                  <code>{c.block_type}</code>: {c.overridden_plugin} → {c.winner_plugin}
                </p>
              ))}
            </div>
          </AlertDescription>
        </Alert>
      )}

      {plugins.map((plugin) => {
        const displayName = getLocalizedField(plugin, 'name', language)
        const displayDescription = getLocalizedField(plugin, 'description', language)
        const isExpanded = expandedPlugin === plugin.name
        const isDisabled = plugin.required || !currentProject || (!!plugin.required_by && plugin.required_by.length > 0)

        return (
          <div key={plugin.name} className="rounded-lg border bg-card p-3 space-y-1.5">
            <div className="flex items-start justify-between gap-2">
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5 flex-wrap">
                  <span className="text-sm font-medium">{displayName}</span>
                  {displayName !== plugin.name && (
                    <span className="text-[10px] text-muted-foreground font-mono">{plugin.name}</span>
                  )}
                  {plugin.version && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1 font-mono">v{plugin.version}</Badge>
                  )}
                  <Badge variant="secondary" className="text-[10px] h-4 px-1">{plugin.type}</Badge>
                  {plugin.auto_enabled && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1 text-cyan-400 border-cyan-400/30">auto</Badge>
                  )}
                  {plugin.manifest_source === 'v1_fallback' && (
                    <Badge variant="outline" className="text-[10px] h-4 px-1 text-orange-400 border-orange-400/30">v1</Badge>
                  )}
                </div>
                {displayDescription && (
                  <p className="text-xs text-muted-foreground mt-1 line-clamp-2">{displayDescription}</p>
                )}
                {plugin.capabilities && plugin.capabilities.length > 0 && (
                  <div className="mt-1 flex gap-1 flex-wrap">
                    {plugin.capabilities.map((cap) => (
                      <Badge key={cap} variant="outline" className="text-[10px] h-4 px-1 text-primary border-primary/30">{cap}</Badge>
                    ))}
                  </div>
                )}
                {plugin.required_by && plugin.required_by.length > 0 && (
                  <p className="text-[11px] text-amber-400 mt-0.5">被依赖: {plugin.required_by.join(', ')}</p>
                )}
                {plugin.dependencies && plugin.dependencies.length > 0 && (
                  <p className="text-[11px] text-muted-foreground mt-0.5">依赖: {plugin.dependencies.join(', ')}</p>
                )}
              </div>
              <div className="flex items-center gap-1.5 shrink-0 pt-0.5">
                <button
                  onClick={() => setExpandedPlugin(isExpanded ? null : plugin.name)}
                  className={`p-1 rounded transition-colors ${
                    isExpanded ? 'text-foreground bg-muted' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
                  }`}
                  title="查看提示词与 Schema"
                >
                  <Code2 className="w-3.5 h-3.5" />
                </button>
                <Switch
                  checked={plugin.enabled}
                  disabled={isDisabled}
                  onCheckedChange={(checked) =>
                    !isDisabled && currentProject &&
                    togglePlugin(plugin.name, currentProject.id, checked)
                  }
                  className="scale-75 origin-right"
                />
              </div>
            </div>

            {isExpanded && <PluginDetailPanel name={plugin.name} />}
          </div>
        )
      })}
    </div>
  )
}
