import { useEffect, useRef, useState, useCallback } from 'react'
import Markdown from 'react-markdown'
import { useSessionStore } from '../../stores/sessionStore'
import type { StreamStatus } from '../../stores/sessionStore'
import { getBlockRenderer } from '../../services/blockRenderers'
import type { Message, StoryImageData } from '../../types'

interface Props {
  onAction: (msg: string) => void
  onRetry?: () => void
  onGenerateImage?: (messageId: string) => void
}

/** Fallback for block types with no registered renderer. */
function FallbackBlock({ type, data }: { type: string; data: any }) {
  return (
    <details className="bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-2 max-w-[80%] text-xs">
      <summary className="text-slate-400 cursor-pointer">
        Block: <code>{type}</code>
      </summary>
      <pre className="mt-1 text-slate-500 overflow-x-auto">
        {JSON.stringify(data, null, 2)}
      </pre>
    </details>
  )
}

/** Render a list of blocks (attached to a message or pending). */
function BlockList({
  blocks,
  onAction,
  locked,
  idPrefix,
}: {
  blocks: { type: string; data: unknown; block_id?: string }[]
  onAction: (msg: string) => void
  locked?: boolean
  idPrefix: string
}) {
  return (
    <>
      {blocks.map((block, i) => {
        const Renderer = getBlockRenderer(block.type)
        const blockId = block.block_id || `${idPrefix}:${i}:${block.type}`
        return (
          <div key={blockId} className="flex justify-start">
            {Renderer ? (
              <Renderer
                data={block.data}
                blockId={blockId}
                onAction={onAction}
                locked={locked}
              />
            ) : (
              <FallbackBlock type={block.type} data={block.data} />
            )}
          </div>
        )
      })}
    </>
  )
}

/** Hover action bar for messages. */
function MessageActions({
  msg,
  isLast,
  onCopy,
  onDelete,
  onRegenerate,
  onEdit,
  onGenerateImage,
  imageLoading,
  hasImage,
}: {
  msg: Message
  isLast: boolean
  onCopy: () => void
  onDelete: () => void
  onRegenerate?: () => void
  onEdit?: () => void
  onGenerateImage?: () => void
  imageLoading?: boolean
  hasImage?: boolean
}) {
  return (
    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
      <button onClick={onCopy} className="p-1 text-slate-500 hover:text-slate-300 rounded transition-colors" title="复制">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" strokeWidth="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" strokeWidth="2" />
        </svg>
      </button>
      {msg.role === 'assistant' && onGenerateImage && (
        <button
          onClick={onGenerateImage}
          disabled={imageLoading}
          className="p-1 text-slate-500 hover:text-purple-400 rounded transition-colors disabled:animate-pulse"
          title={hasImage ? "重新生成配图" : "生成配图"}
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <polyline points="21 15 16 10 5 21" />
          </svg>
        </button>
      )}
      {msg.role === 'assistant' && isLast && onRegenerate && (
        <button onClick={onRegenerate} className="p-1 text-slate-500 hover:text-slate-300 rounded transition-colors" title="重新生成">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path d="M1 4v6h6M23 20v-6h-6" />
            <path d="M20.49 9A9 9 0 005.64 5.64L1 10m22 4l-4.64 4.36A9 9 0 013.51 15" />
          </svg>
        </button>
      )}
      {msg.role === 'user' && onEdit && (
        <button onClick={onEdit} className="p-1 text-slate-500 hover:text-slate-300 rounded transition-colors" title="编辑并重新发送">
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
            <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
        </button>
      )}
      <button onClick={onDelete} className="p-1 text-slate-500 hover:text-red-400 rounded transition-colors" title="删除">
        <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" strokeWidth="2">
          <polyline points="3 6 5 6 21 6" />
          <path d="M19 6v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2" />
        </svg>
      </button>
    </div>
  )
}

/** Raw message inspector overlay. */
function RawMessageViewer({ msg, onClose }: { msg: Message; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={onClose}>
      <div
        className="bg-slate-800 border border-slate-600 rounded-xl shadow-2xl max-w-2xl w-full mx-4 max-h-[80vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700">
          <span className="text-sm text-slate-300 font-medium">消息原始数据</span>
          <button onClick={onClose} className="text-slate-500 hover:text-slate-300 text-lg leading-none">&times;</button>
        </div>
        <div className="flex-1 overflow-y-auto p-4 space-y-3 text-xs font-mono">
          <div>
            <span className="text-slate-500">ID: </span>
            <span className="text-slate-400">{msg.id}</span>
          </div>
          <div>
            <span className="text-slate-500">Role: </span>
            <span className="text-slate-400">{msg.role}</span>
          </div>
          <div>
            <span className="text-slate-500">Type: </span>
            <span className="text-slate-400">{msg.message_type}</span>
          </div>
          {msg.scene_id && (
            <div>
              <span className="text-slate-500">Scene: </span>
              <span className="text-slate-400">{msg.scene_id}</span>
            </div>
          )}
          <div>
            <span className="text-slate-500 block mb-1">Content:</span>
            <pre className="text-slate-300 whitespace-pre-wrap bg-slate-900 rounded p-2 overflow-x-auto">{msg.content}</pre>
          </div>
          {msg.raw_content && msg.raw_content !== msg.content && (
            <div>
              <span className="text-slate-500 block mb-1">Raw Content (with json blocks):</span>
              <pre className="text-slate-300 whitespace-pre-wrap bg-slate-900 rounded p-2 overflow-x-auto">{msg.raw_content}</pre>
            </div>
          )}
          {msg.blocks && msg.blocks.length > 0 && (
            <div>
              <span className="text-slate-500 block mb-1">Blocks ({msg.blocks.length}):</span>
              <pre className="text-slate-300 whitespace-pre-wrap bg-slate-900 rounded p-2 overflow-x-auto">
                {JSON.stringify(msg.blocks, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

/** Fullscreen image preview modal. */
function ImagePreviewModal({ image, onClose }: { image: StoryImageData; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 bg-black/80 flex items-center justify-center" onClick={onClose}>
      <img
        src={image.image_url}
        alt={image.title || 'Story image'}
        className="max-w-[90vw] max-h-[90vh] object-contain rounded-lg"
        onClick={(e) => e.stopPropagation()}
      />
    </div>
  )
}

/** Inline image strip rendered below a message. */
function MessageImageStrip({
  images,
  onPreview,
}: {
  images: StoryImageData[]
  onPreview: (image: StoryImageData) => void
}) {
  return (
    <div className="flex justify-start pl-1">
      <div className="max-w-[80%] space-y-1.5">
        {images.map((img, i) => (
          <div key={img.image_id || i} className="relative group/img">
            <img
              src={img.image_url}
              alt={img.title || 'Story image'}
              className="w-full max-h-[400px] object-contain rounded-xl border border-slate-700/50
                         bg-slate-900 shadow-lg cursor-zoom-in"
              loading="lazy"
              onClick={() => onPreview(img)}
            />
            {img.title && (
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent
                              rounded-b-xl px-3 py-1.5 opacity-0 group-hover/img:opacity-100 transition-opacity">
                <span className="text-xs text-white/80">{img.title}</span>
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export function ChatMessages({ onAction, onRetry, onGenerateImage }: Props) {
  const { messages, isStreaming, streamingContent, streamStatus, pendingBlocks, deleteMessage, deleteMessagesFrom, messageImages, imageLoadingMessages } = useSessionStore()
  const bottomRef = useRef<HTMLDivElement>(null)
  const [inspectMsg, setInspectMsg] = useState<Message | null>(null)
  const [previewImage, setPreviewImage] = useState<StoryImageData | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editText, setEditText] = useState('')

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, streamingContent, pendingBlocks])

  const handleCopy = useCallback((content: string) => {
    navigator.clipboard.writeText(content).catch(() => {})
  }, [])

  const handleDelete = useCallback((msgId: string) => {
    deleteMessage(msgId)
  }, [deleteMessage])

  const handleDeleteFrom = useCallback((msgId: string) => {
    // Delete this message and all subsequent ones (used when deleting user msg to also remove assistant response)
    deleteMessagesFrom(msgId)
  }, [deleteMessagesFrom])

  const handleEdit = useCallback((msg: Message) => {
    setEditingId(msg.id)
    setEditText(msg.content)
  }, [])

  const handleEditSubmit = useCallback((msgId: string) => {
    const text = editText.trim()
    if (!text) return
    // Delete from this message onward, then send the edited text
    deleteMessagesFrom(msgId)
    setEditingId(null)
    setEditText('')
    onAction(text)
  }, [editText, deleteMessagesFrom, onAction])

  const handleEditCancel = useCallback(() => {
    setEditingId(null)
    setEditText('')
  }, [])

  const handleEditKeyDown = useCallback((e: React.KeyboardEvent, msgId: string) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault()
      handleEditSubmit(msgId)
    }
    if (e.key === 'Escape') {
      handleEditCancel()
    }
  }, [handleEditSubmit, handleEditCancel])

  // Determine if a message's blocks should be locked:
  // Blocks are unlocked only on the very last assistant message (and only if there's no newer user message after it)
  const lastMsgIndex = messages.length - 1

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-3">
      {messages.length === 0 && !isStreaming && (
        <div className="text-center py-16 space-y-2">
          <p className="text-base font-medium" style={{ color: 'rgba(127,168,196,0.4)' }}>Begin your adventure</p>
          <p className="text-xs" style={{ color: 'rgba(127,168,196,0.25)' }}>Send a message to start the game</p>
        </div>
      )}

      {messages.map((msg, idx) => {
        const isLast = idx === lastMsgIndex
        // Blocks are locked unless this is the last message in the list
        const blocksLocked = !isLast

        if (msg.role === 'system') {
          return (
            <div key={msg.id} className="flex justify-center group">
              <div className="text-xs px-3 py-1.5 rounded-full max-w-md text-center"
                style={{
                  background: 'rgba(139, 92, 246, 0.08)',
                  border: '1px solid rgba(139, 92, 246, 0.15)',
                  color: 'rgba(167, 139, 250, 0.6)',
                }}
              >
                {msg.content}
              </div>
            </div>
          )
        }

        if (msg.role === 'user') {
          // Editing mode
          if (editingId === msg.id) {
            return (
              <div key={msg.id} className="flex justify-end">
                <div className="bg-emerald-900/60 border border-emerald-500/50 rounded-2xl rounded-br-sm max-w-[75%] p-2 space-y-2">
                  <textarea
                    value={editText}
                    onChange={(e) => setEditText(e.target.value)}
                    onKeyDown={(e) => handleEditKeyDown(e, msg.id)}
                    className="w-full bg-slate-900/60 text-slate-100 text-sm rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-emerald-500/50 min-h-[60px]"
                    rows={2}
                    autoFocus
                  />
                  <div className="flex justify-end gap-2">
                    <button onClick={handleEditCancel} className="text-xs px-2 py-1 text-slate-400 hover:text-slate-200 transition-colors">
                      取消
                    </button>
                    <button
                      onClick={() => handleEditSubmit(msg.id)}
                      disabled={!editText.trim()}
                      className="text-xs px-3 py-1 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white rounded transition-colors"
                    >
                      发送
                    </button>
                  </div>
                </div>
              </div>
            )
          }

          return (
            <div key={msg.id} className="flex justify-end group">
              <div className="flex items-end gap-1">
                <MessageActions
                  msg={msg}
                  isLast={isLast}
                  onCopy={() => handleCopy(msg.content)}
                  onDelete={() => handleDeleteFrom(msg.id)}
                  onEdit={() => handleEdit(msg)}
                />
                <div
                  className="px-4 py-2.5 rounded-2xl rounded-br-sm max-w-[75%] text-sm cursor-pointer transition-all duration-200"
                  style={{
                    background: 'linear-gradient(135deg, rgba(16,185,129,0.18) 0%, rgba(6,182,212,0.12) 100%)',
                    border: '1px solid rgba(16, 185, 129, 0.25)',
                    color: '#dff0f7',
                  }}
                  onClick={() => setInspectMsg(msg)}
                  title="点击查看原始数据"
                >
                  {msg.content}
                </div>
              </div>
            </div>
          )
        }

        // assistant — render content + attached blocks
        return (
          <div key={msg.id} className="space-y-2 group">
            <div className="flex justify-start">
              <div className="flex items-end gap-1">
                <div
                  className="px-4 py-2.5 rounded-2xl rounded-bl-sm max-w-[80%] text-sm markdown-content cursor-pointer transition-all duration-200"
                  style={{
                    background: 'rgba(16, 28, 46, 0.75)',
                    border: '1px solid rgba(148, 163, 184, 0.1)',
                    color: '#dff0f7',
                    backdropFilter: 'blur(8px)',
                  }}
                  onClick={() => setInspectMsg(msg)}
                  title="点击查看原始数据"
                >
                  <Markdown>{msg.content}</Markdown>
                </div>
                <MessageActions
                  msg={msg}
                  isLast={isLast}
                  onCopy={() => handleCopy(msg.content)}
                  onDelete={() => handleDelete(msg.id)}
                  onRegenerate={isLast && !isStreaming ? onRetry : undefined}
                  onGenerateImage={onGenerateImage ? () => onGenerateImage(msg.id) : undefined}
                  imageLoading={imageLoadingMessages.has(msg.id)}
                  hasImage={!!messageImages[msg.id]?.length}
                />
              </div>
            </div>
            {/* Inline story images for this message */}
            {messageImages[msg.id]?.length > 0 && (
              <MessageImageStrip
                images={messageImages[msg.id]}
                onPreview={setPreviewImage}
              />
            )}
            {imageLoadingMessages.has(msg.id) && (
              <div className="flex justify-start pl-1">
                <div className="bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 max-w-[80%] flex items-center gap-2">
                  <span className="w-4 h-4 border-2 border-purple-400 border-t-transparent rounded-full animate-spin" />
                  <span className="text-xs text-slate-400">生成配图中...</span>
                </div>
              </div>
            )}
            {/* Render blocks attached to this message */}
            {msg.blocks && msg.blocks.length > 0 && (
              <BlockList
                blocks={msg.blocks}
                onAction={onAction}
                locked={blocksLocked}
                idPrefix={msg.id}
              />
            )}
          </div>
        )
      })}

      {isStreaming && streamingContent && (
        <div className="flex justify-start">
          <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm max-w-[80%] text-sm markdown-content"
            style={{
              background: 'rgba(16, 28, 46, 0.75)',
              border: '1px solid rgba(16, 185, 129, 0.15)',
              color: '#dff0f7',
              backdropFilter: 'blur(8px)',
              boxShadow: '0 0 20px rgba(16, 185, 129, 0.05)',
            }}
          >
            <Markdown>{streamingContent}</Markdown>
            <span className="streaming-cursor" />
          </div>
        </div>
      )}

      {isStreaming && !streamingContent && (
        <div className="flex justify-start">
          <div className="px-4 py-2.5 rounded-2xl rounded-bl-sm text-sm"
            style={{
              background: 'rgba(16, 28, 46, 0.75)',
              border: '1px solid rgba(148, 163, 184, 0.08)',
              color: 'rgba(127, 168, 196, 0.6)',
            }}
          >
            <span className="flex gap-1">
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </span>
          </div>
        </div>
      )}

      {/* Render pending interactive blocks (not yet attached to a message) */}
      {pendingBlocks.length > 0 && (
        <BlockList
          blocks={pendingBlocks.map((b) => ({
            type: b.type,
            data: b.data,
            block_id: b.blockId,
          }))}
          onAction={onAction}
          idPrefix="pending"
        />
      )}

      {/* Status indicator */}
      <StatusBar status={streamStatus} onRetry={onRetry} />

      <div ref={bottomRef} />

      {/* Raw message inspector */}
      {inspectMsg && <RawMessageViewer msg={inspectMsg} onClose={() => setInspectMsg(null)} />}

      {/* Image preview modal */}
      {previewImage && <ImagePreviewModal image={previewImage} onClose={() => setPreviewImage(null)} />}
    </div>
  )
}

function StatusBar({ status, onRetry }: { status: StreamStatus; onRetry?: () => void }) {
  if (status === 'idle') return null

  const config: Record<StreamStatus, { label: string; color: string; icon: React.ReactNode }> = {
    idle: { label: '', color: '', icon: null },
    waiting: {
      label: '等待响应...',
      color: 'text-amber-400',
      icon: (
        <span className="flex gap-0.5">
          <span className="w-1 h-1 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
          <span className="w-1 h-1 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
          <span className="w-1 h-1 bg-amber-400 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
        </span>
      ),
    },
    streaming: {
      label: '生成中...',
      color: 'text-cyan-400',
      icon: <span className="w-1.5 h-1.5 bg-cyan-400 rounded-full animate-pulse" />,
    },
    done: {
      label: '生成完成',
      color: 'text-emerald-400',
      icon: <span className="text-emerald-400">&#10003;</span>,
    },
    error: {
      label: '生成失败',
      color: 'text-red-400',
      icon: <span className="text-red-400">&#10007;</span>,
    },
  }

  const c = config[status]
  return (
    <div className={`flex items-center gap-2 px-2 py-1 text-xs ${c.color}`}>
      {c.icon}
      <span>{c.label}</span>
      {status === 'error' && onRetry && (
        <button
          onClick={onRetry}
          className="ml-2 px-2 py-0.5 bg-red-900/50 hover:bg-red-800/60 border border-red-700/50 text-red-300 rounded text-xs transition-colors"
        >
          重试
        </button>
      )}
    </div>
  )
}
