type ChunkCallback = (content: string) => void
type DoneCallback = (fullContent: string, turnId: string, hasBlocks: boolean) => void
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

export interface StructuredMessage {
  type: string
  [key: string]: unknown
}

export class GameWebSocket {
  private ws: WebSocket | null = null
  private reconnectAttempts = 0
  private maxReconnectAttempts = 5
  private sessionId: string | null = null
  private shouldReconnect = true

  onChunk: ChunkCallback = () => {}
  onDone: DoneCallback = () => {}
  onStateUpdate: StateUpdateCallback = () => {}
  onBlock: BlockCallback = () => {}
  onError: ErrorCallback = () => {}
  onPhaseChange: PhaseChangeCallback = () => {}
  onSceneUpdate: SceneUpdateCallback = () => {}
  onNotification: NotificationCallback = () => {}
  onTurnEnd: TurnEndCallback = () => {}

  connect(sessionId: string) {
    this.sessionId = sessionId
    this.shouldReconnect = true
    this.reconnectAttempts = 0
    this.createConnection()
  }

  private createConnection() {
    if (!this.sessionId) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws/chat/${this.sessionId}`

    this.ws = new WebSocket(wsUrl)

    this.ws.onopen = () => {
      this.reconnectAttempts = 0
    }

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        switch (data.type) {
          case 'chunk':
            this.onChunk(data.content)
            break
          case 'done':
            this.onDone(data.content || '', data.turn_id || '', !!data.has_blocks)
            break
          case 'state_update':
            // Fire both the specific callback and the generic one
            this.onStateUpdate(data.data)
            this.onBlock('state_update', data.data, data.turn_id || '', data.block_id || '')
            break
          case 'phase_change':
            this.onPhaseChange(data.data?.phase ?? data.phase)
            break
          case 'scene_update':
            this.onSceneUpdate(data.data)
            this.onBlock('scene_update', data.data, data.turn_id || '', data.block_id || '')
            break
          case 'notification':
            this.onNotification(data.data, data.turn_id || '', data.block_id || '')
            this.onBlock('notification', data.data, data.turn_id || '', data.block_id || '')
            break
          case 'turn_end':
            this.onTurnEnd(data.turn_id || '')
            break
          case 'error':
            this.onError(data.content || data.message || 'Unknown error')
            break
          default:
            // Any other json:xxx block type (choices, dice_roll, etc.)
            if (data.type && data.data !== undefined) {
              this.onBlock(data.type, data.data, data.turn_id || '', data.block_id || '')
            }
            break
        }
      } catch {
        // Non-JSON message, treat as plain text chunk
        this.onChunk(event.data)
      }
    }

    this.ws.onclose = () => {
      if (this.shouldReconnect && this.reconnectAttempts < this.maxReconnectAttempts) {
        const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 30000)
        this.reconnectAttempts++
        setTimeout(() => this.createConnection(), delay)
      }
    }

    this.ws.onerror = () => {
      this.onError('WebSocket connection error')
    }
  }

  send(message: string | StructuredMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      if (typeof message === 'string') {
        this.ws.send(JSON.stringify({ type: 'message', content: message }))
      } else {
        this.ws.send(JSON.stringify(message))
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

  disconnect() {
    this.shouldReconnect = false
    this.ws?.close()
    this.ws = null
    this.sessionId = null
  }
}
