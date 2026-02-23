import { useEffect, useRef, useState, useCallback } from 'react'
import Markdown from 'react-markdown'
import { Copy, Image as ImageIcon, RotateCcw, Pencil, Trash2, X, AlertCircle, CheckCircle2 } from 'lucide-react'
import { useSessionStore } from '../../stores/sessionStore'
import { useUiStore } from '../../stores/uiStore'
import type { StreamStatus } from '../../stores/sessionStore'
import { getBlockRenderer } from '../../services/blockRenderers'
import type { Message, StoryImageData } from '../../types'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { Alert, AlertDescription } from '@/components/ui/alert'

interface Props {
  onAction: (msg: string) => void
  onRetry?: () => void
  onGenerateImage?: (messageId: string) => void
}

const chatText: Record<string, Record<string, string>> = {
  zh: {
    block: '区块',
    copy: '复制',
    regenerateImage: '重新生成配图',
    generateImage: '生成配图',
    regenerate: '重新生成',
    editAndResend: '编辑并重新发送',
    delete: '删除',
    rawMessageData: '消息原始数据',
    id: 'ID',
    role: '角色',
    type: '类型',
    scene: '场景',
    content: '内容',
    rawContent: '原始内容',
    blocks: '区块',
    close: '关闭',
    storyImageAlt: '剧情配图',
    beginAdventure: '开始你的冒险',
    beginAdventureHint: '发送一条消息以开始游戏',
    cancel: '取消',
    send: '发送',
    clickViewRaw: '点击查看原始数据',
    generatingImage: '生成配图中...',
    generationFailed: '生成失败',
    retry: '重试',
    generationDone: '生成完成',
  },
  en: {
    block: 'Block',
    copy: 'Copy',
    regenerateImage: 'Regenerate image',
    generateImage: 'Generate image',
    regenerate: 'Regenerate',
    editAndResend: 'Edit and resend',
    delete: 'Delete',
    rawMessageData: 'Raw Message Data',
    id: 'ID',
    role: 'Role',
    type: 'Type',
    scene: 'Scene',
    content: 'Content',
    rawContent: 'Raw Content',
    blocks: 'Blocks',
    close: 'Close',
    storyImageAlt: 'Story image',
    beginAdventure: 'Begin your adventure',
    beginAdventureHint: 'Send a message to start the game',
    cancel: 'Cancel',
    send: 'Send',
    clickViewRaw: 'Click to view raw data',
    generatingImage: 'Generating image...',
    generationFailed: 'Generation failed',
    retry: 'Retry',
    generationDone: 'Done',
  },
}

/** Fallback for block types with no registered renderer. */
function FallbackBlock({ type, data, label }: { type: string; data: unknown; label: string }) {
  return (
    <details className="bg-muted/50 border rounded-xl px-4 py-2 max-w-[80%] text-xs">
      <summary className="text-muted-foreground cursor-pointer font-medium hover:text-foreground">
        {label}: <code className="bg-muted px-1 py-0.5 rounded">{type}</code>
      </summary>
      <pre className="mt-2 text-muted-foreground overflow-x-auto bg-background/50 p-2 rounded-md border border-border/50">
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
  t,
}: {
  blocks: { type: string; data: unknown; block_id?: string }[]
  onAction: (msg: string) => void
  locked?: boolean
  idPrefix: string
  t: Record<string, string>
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
              <FallbackBlock type={block.type} data={block.data} label={t.block} />
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
  t,
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
  t: Record<string, string>
}) {
  return (
    <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={onCopy}>
            <Copy className="w-3.5 h-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent><p>{t.copy}</p></TooltipContent>
      </Tooltip>

      {msg.role === 'assistant' && onGenerateImage && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button 
              variant="ghost" 
              size="icon" 
              className="h-6 w-6 text-muted-foreground hover:text-purple-400 disabled:opacity-50" 
              onClick={onGenerateImage}
              disabled={imageLoading}
            >
              <ImageIcon className={`w-3.5 h-3.5 ${imageLoading ? 'animate-pulse' : ''}`} />
            </Button>
          </TooltipTrigger>
          <TooltipContent><p>{hasImage ? t.regenerateImage : t.generateImage}</p></TooltipContent>
        </Tooltip>
      )}

      {msg.role === 'assistant' && isLast && onRegenerate && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={onRegenerate}>
              <RotateCcw className="w-3.5 h-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent><p>{t.regenerate}</p></TooltipContent>
        </Tooltip>
      )}

      {msg.role === 'user' && onEdit && (
        <Tooltip>
          <TooltipTrigger asChild>
            <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-foreground" onClick={onEdit}>
              <Pencil className="w-3.5 h-3.5" />
            </Button>
          </TooltipTrigger>
          <TooltipContent><p>{t.editAndResend}</p></TooltipContent>
        </Tooltip>
      )}

      <Tooltip>
        <TooltipTrigger asChild>
          <Button variant="ghost" size="icon" className="h-6 w-6 text-muted-foreground hover:text-destructive" onClick={onDelete}>
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        </TooltipTrigger>
        <TooltipContent><p>{t.delete}</p></TooltipContent>
      </Tooltip>
    </div>
  )
}

/** Raw message inspector overlay. */
function RawMessageViewer({ msg, onClose, t }: { msg: Message; onClose: () => void; t: Record<string, string> }) {
  return (
    <Dialog open={true} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-w-2xl max-h-[80vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-4 py-3 border-b shrink-0">
          <DialogTitle className="text-sm font-medium">{t.rawMessageData}</DialogTitle>
        </DialogHeader>
        <div className="flex-1 overflow-y-auto p-4 space-y-4 text-xs font-mono">
          <div className="grid grid-cols-[100px_1fr] gap-2">
            <span className="text-muted-foreground">{t.id}:</span>
            <span className="text-foreground">{msg.id}</span>
            
            <span className="text-muted-foreground">{t.role}:</span>
            <span className="text-foreground">{msg.role}</span>
            
            <span className="text-muted-foreground">{t.type}:</span>
            <span className="text-foreground">{msg.message_type}</span>
            
            {msg.scene_id && (
              <>
                <span className="text-muted-foreground">{t.scene}:</span>
                <span className="text-foreground">{msg.scene_id}</span>
              </>
            )}
          </div>
          
          <div className="space-y-1.5">
            <span className="text-muted-foreground block font-medium">{t.content}:</span>
            <pre className="text-foreground whitespace-pre-wrap bg-muted/50 border rounded-md p-3 overflow-x-auto">
              {msg.content}
            </pre>
          </div>
          
          {msg.raw_content && msg.raw_content !== msg.content && (
            <div className="space-y-1.5">
              <span className="text-muted-foreground block font-medium">{t.rawContent}:</span>
              <pre className="text-foreground whitespace-pre-wrap bg-muted/50 border rounded-md p-3 overflow-x-auto">
                {msg.raw_content}
              </pre>
            </div>
          )}
          
          {msg.blocks && msg.blocks.length > 0 && (
            <div className="space-y-1.5">
              <span className="text-muted-foreground block font-medium">{t.blocks} ({msg.blocks.length}):</span>
              <pre className="text-foreground whitespace-pre-wrap bg-muted/50 border rounded-md p-3 overflow-x-auto">
                {JSON.stringify(msg.blocks, null, 2)}
              </pre>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}

/** Fullscreen image preview modal. */
function ImagePreviewModal({ image, onClose, closeLabel, altLabel }: { image: StoryImageData; onClose: () => void; closeLabel: string; altLabel: string }) {
  return (
    <div className="fixed inset-0 z-50 bg-background/95 backdrop-blur-sm flex items-center justify-center p-4 sm:p-8" onClick={onClose}>
      <Button 
        variant="ghost" 
        size="icon" 
        className="absolute top-4 right-4 rounded-full bg-background/20 hover:bg-background/40 text-foreground backdrop-blur-md"
        onClick={onClose}
        aria-label={closeLabel}
      >
        <X className="w-5 h-5" />
      </Button>
      <img
        src={image.image_url}
        alt={image.title || altLabel}
        className="max-w-full max-h-full object-contain rounded-lg shadow-2xl ring-1 ring-border/50"
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
    <div className="flex justify-start pl-1 pt-1">
      <div className="max-w-[80%] space-y-2">
        {images.map((img, i) => (
          <div key={img.image_id || i} className="relative group/img overflow-hidden rounded-xl border bg-muted shadow-sm">
            <img
              src={img.image_url}
              alt={img.title || 'Story image'}
              className="w-full max-h-[400px] object-cover cursor-zoom-in transition-transform duration-300 group-hover/img:scale-[1.02]"
              loading="lazy"
              onClick={() => onPreview(img)}
            />
            {img.title && (
              <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 via-black/40 to-transparent px-4 py-3 opacity-0 group-hover/img:opacity-100 transition-opacity duration-300">
                <span className="text-xs text-white font-medium drop-shadow-md">{img.title}</span>
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
  const language = useUiStore((s) => s.language)
  const t = chatText[language] ?? chatText.en
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
    deleteMessagesFrom(msgId)
  }, [deleteMessagesFrom])

  const handleEdit = useCallback((msg: Message) => {
    setEditingId(msg.id)
    setEditText(msg.content)
  }, [])

  const handleEditSubmit = useCallback((msgId: string) => {
    const text = editText.trim()
    if (!text) return
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

  const lastMsgIndex = messages.length - 1

  return (
    <div className="flex-1 overflow-y-auto p-4 md:p-6 space-y-6 scroll-smooth bg-background">
      {messages.length === 0 && !isStreaming && (
        <div className="flex flex-col items-center justify-center h-full text-muted-foreground opacity-50">
          <p className="text-lg font-medium mb-2">{t.beginAdventure}</p>
          <p className="text-sm">{t.beginAdventureHint}</p>
        </div>
      )}

      <div className="max-w-4xl mx-auto space-y-6">
        {messages.map((msg, idx) => {
          const isLast = idx === lastMsgIndex
          const blocksLocked = !isLast

          if (msg.role === 'system') {
            return (
              <div key={msg.id} className="flex justify-center group py-2">
                <Badge variant="secondary" className="px-4 py-1.5 text-xs font-normal bg-muted text-muted-foreground shadow-sm whitespace-normal text-center max-w-lg break-words">
                  {msg.content}
                </Badge>
              </div>
            )
          }

          if (msg.role === 'user') {
            if (editingId === msg.id) {
              return (
                <div key={msg.id} className="flex justify-end">
                  <div className="bg-muted border rounded-2xl rounded-tr-sm max-w-[85%] p-3 space-y-3 shadow-sm w-full sm:w-[400px]">
                    <textarea
                      value={editText}
                      onChange={(e) => setEditText(e.target.value)}
                      onKeyDown={(e) => handleEditKeyDown(e, msg.id)}
                      className="w-full bg-background text-foreground text-sm rounded-lg px-3 py-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary min-h-[80px] border"
                      rows={3}
                      autoFocus
                    />
                    <div className="flex justify-end gap-2">
                      <Button variant="ghost" size="sm" onClick={handleEditCancel}>
                        {t.cancel}
                      </Button>
                      <Button
                        size="sm"
                        onClick={() => handleEditSubmit(msg.id)}
                        disabled={!editText.trim()}
                      >
                        {t.send}
                      </Button>
                    </div>
                  </div>
                </div>
              )
            }

            return (
              <div key={msg.id} className="flex justify-end group">
                <div className="flex items-end gap-2 flex-row-reverse">
                  <div
                    className="px-5 py-3 rounded-2xl rounded-tr-sm max-w-[85%] text-sm shadow-sm cursor-pointer transition-all bg-primary text-primary-foreground hover:bg-primary/90"
                    onClick={() => setInspectMsg(msg)}
                    title={t.clickViewRaw}
                  >
                    {msg.content}
                  </div>
                  <MessageActions
                    msg={msg}
                    isLast={isLast}
                    onCopy={() => handleCopy(msg.content)}
                    onDelete={() => handleDeleteFrom(msg.id)}
                    onEdit={() => handleEdit(msg)}
                    t={t}
                  />
                </div>
              </div>
            )
          }

          // assistant
          return (
            <div key={msg.id} className="space-y-3 group">
              <div className="flex justify-start">
                <div className="flex items-end gap-2">
                  <div
                    className="px-5 py-3 rounded-2xl rounded-tl-sm max-w-[85%] text-sm markdown-content cursor-pointer transition-all bg-muted/50 border text-foreground shadow-sm hover:bg-muted/70"
                    onClick={() => setInspectMsg(msg)}
                    title={t.clickViewRaw}
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
                    t={t}
                  />
                </div>
              </div>
              
              {messageImages[msg.id]?.length > 0 && (
                <MessageImageStrip
                  images={messageImages[msg.id]}
                  onPreview={setPreviewImage}
                />
              )}
              
              {imageLoadingMessages.has(msg.id) && (
                <div className="flex justify-start pl-1">
                  <div className="bg-muted/50 border rounded-xl px-4 py-3 max-w-[80%] flex items-center gap-3">
                    <span className="w-4 h-4 border-2 border-primary border-t-transparent rounded-full animate-spin" />
                    <span className="text-xs text-muted-foreground font-medium">{t.generatingImage}</span>
                  </div>
                </div>
              )}
              
              {msg.blocks && msg.blocks.length > 0 && (
                <BlockList
                  blocks={msg.blocks}
                  onAction={onAction}
                  locked={blocksLocked}
                  idPrefix={msg.id}
                  t={t}
                />
              )}
            </div>
          )
        })}

        {isStreaming && streamingContent && (
          <div className="flex justify-start">
            <div className="px-5 py-3 rounded-2xl rounded-tl-sm max-w-[85%] text-sm markdown-content bg-muted/30 border border-primary/20 text-foreground shadow-sm ring-1 ring-primary/10">
              <Markdown>{streamingContent}</Markdown>
              <span className="inline-block w-1.5 h-4 ml-1 bg-primary/70 animate-pulse align-middle" />
            </div>
          </div>
        )}

        {isStreaming && !streamingContent && (
          <div className="flex justify-start">
            <div className="px-5 py-4 rounded-2xl rounded-tl-sm bg-muted/30 border shadow-sm">
              <div className="flex gap-1.5">
                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
                <span className="w-2 h-2 bg-primary/50 rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
              </div>
            </div>
          </div>
        )}

        {pendingBlocks.length > 0 && (
          <BlockList
            blocks={pendingBlocks.map((b) => ({
              type: b.type,
              data: b.data,
              block_id: b.blockId,
            }))}
            onAction={onAction}
            idPrefix="pending"
            t={t}
          />
        )}
      </div>

      <StatusBar status={streamStatus} onRetry={onRetry} t={t} />

      <div ref={bottomRef} className="h-4" />

      {inspectMsg && <RawMessageViewer msg={inspectMsg} onClose={() => setInspectMsg(null)} t={t} />}
      {previewImage && <ImagePreviewModal image={previewImage} onClose={() => setPreviewImage(null)} closeLabel={t.close} altLabel={t.storyImageAlt} />}
    </div>
  )
}

function StatusBar({ status, onRetry, t }: { status: StreamStatus; onRetry?: () => void; t: Record<string, string> }) {
  if (status === 'idle') return null

  if (status === 'error') {
    return (
      <div className="flex justify-center my-4">
        <Alert variant="destructive" className="max-w-md py-2 px-4 inline-flex items-center w-auto shadow-sm">
          <AlertCircle className="h-4 w-4 mr-2" />
          <AlertDescription className="text-xs flex items-center gap-3 mt-0">
            {t.generationFailed}
            {onRetry && (
              <Button variant="outline" size="sm" className="h-6 px-2 text-xs border-destructive/30 hover:bg-destructive/10" onClick={onRetry}>
                {t.retry}
              </Button>
            )}
          </AlertDescription>
        </Alert>
      </div>
    )
  }

  if (status === 'done') {
    return (
      <div className="flex justify-center my-4">
        <Badge variant="outline" className="text-emerald-600 border-emerald-200 bg-emerald-50 dark:bg-emerald-950/30 dark:border-emerald-900 font-normal px-3 py-1 shadow-sm gap-1.5">
          <CheckCircle2 className="w-3.5 h-3.5" /> {t.generationDone}
        </Badge>
      </div>
    )
  }

  return null
}
