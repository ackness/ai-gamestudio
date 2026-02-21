import type {
  ImageOverridePayload,
  LlmOverridePayload,
} from '../utils/browserLlmConfig'
import { StorageFactory } from './settingsStorage'
import { idbGetSession, idbGetProject } from './localDb'
import * as api from './api'

type ChunkCallback = (content: string) => void
type DoneCallback = (fullContent: string, turnId: string, hasBlocks: boolean, messageId: string, rawContent: string) => void
type StateUpdateCallback = (state: Record<string, unknown>) => void
type BlockCallback = (
  type: string,
  data: unknown,
  turnId: string,
  blockId: string,
) => void
type ErrorCallback = (error: string) => void
type PhaseChangeCallback = (phase: string) => void
type SceneUpdateCallback = (data: Record<string, unknown>) => void
type NotificationCallback = (
  data: Record<string, unknown>,
  turnId: string,
  blockId: string,
) => void
type TurnEndCallback = (turnId: string) => void
type MessageImageCallback = (messageId: string, data: Record<string, unknown>) => void
type MessageImageLoadingCallback = (messageId: string) => void
type ConnectedCallback = () => void
type ReconnectingCallback = (attempt: number, max: number) => void
type DisconnectedCallback = () => void

export interface StructuredMessage {
  type: string
  [key: string]: unknown
}

type TransportMode = 'websocket' | 'http'

function normalizeBaseUrl(value: string | undefined, fallback: string): string {
  const trimmed = (value || '').trim()
  const base = trimmed || fallback
  return base.endsWith('/') ? base.slice(0, -1) : base
}

function resolveTransportMode(): TransportMode {
  const raw = String(import.meta.env.VITE_CHAT_TRANSPORT || '').trim().toLowerCase()
  if (raw === 'http') return 'http'
  if (raw === 'websocket') return 'websocket'
  // No explicit setting: will be auto-detected on first connect() via StorageFactory.
  return 'websocket'
}

function getApiBaseUrl(): string {
  return normalizeBaseUrl(import.meta.env.VITE_API_BASE_URL, '/api')
}

function getWsBasePrefix(): string {
  const configured = normalizeBaseUrl(import.meta.env.VITE_WS_BASE_URL, '')
  if (configured) return configured
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

function getAccessKeyQueryParam(): string {
  const accessKey = String(import.meta.env.VITE_ACCESS_KEY || '').trim()
  if (!accessKey) return ''
  return `access_key=${encodeURIComponent(accessKey)}`
}

export class GameWebSocket {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private sessionId: string | null = null
  private shouldReconnect = true
  private transportMode: TransportMode = resolveTransportMode()
  private httpQueue: Promise<void> = Promise.resolve()
  private llmOverrideResolver: (() => LlmOverridePayload | undefined) | null = null
  private imageOverrideResolver: (() => ImageOverridePayload | undefined) | null = null

  onChunk: ChunkCallback = () => {}
  onDone: DoneCallback = () => {}
  onStateUpdate: StateUpdateCallback = () => {}
  onBlock: BlockCallback = () => {}
  onError: ErrorCallback = () => {}
  onPhaseChange: PhaseChangeCallback = () => {}
  onSceneUpdate: SceneUpdateCallback = () => {}
  onNotification: NotificationCallback = () => {}
  onTurnEnd: TurnEndCallback = () => {}
  onMessageImage: MessageImageCallback = () => {}
  onMessageImageLoading: MessageImageLoadingCallback = () => {}
  onConnected: ConnectedCallback = () => {}
  onReconnecting: ReconnectingCallback = () => {}
  onDisconnected: DisconnectedCallback = () => {}

  async connect(sessionId: string) {
    this.sessionId = sessionId
    this.shouldReconnect = true
    this.reconnectAttempts = 0

    // Auto-detect HTTP mode when VITE_CHAT_TRANSPORT is not explicitly set:
    // if backend storage is not persistent (Vercel + ephemeral SQLite), WebSockets
    // are not available — fall back to HTTP polling.
    if (this.transportMode === 'websocket' && !import.meta.env.VITE_CHAT_TRANSPORT) {
      const persistent = await StorageFactory.isStoragePersistent()
      if (!persistent) {
        this.transportMode = 'http'
      }
    }

    if (this.transportMode === 'http') {
      return
    }
    this.createConnection()
  }

  setLlmOverrideResolver(resolver: (() => LlmOverridePayload | undefined) | null) {
    this.llmOverrideResolver = resolver
  }

  setImageOverrideResolver(
    resolver: (() => ImageOverridePayload | undefined) | null,
  ) {
    this.imageOverrideResolver = resolver
  }

  private createConnection() {
    if (!this.sessionId) return

    const accessKeyParam = getAccessKeyQueryParam()
    const wsUrl = accessKeyParam
      ? `${getWsBasePrefix()}/chat/${this.sessionId}?${accessKeyParam}`
      : `${getWsBasePrefix()}/chat/${this.sessionId}`

    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
      this.onConnected()
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        this.handleServerEvent(data)
      } catch {
        // Non-JSON message, treat as plain text chunk
        this.onChunk(event.data)
      }
    }

    this.ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
        this.reconnectAttempts++
        this.onReconnecting(this.reconnectAttempts, this.maxReconnectAttempts)
        setTimeout(() => this.createConnection(), delay)
      } else if (this.shouldReconnect) {
        // All retries exhausted
        this.onDisconnected()
      }
      // If !shouldReconnect, intentional disconnect — do nothing
    }

    this.ws.onerror = () => {
      // Intentionally empty: connection failures are surfaced via onclose → onDisconnected
    }
  }

  send(message: string | StructuredMessage) {
    const payloadBase: StructuredMessage =
      typeof message === 'string'
        ? { type: 'message', content: message }
        : message
    const payload = this.attachOverrides(payloadBase)

    if (this.transportMode === 'http') {
      this.enqueueHttpCommand(payload)
      return
    }

    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload))
    }
  }

  private attachOverrides(payload: StructuredMessage): StructuredMessage {
    const nextPayload: StructuredMessage = { ...payload }
    if (!nextPayload.llm_overrides && this.llmOverrideResolver) {
      const llmOverrides = this.llmOverrideResolver()
      if (llmOverrides) nextPayload.llm_overrides = llmOverrides
    }
    if (!nextPayload.image_overrides && this.imageOverrideResolver) {
      const imageOverrides = this.imageOverrideResolver()
      if (imageOverrides) nextPayload.image_overrides = imageOverrides
    }
    return nextPayload
  }

  private async ensureSessionInBackend(): Promise<void> {
    if (!this.sessionId) return
    try {
      const row = await idbGetSession(this.sessionId)
      if (!row) return
      const projectId = String(row.project_id ?? '')
      if (!projectId) return

      // Re-sync project (upsert with original ID)
      const projectRow = await idbGetProject(projectId)
      if (projectRow) {
        try {
          await api.createProject({
            id: projectId,
            name: String(projectRow.name ?? projectId),
            description: projectRow.description ? String(projectRow.description) : undefined,
            world_doc: projectRow.world_doc ? String(projectRow.world_doc) : '',
          } as Parameters<typeof api.createProject>[0] & { id: string })
        } catch { /* best-effort */ }
      }

      // Re-sync session (upsert with original ID)
      await api.createSession(projectId, this.sessionId)
    } catch { /* best-effort */ }
  }

  private enqueueHttpCommand(payload: StructuredMessage) {
    if (!this.sessionId) {
      this.onError('Session not connected')
      return
    }
    this.httpQueue = this.httpQueue
      .then(() => this.ensureSessionInBackend())
      .then(() => this.sendHttpCommand(payload))
      .catch((err: unknown) => {
        const message = err instanceof Error ? err.message : String(err)
        this.onError(message || 'HTTP command failed')
      })
  }

  private async sendHttpCommand(payload: StructuredMessage) {
    if (!this.sessionId) return
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }
    const accessKey = String(import.meta.env.VITE_ACCESS_KEY || '').trim()
    if (accessKey) headers['X-Access-Key'] = accessKey

    const res = await fetch(`${getApiBaseUrl()}/chat/${this.sessionId}/command`, {
      method: 'POST',
      headers,
      body: JSON.stringify(payload),
    })

    if (!res.ok) {
      const detail = await res.text()
      throw new Error(`HTTP chat error ${res.status}: ${detail}`)
    }

    const data = await res.json()
    const events = Array.isArray(data?.events) ? data.events : []
    for (const event of events) {
      if (event && typeof event === 'object' && !Array.isArray(event)) {
        this.handleServerEvent(event as Record<string, unknown>)
      }
    }
  }

  private handleServerEvent(data: Record<string, unknown>) {
    const type = typeof data.type === 'string' ? data.type : ''
    switch (type) {
      case 'chunk':
        this.onChunk(String(data.content || ''))
        break
      case 'done':
        this.onDone(String(data.content || ''), String(data.turn_id || ''), !!data.has_blocks, String(data.message_id || ''), String(data.raw_content || data.content || ''))
        break
      case 'state_update':
        this.onStateUpdate((data.data as Record<string, unknown>) || {})
        this.onBlock('state_update', data.data, String(data.turn_id || ''), String(data.block_id || ''))
        break
      case 'phase_change': {
        const phaseData = data.data
        const phase =
          phaseData && typeof phaseData === 'object' && !Array.isArray(phaseData)
            ? String((phaseData as Record<string, unknown>).phase || '')
            : String(data.phase || '')
        this.onPhaseChange(phase)
        break
      }
      case 'scene_update':
        this.onSceneUpdate((data.data as Record<string, unknown>) || {})
        this.onBlock('scene_update', data.data, String(data.turn_id || ''), String(data.block_id || ''))
        break
      case 'notification':
        this.onNotification(
          (data.data as Record<string, unknown>) || {},
          String(data.turn_id || ''),
          String(data.block_id || ''),
        )
        this.onBlock('notification', data.data, String(data.turn_id || ''), String(data.block_id || ''))
        break
      case 'turn_end':
        this.onTurnEnd(String(data.turn_id || ''))
        break
      case 'message_image':
        this.onMessageImage(String(data.message_id || ''), (data.data as Record<string, unknown>) || {})
        break
      case 'message_image_loading':
        this.onMessageImageLoading(String(data.message_id || ''))
        break
      case 'error':
        this.onError(String(data.content || data.message || 'Unknown error'))
        break
      default:
        if (type && data.data !== undefined) {
          this.onBlock(type, data.data, String(data.turn_id || ''), String(data.block_id || ''))
        }
    }
  }

  sendMessage(content: string) {
    this.send({ type: 'message', content })
  }

  sendInitGame(preset?: string) {
    this.send({ type: 'init_game', ...(preset ? { preset } : {}) })
  }

  sendFormSubmit(formId: string, values: Record<string, unknown>) {
    this.send({ type: 'form_submit', form_id: formId, values })
  }

  sendCharacterEdit(characterId: string, changes: Record<string, unknown>) {
    this.send({ type: 'character_edit', character_id: characterId, changes })
  }

  sendSceneSwitch(sceneId: string) {
    this.send({ type: 'scene_switch', scene_id: sceneId })
  }

  sendConfirm(action: string, data?: Record<string, unknown>) {
    this.send({ type: 'confirm', action, ...(data ? { data } : {}) })
  }

  sendBlockResponse(blockType: string, blockId: string, data: Record<string, unknown>) {
    this.send({ type: 'block_response', block_type: blockType, block_id: blockId, data })
  }

  sendForceTrigger(blockType: string) {
    this.send({ type: 'force_trigger', block_type: blockType })
  }

  sendGenerateMessageImage(messageId: string) {
    this.send({ type: 'generate_message_image', message_id: messageId })
  }

  disconnect() {
    this.shouldReconnect = false
    this.ws?.close()
    this.ws = null
    this.httpQueue = Promise.resolve()
    this.llmOverrideResolver = null
    this.imageOverrideResolver = null
    this.sessionId = null
  }
}
