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
    world_lore_excerpt?: string
    text_world_state?: string
    reference_images?: Array<{ image_id?: string; title?: string }>
    runtime_settings?: Record<string, unknown>
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
        className="w-full max-w-6xl max-h-[90vh] overflow-y-auto bg-slate-900 border border-slate-700 rounded-xl p-4 space-y-3"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <p className="text-sm font-medium text-slate-200">Story Image Debug</p>
          <button onClick={onClose} className="text-xs px-2 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded">
            Close
          </button>
        </div>

        {payload.image_url && (
          <img
            src={payload.image_url}
            alt={payload.prompt || 'story image'}
            className="w-full max-h-[520px] object-contain rounded-lg border border-slate-700 bg-slate-950"
          />
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-xs">
          <div className="bg-slate-950/70 border border-slate-700 rounded p-2 space-y-1">
            <p className="text-slate-400">Metadata</p>
            <pre className="text-slate-300 whitespace-pre-wrap break-words">
              {JSON.stringify(
                {
                  image_id: payload.image_id,
                  title: payload.title,
                  status: payload.status,
                  provider_model: payload.provider_model,
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

          <div className="bg-slate-950/70 border border-slate-700 rounded p-2 space-y-1">
            <p className="text-slate-400">Generated Prompt</p>
            <pre className="text-slate-300 whitespace-pre-wrap break-words">
              {payload.debug?.generated_prompt || '(none)'}
            </pre>
          </div>

          <div className="bg-slate-950/70 border border-slate-700 rounded p-2 space-y-1">
            <p className="text-slate-400">World Lore Snapshot</p>
            <pre className="text-slate-300 whitespace-pre-wrap break-words">
              {payload.debug?.world_lore_excerpt || '(none)'}
            </pre>
          </div>

          <div className="bg-slate-950/70 border border-slate-700 rounded p-2 space-y-1">
            <p className="text-slate-400">Current Text World State</p>
            <pre className="text-slate-300 whitespace-pre-wrap break-words">
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
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-3 max-w-[80%] space-y-2">
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-200">{payload.title || 'Story Image'}</p>
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
          className="w-full max-h-[460px] object-contain rounded-lg border border-slate-700 bg-slate-900 cursor-zoom-in"
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
            className="text-xs text-slate-400 hover:text-slate-200 transition-colors"
          >
            {expanded ? 'Hide context' : 'Show context'}
          </button>
          {expanded && (
            <div className="space-y-2 text-xs text-slate-300 bg-slate-900/60 border border-slate-700 rounded-lg px-3 py-2">
              {payload.story_background && (
                <p><span className="text-slate-400">Background:</span> {payload.story_background}</p>
              )}
              {payload.prompt && (
                <p><span className="text-slate-400">Prompt:</span> {payload.prompt}</p>
              )}
              {payload.continuity_notes && (
                <p><span className="text-slate-400">Continuity:</span> {payload.continuity_notes}</p>
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
          className="w-full bg-slate-900/70 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 placeholder-slate-500 disabled:opacity-50"
        />
        <button
          onClick={handleRegenerate}
          disabled={!canRegenerate}
          className="text-xs px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 disabled:cursor-not-allowed text-slate-100 rounded transition-colors"
        >
          Regenerate image
        </button>
        <button
          onClick={() => setPreviewOpen(true)}
          className="text-xs px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded transition-colors"
        >
          Debug preview
        </button>
      </div>

      {previewOpen && <DebugModal payload={payload} onClose={() => setPreviewOpen(false)} />}
    </div>
  )
}
