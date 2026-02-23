import { useState } from 'react'
import type { BlockRendererProps } from '../../services/blockRenderers'

interface StoryImageData {
  status?: 'ok' | 'error'
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

function DebugModal({
  payload,
  onClose,
}: {
  payload: StoryImageData
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className="w-full max-w-6xl max-h-[90vh] overflow-y-auto bg-popover border rounded-xl p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium">Image Details</p>
          <button onClick={onClose} className="text-xs px-2 py-1 bg-muted hover:bg-muted/80 rounded">
            Close
          </button>
        </div>

        {payload.image_url && (
          <img
            src={payload.image_url}
            alt={payload.prompt || 'story image'}
            className="w-full max-h-[520px] object-contain rounded-lg border bg-muted"
          />
        )}

        {/* Model & Generation Info */}
        <div className="flex flex-wrap gap-2 text-xs">
          {(payload.debug?.provider_model || payload.provider_model) && (
            <span className="bg-blue-900/40 text-blue-300 px-2 py-0.5 rounded">
              Model: {payload.debug?.provider_model || payload.provider_model}
            </span>
          )}
          {payload.debug?.api_base && (
            <span className="bg-violet-900/40 text-violet-300 px-2 py-0.5 rounded truncate max-w-[300px]" title={payload.debug.api_base}>
              API: {payload.debug.api_base}
            </span>
          )}
          {payload.debug?.enhanced_prompt && (
            <span className="bg-amber-900/40 text-amber-300 px-2 py-0.5 rounded">
              LLM Enhanced
            </span>
          )}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          {/* Original Prompt (from LLM block) */}
          <div className="bg-muted/50 border rounded p-2 space-y-1">
            <p className="text-muted-foreground">Original Prompt</p>
            <pre className="text-foreground/80 whitespace-pre-wrap break-words">
              {payload.prompt || '(none)'}
            </pre>
            {payload.story_background && (
              <>
                <p className="text-muted-foreground mt-2">Story Background</p>
                <pre className="text-foreground/80 whitespace-pre-wrap break-words">
                  {payload.story_background}
                </pre>
              </>
            )}
            {payload.continuity_notes && (
              <>
                <p className="text-muted-foreground mt-2">Continuity Notes</p>
                <pre className="text-foreground/80 whitespace-pre-wrap break-words">
                  {payload.continuity_notes}
                </pre>
              </>
            )}
          </div>

          {/* Final Generated Prompt (sent to image API) */}
          <div className="bg-muted/50 border rounded p-2 space-y-1">
            <p className="text-muted-foreground">
              {payload.debug?.enhanced_prompt ? 'LLM Enhanced Prompt' : 'Generated Prompt'}
            </p>
            <pre className="text-foreground/80 whitespace-pre-wrap break-words">
              {payload.debug?.enhanced_prompt || payload.debug?.generated_prompt || '(none)'}
            </pre>
            {payload.debug?.enhanced_prompt && payload.debug?.generated_prompt && (
              <>
                <p className="text-muted-foreground mt-2">Pre-Enhancement Prompt</p>
                <pre className="text-foreground/60 whitespace-pre-wrap break-words">
                  {payload.debug.generated_prompt}
                </pre>
              </>
            )}
          </div>

          {/* Metadata */}
          <div className="bg-muted/50 border rounded p-2 space-y-1">
            <p className="text-muted-foreground">Metadata</p>
            <pre className="text-foreground/80 whitespace-pre-wrap break-words">
              {JSON.stringify(
                {
                  image_id: payload.image_id,
                  title: payload.title,
                  status: payload.status,
                  provider_model: payload.debug?.provider_model || payload.provider_model,
                  provider_note: payload.provider_note,
                  layout_preference: payload.layout_preference,
                  reference_image_ids: payload.reference_image_ids,
                  scene_frames: payload.scene_frames,
                  reference_images: payload.reference_images,
                  settings_applied: payload.settings_applied,
                },
                null,
                2,
              )}
            </pre>
          </div>

          {/* World Context */}
          <div className="bg-muted/50 border rounded p-2 space-y-1">
            <p className="text-muted-foreground">World Lore Snapshot</p>
            <pre className="text-foreground/80 whitespace-pre-wrap break-words">
              {payload.debug?.world_lore_excerpt || '(none)'}
            </pre>
            <p className="text-muted-foreground mt-2">Current Text World State</p>
            <pre className="text-foreground/80 whitespace-pre-wrap break-words">
              {payload.debug?.text_world_state || '(none)'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  )
}

export function StoryImageRenderer({ data, blockId, onAction, locked }: BlockRendererProps) {
  const payload = data && typeof data === 'object' ? (data as StoryImageData) : null
  const [expanded, setExpanded] = useState(false)
  const [reason, setReason] = useState('')
  const [previewOpen, setPreviewOpen] = useState(false)

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
        <p className="text-sm font-medium">{payload.title || 'Story Image'}</p>
        <span
          className={`text-[10px] px-2 py-0.5 rounded ${
            status === 'ok'
              ? 'bg-emerald-900/60 text-emerald-300'
              : 'bg-red-900/60 text-red-300'
          }`}
        >
          {status === 'ok' ? 'ready' : 'error'}
        </span>
      </div>

      {status === 'ok' && payload.image_url ? (
        <img
          src={payload.image_url}
          alt={payload.prompt || 'story image'}
          className="w-full max-h-[460px] object-contain rounded-lg border bg-muted cursor-zoom-in"
          loading="lazy"
          onClick={() => setPreviewOpen(true)}
        />
      ) : (
        <div className="text-sm text-red-300 bg-red-900/20 border border-red-800/40 rounded-lg px-3 py-2">
          {payload.error || 'Image generation failed.'}
        </div>
      )}

      {(payload.story_background || payload.prompt || payload.continuity_notes) && (
        <div className="space-y-2">
          <button
            onClick={() => setExpanded((v) => !v)}
            className="text-xs text-muted-foreground hover:text-foreground transition-colors"
          >
            {expanded ? 'Hide context' : 'Show context'}
          </button>
          {expanded && (
            <div className="space-y-2 text-xs text-foreground/80 bg-muted/50 border rounded-lg px-3 py-2">
              {payload.story_background && (
                <p><span className="text-muted-foreground">Background:</span> {payload.story_background}</p>
              )}
              {payload.prompt && (
                <p><span className="text-muted-foreground">Prompt:</span> {payload.prompt}</p>
              )}
              {payload.continuity_notes && (
                <p><span className="text-muted-foreground">Continuity:</span> {payload.continuity_notes}</p>
              )}
            </div>
          )}
        </div>
      )}

      <div className="space-y-1">
        <input
          type="text"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          disabled={!canRegenerate}
          placeholder="Optional regeneration note"
          className="w-full bg-background border border-input rounded px-2 py-1 text-xs placeholder:text-muted-foreground disabled:opacity-50"
        />
        <button
          onClick={handleRegenerate}
          disabled={!canRegenerate}
          className="text-xs px-3 py-1.5 bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-40 disabled:cursor-not-allowed rounded transition-colors"
        >
          Regenerate image
        </button>
        <button
          onClick={() => setPreviewOpen(true)}
          className="text-xs px-3 py-1.5 bg-muted hover:bg-muted/80 text-foreground rounded transition-colors"
        >
          Image details
        </button>
      </div>

      {previewOpen && <DebugModal payload={payload} onClose={() => setPreviewOpen(false)} />}
    </div>
  )
}
