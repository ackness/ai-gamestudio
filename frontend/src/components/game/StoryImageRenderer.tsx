import { useState } from 'react'
import type { BlockRendererProps } from '../../services/blockRenderers'
import { useUiStore } from '../../stores/uiStore'

// ---------------------------------------------------------------------------
// i18n
// ---------------------------------------------------------------------------
const texts: Record<string, Record<string, string>> = {
  zh: {
    storyImage: '剧情配图',
    ready: '就绪',
    error: '错误',
    generating: '生成中…',
    viewDetails: '查看详情',
    regenerate: '重新生成',
    context: '上下文',
    hideContext: '收起上下文',
    background: '背景',
    prompt: '提示词',
    continuity: '连续性',
    imageFailed: '图片生成失败。',
    imageGenerating: '正在生成图片，请稍候…',
    regenNote: '可选的重新生成备注',
    showDetails: '显示详情',
    hideDetails: '隐藏详情',
    close: '关闭',
    llmEnhanced: 'LLM 增强',
    originalPrompt: '原始提示词',
    storyBackground: '故事背景',
    continuityNotes: '连续性注记',
    sceneFrames: '场景分镜',
    enhancedPrompt: '增强后提示词',
    generatedPrompt: '生成的提示词',
    preEnhancement: '增强前提示词',
    none: '（无）',
    worldContext: '世界上下文',
    worldLore: '世界设定',
    textWorldState: '文本世界状态',
    metadata: '元数据',
  },
  en: {
    storyImage: 'Story Image',
    ready: 'ready',
    error: 'error',
    generating: 'generating…',
    viewDetails: 'View details',
    regenerate: 'Regenerate',
    context: 'Context',
    hideContext: 'Hide context',
    background: 'Background',
    prompt: 'Prompt',
    continuity: 'Continuity',
    imageFailed: 'Image generation failed.',
    imageGenerating: 'Generating image, please wait…',
    regenNote: 'Optional regeneration note',
    showDetails: 'Show details',
    hideDetails: 'Hide details',
    close: 'Close',
    llmEnhanced: 'LLM Enhanced',
    originalPrompt: 'Original Prompt',
    storyBackground: 'Story Background',
    continuityNotes: 'Continuity Notes',
    sceneFrames: 'Scene Frames',
    enhancedPrompt: 'Enhanced Prompt',
    generatedPrompt: 'Generated Prompt',
    preEnhancement: 'Pre-Enhancement Prompt',
    none: '(none)',
    worldContext: 'World Context',
    worldLore: 'World Lore',
    textWorldState: 'Text World State',
    metadata: 'Metadata',
  },
}

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
interface StoryImageData {
  status?: 'ok' | 'error' | 'generating'
  image_id?: string
  title?: string
  story_background?: string
  prompt?: string
  continuity_notes?: string
  image_url?: string
  error?: string
  can_regenerate?: boolean
  reference_image_ids?: string[]
  scene_frames?: string[]
  layout_preference?: string
  reference_images?: Array<{ image_id?: string; title?: string }>
  provider_model?: string
  provider_note?: string
  settings_applied?: Record<string, unknown>
  debug?: {
    generated_prompt?: string
    enhanced_prompt?: string
    world_lore_excerpt?: string
    text_world_state?: string
    reference_images?: Array<{ image_id?: string; title?: string }>
    runtime_settings?: Record<string, unknown>
    provider_model?: string
    api_base?: string
  }
}

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------
function DetailRow({ label, value }: { label: string; value?: string | null }) {
  if (!value) return null
  return (
    <div className="space-y-0.5">
      <p className="text-muted-foreground font-medium">{label}</p>
      <pre className="text-foreground/80 whitespace-pre-wrap break-words leading-relaxed">
        {value}
      </pre>
    </div>
  )
}

function ImageLightbox({
  payload,
  onClose,
  t,
}: {
  payload: StoryImageData
  onClose: () => void
  t: Record<string, string>
}) {
  const [showDetails, setShowDetails] = useState(false)
  const model = payload.debug?.provider_model || payload.provider_model
  const apiBase = payload.debug?.api_base
  const enhanced = payload.debug?.enhanced_prompt
  const generated = payload.debug?.generated_prompt

  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex flex-col" onClick={onClose}>
      {/* Top bar */}
      <div
        className="flex items-center justify-between px-4 py-2 bg-black/40 shrink-0"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 min-w-0">
          <p className="text-sm font-medium text-white truncate">
            {payload.title || t.storyImage}
          </p>
          {model && (
            <span className="text-[10px] bg-blue-900/60 text-blue-300 px-2 py-0.5 rounded shrink-0">
              {model}
            </span>
          )}
          {enhanced && (
            <span className="text-[10px] bg-amber-900/60 text-amber-300 px-2 py-0.5 rounded shrink-0">
              {t.llmEnhanced}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={() => setShowDetails((v) => !v)}
            className="text-xs px-3 py-1 bg-white/10 hover:bg-white/20 text-white rounded transition-colors"
          >
            {showDetails ? t.hideDetails : t.showDetails}
          </button>
          <button
            onClick={onClose}
            className="text-xs px-3 py-1 bg-white/10 hover:bg-white/20 text-white rounded transition-colors"
          >
            {t.close}
          </button>
        </div>
      </div>

      {/* Main content area */}
      <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
        {/* Image */}
        {!showDetails && payload.image_url && (
          <div className="flex-1 flex items-center justify-center p-4" onClick={onClose}>
            <img
              src={payload.image_url}
              alt={payload.prompt || t.storyImage}
              className="max-w-full max-h-full object-contain rounded-lg"
              onClick={(e) => e.stopPropagation()}
            />
          </div>
        )}

        {/* Details panel */}
        {showDetails && (
          <div
            className="flex-1 overflow-y-auto p-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="max-w-5xl mx-auto space-y-4">
              {/* Image preview (smaller when details shown) */}
              {payload.image_url && (
                <img
                  src={payload.image_url}
                  alt={payload.prompt || t.storyImage}
                  className="w-full max-h-[300px] object-contain rounded-lg border border-white/10"
                />
              )}

              {/* Badges */}
              <div className="flex flex-wrap gap-2 text-xs">
                {model && (
                  <span className="bg-blue-900/40 text-blue-300 px-2 py-0.5 rounded">
                    Model: {model}
                  </span>
                )}
                {apiBase && (
                  <span className="bg-violet-900/40 text-violet-300 px-2 py-0.5 rounded truncate max-w-[400px]" title={apiBase}>
                    API: {apiBase}
                  </span>
                )}
                {enhanced && (
                  <span className="bg-amber-900/40 text-amber-300 px-2 py-0.5 rounded">
                    {t.llmEnhanced}
                  </span>
                )}
                {payload.image_id && (
                  <span className="bg-gray-700/40 text-gray-300 px-2 py-0.5 rounded font-mono">
                    ID: {payload.image_id.slice(0, 8)}
                  </span>
                )}
              </div>

              {/* Detail cards */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
                {/* Original prompt from LLM */}
                <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-2">
                  <p className="text-white/60 font-semibold uppercase tracking-wider text-[10px]">{t.originalPrompt}</p>
                  <DetailRow label={t.prompt} value={payload.prompt} />
                  <DetailRow label={t.storyBackground} value={payload.story_background} />
                  <DetailRow label={t.continuityNotes} value={payload.continuity_notes} />
                  {payload.scene_frames && payload.scene_frames.length > 0 && (
                    <DetailRow label={t.sceneFrames} value={payload.scene_frames.join('\n')} />
                  )}
                </div>

                {/* Final prompt sent to image API */}
                <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-2">
                  <p className="text-white/60 font-semibold uppercase tracking-wider text-[10px]">
                    {enhanced ? t.enhancedPrompt : t.generatedPrompt}
                  </p>
                  <pre className="text-foreground/80 whitespace-pre-wrap break-words leading-relaxed">
                    {enhanced || generated || t.none}
                  </pre>
                  {enhanced && generated && (
                    <>
                      <p className="text-white/40 font-semibold uppercase tracking-wider text-[10px] mt-3">
                        {t.preEnhancement}
                      </p>
                      <pre className="text-foreground/60 whitespace-pre-wrap break-words leading-relaxed">
                        {generated}
                      </pre>
                    </>
                  )}
                </div>

                {/* World context */}
                <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-2">
                  <p className="text-white/60 font-semibold uppercase tracking-wider text-[10px]">{t.worldContext}</p>
                  <DetailRow label={t.worldLore} value={payload.debug?.world_lore_excerpt} />
                  <DetailRow label={t.textWorldState} value={payload.debug?.text_world_state} />
                </div>

                {/* Metadata */}
                <div className="bg-white/5 border border-white/10 rounded-lg p-3 space-y-2">
                  <p className="text-white/60 font-semibold uppercase tracking-wider text-[10px]">{t.metadata}</p>
                  <pre className="text-foreground/80 whitespace-pre-wrap break-words leading-relaxed">
                    {JSON.stringify(
                      {
                        image_id: payload.image_id,
                        title: payload.title,
                        status: payload.status,
                        provider_model: model,
                        api_base: apiBase,
                        provider_note: payload.provider_note,
                        layout_preference: payload.layout_preference,
                        reference_image_ids: payload.reference_image_ids,
                        reference_images: payload.reference_images,
                        settings_applied: payload.settings_applied,
                        runtime_settings: payload.debug?.runtime_settings,
                      },
                      null,
                      2,
                    )}
                  </pre>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export function StoryImageRenderer({ data, blockId, onAction, locked }: BlockRendererProps) {
  const language = useUiStore((s) => s.language)
  const t = texts[language] ?? texts.en
  const payload = data && typeof data === 'object' ? (data as StoryImageData) : null
  const [expanded, setExpanded] = useState(false)
  const [reason, setReason] = useState('')
  const [lightboxOpen, setLightboxOpen] = useState(false)

  if (!payload) return null

  const status = payload.status || (payload.image_url ? 'ok' : 'error')
  const canRegenerate = Boolean(payload.can_regenerate) && !locked && (
    !!payload.image_id || (!!payload.story_background && !!payload.prompt)
  )

  const handleRegenerate = () => {
    onAction(
      JSON.stringify({
        type: 'block_response',
        block_type: 'story_image',
        block_id: blockId,
        data: {
          action: 'regenerate',
          image_id: payload.image_id || undefined,
          title: payload.title || undefined,
          story_background: payload.story_background || undefined,
          prompt: payload.prompt || undefined,
          continuity_notes: payload.continuity_notes || undefined,
          reference_image_ids: payload.reference_image_ids || undefined,
          scene_frames: payload.scene_frames || undefined,
          layout_preference: payload.layout_preference || undefined,
          reason: reason.trim() || undefined,
        },
      }),
    )
  }

  return (
    <div className="bg-card border rounded-xl p-3 max-w-[80%] space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium">{payload.title || t.storyImage}</p>
        <span
          className={`text-[10px] px-2 py-0.5 rounded ${
            status === 'ok'
              ? 'bg-emerald-900/60 text-emerald-300'
              : status === 'generating'
                ? 'bg-blue-900/60 text-blue-300'
                : 'bg-red-900/60 text-red-300'
          }`}
        >
          {status === 'ok' ? t.ready : status === 'generating' ? t.generating : t.error}
        </span>
      </div>

      {status === 'generating' ? (
        <div className="flex items-center gap-3 text-sm text-blue-300 bg-blue-900/20 border border-blue-800/40 rounded-lg px-4 py-3">
          <svg className="animate-spin h-4 w-4 shrink-0" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
          </svg>
          {t.imageGenerating}
        </div>
      ) : status === 'ok' && payload.image_url ? (
        <img
          src={payload.image_url}
          alt={payload.prompt || t.storyImage}
          className="w-full max-h-[460px] object-contain rounded-lg border bg-muted"
          loading="lazy"
        />
      ) : (
        <div className="text-sm text-red-300 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
          {payload.error || t.imageFailed}
        </div>
      )}

      {/* Action buttons row — always visible */}
      <div className="flex items-center gap-2 flex-wrap">
        <button
          onClick={() => setLightboxOpen(true)}
          className="text-xs px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded transition-colors"
        >
          {t.viewDetails}
        </button>
        <button
          onClick={handleRegenerate}
          disabled={!canRegenerate}
          className="text-xs px-3 py-1.5 bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-40 disabled:cursor-not-allowed rounded transition-colors"
        >
          {t.regenerate}
        </button>
        {(payload.story_background || payload.prompt || payload.continuity_notes) && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs px-3 py-1.5 text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? t.hideContext : t.context}
          </button>
        )}
      </div>

      {expanded && (
        <div className="space-y-2 text-xs text-foreground/80 bg-muted/50 border rounded-lg px-3 py-2">
          {payload.story_background && (
            <p><span className="text-muted-foreground">{t.background}:</span> {payload.story_background}</p>
          )}
          {payload.prompt && (
            <p><span className="text-muted-foreground">{t.prompt}:</span> {payload.prompt}</p>
          )}
          {payload.continuity_notes && (
            <p><span className="text-muted-foreground">{t.continuity}:</span> {payload.continuity_notes}</p>
          )}
        </div>
      )}

      {canRegenerate && (
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder={t.regenNote}
          className="w-full bg-background border border-input rounded px-2 py-1 text-xs placeholder:text-muted-foreground"
        />
      )}

      {lightboxOpen && <ImageLightbox payload={payload} onClose={() => setLightboxOpen(false)} t={t} />}
    </div>
  )
}
