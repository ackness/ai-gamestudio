import { useEffect, useRef, useState } from 'react'
import type { Session, Character, GameEvent, StoryImageData, Scene } from '../types'
import { useSessionStore } from '../stores/sessionStore'
import { useGameStateStore } from '../stores/gameStateStore'
import { useProjectStore } from '../stores/projectStore'
import { useBlockInteractionStore } from '../stores/blockInteractionStore'
import { useNotificationStore } from '../stores/notificationStore'
import { useTokenStore } from '../stores/tokenStore'
import { GameWebSocket } from '../services/websocket'
import { StorageFactory } from '../services/settingsStorage'
import { useUiStore } from '../stores/uiStore'
import * as api from '../services/api'
import * as gameStorage from '../services/gameStorage'
import {
  buildBrowserImageOverrides,
  buildBrowserLlmOverrides,
} from '../utils/browserLlmConfig'

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function isGameEvent(value: unknown): value is GameEvent {
  if (!isRecord(value)) return false
  return (
    typeof value.id === 'string' &&
    typeof value.session_id === 'string' &&
    typeof value.event_type === 'string' &&
    typeof value.name === 'string' &&
    typeof value.description === 'string' &&
    typeof value.status === 'string' &&
    typeof value.source === 'string' &&
    typeof value.visibility === 'string'
  )
}

export function useGameWebSocket(currentSession: Session | null) {
  const wsRef = useRef<GameWebSocket | null>(null)
  const [wsStatus, setWsStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>('connected')
  const [initError, setInitError] = useState<string | null>(null)

  const {
    addMessage,
    setStreaming,
    setStreamStatus,
    appendStreamContent,
    clearStreamContent,
    addPendingBlock,
    setPhase,
    setPluginProcessing,
    setPluginProgress,
    setLastPluginSummary,
    setCurrentScene,
    setScenes,
    flushPendingBlocksForTurn,
    setMessageImage,
    setImageLoading,
    hydrateMessageImages,
    updateMessageBlocks,
  } = useSessionStore()
  const { setCharacters, mergeCharacters, setWorldState, addEvent, setEvents } = useGameStateStore()

  useEffect(() => {
    if (!currentSession) return
    useBlockInteractionStore.getState().clear()
    useNotificationStore.getState().resetForSession(currentSession.id)

    setCharacters([])
    setEvents([])
    setWorldState({})

    const ws = new GameWebSocket()
    ws.setLlmOverrideResolver(() => {
      const projectId = useProjectStore.getState().currentProject?.id ?? null
      return buildBrowserLlmOverrides(projectId)
    })
    ws.setImageOverrideResolver(() => {
      const projectId = useProjectStore.getState().currentProject?.id ?? null
      return buildBrowserImageOverrides(projectId)
    })
    wsRef.current = ws
    setWsStatus('connected')

    ws.onConnected = () => {
      setWsStatus('connected')
      // Re-probe backend persistence in case it started after the frontend
      StorageFactory.redetectIfNeeded().then((persistent) => {
        if (persistent) useUiStore.getState().checkStoragePersistence()
      }).catch(() => {})
    }
    ws.onReconnecting = () => setWsStatus('reconnecting')
    ws.onDisconnected = () => {
      setWsStatus('disconnected')
      setStreaming(false)
      setStreamStatus('error')
      clearStreamContent()
    }

    ws.onChunk = (content) => {
      setStreamStatus('streaming')
      appendStreamContent(content)
    }

    ws.onDone = (fullContent, turnId, hasBlocks, messageId, rawContent) => {
      setStreaming(false)
      setStreamStatus('done')
      if (fullContent || hasBlocks) {
        addMessage({
          id: messageId || crypto.randomUUID(),
          session_id: currentSession.id,
          role: 'assistant',
          content: fullContent || '（结构化响应）',
          raw_content: rawContent || undefined,
          turn_id: turnId || undefined,
          message_type: 'narration',
          created_at: new Date().toISOString(),
        })
      }
      clearStreamContent()
      setTimeout(() => setStreamStatus('idle'), 3000)
    }

    ws.onStateUpdate = (state) => {
      const characters = state?.characters
      if (Array.isArray(characters)) mergeCharacters(characters as Character[])
      const world = state?.world
      if (isRecord(world)) setWorldState(world)
    }

    ws.onPluginSummary = (data) => {
      setLastPluginSummary(data)
    }

    ws.onPluginProgress = (data) => {
      setPluginProgress(data)
    }

    ws.onPhaseChange = (newPhase) => {
      // Transient processing phases — don't override game phase
      if (newPhase === 'plugins') {
        setPluginProcessing(true)
        setLastPluginSummary(null)
        return
      }
      if (newPhase === 'complete') {
        setPluginProcessing(false)
        return
      }

      setPhase(newPhase)
      if ((newPhase === 'playing' || newPhase === 'character_creation') && currentSession) {
        gameStorage.fetchScenes(currentSession.id).then(setScenes).catch(() => {})
        gameStorage.fetchEvents(currentSession.id).then(setEvents).catch(() => {})
        gameStorage.fetchCharacters(currentSession.id).then(setCharacters).catch(() => {})
        api.getSessionState(currentSession.id).then((state) => setWorldState(state.world || {})).catch(() => {})
      } else if (newPhase === 'init') {
        setScenes([])
        setCurrentScene(null)
        setEvents([])
        setCharacters([])
        setWorldState({})
      }
    }

    ws.onSceneUpdate = (data) => {
      const sceneId = typeof data.scene_id === 'string' ? data.scene_id : ''
      const sceneName = typeof data.name === 'string' ? data.name : ''
      if (!sceneId || !sceneName) return

      const description = typeof data.description === 'string' ? data.description : undefined
      const npcs = Array.isArray(data.npcs) ? data.npcs : undefined
      const scene: Scene = {
        id: sceneId,
        session_id: currentSession.id,
        name: sceneName,
        description,
        is_current: true,
        metadata: npcs ? { npcs } : undefined,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }

      setCurrentScene(scene)
      const existing = useSessionStore.getState().scenes
      const updated = existing.map((s) => (s.id === scene.id ? scene : { ...s, is_current: false }))
      const found = existing.find((s) => s.id === scene.id)
      if (found) {
        setScenes(updated)
      } else {
        setScenes([...updated.map((s) => ({ ...s, is_current: false })), scene])
      }
    }

    ws.onNotification = (data, turnId, blockId) => {
      useNotificationStore.getState().addLiveNotification(
        currentSession.id,
        {
          level: typeof data.level === 'string' ? data.level : undefined,
          title: typeof data.title === 'string' ? data.title : undefined,
          content: typeof data.content === 'string' ? data.content : undefined,
        },
        { id: blockId || undefined, turnId: turnId || undefined },
      )
    }

    ws.onBlock = (type, data, turnId, blockId) => {
      if (type === 'state_update') return
      if (type === 'scene_update') return
      if (type === 'character_confirmed') return
      if (type === 'event') {
        if (isGameEvent(data)) addEvent(data)
        return
      }
      const enrichedData =
        data && typeof data === 'object' && !Array.isArray(data)
          ? { ...(data as Record<string, unknown>), _block_type: type }
          : data
      const resolvedBlockId = blockId || `${turnId || 'turnless'}:${crypto.randomUUID()}`

      // Check if this block updates an existing one (e.g. async story_image completion)
      if (blockId) {
        const state = useSessionStore.getState()
        const existsInMessages = state.messages.some(
          (m) => m.blocks?.some((b) => b.block_id === blockId),
        )
        const existsInPending = state.pendingBlocks.some((b) => b.blockId === blockId)
        if (existsInMessages || existsInPending) {
          state.updateBlockData(blockId, enrichedData)
          return
        }
      }

      addPendingBlock({ type, data: enrichedData, turnId: turnId || undefined, blockId: resolvedBlockId })
    }

    ws.onMessageBlocksUpdated = (messageId, blocks) => {
      if (messageId && blocks) updateMessageBlocks(messageId, blocks)
    }

    ws.onTurnEnd = (turnId) => {
      if (!turnId) return
      flushPendingBlocksForTurn(turnId)
    }

    ws.onMessageImage = (messageId, imageData) => {
      setImageLoading(messageId, false)
      if (imageData && (imageData as Record<string, unknown>).status !== 'error') {
        setMessageImage(messageId, imageData as StoryImageData)
      }
    }

    ws.onMessageImageLoading = (messageId) => setImageLoading(messageId, true)

    ws.onTokenUsage = (data) => {
      useTokenStore.getState().updateUsage({
        promptTokens: Number(data.prompt_tokens || 0),
        completionTokens: Number(data.completion_tokens || 0),
        totalTokens: Number(data.total_tokens || 0),
        turnCost: Number(data.turn_cost || 0),
        totalCost: Number(data.total_cost || 0),
        totalPromptTokens: Number(data.total_prompt_tokens || 0),
        totalCompletionTokens: Number(data.total_completion_tokens || 0),
        contextUsage: Number(data.context_usage || 0),
        maxInputTokens: Number(data.max_input_tokens || 0),
        model: String(data.model || ''),
      })
    }

    ws.onError = (error) => {
      setStreaming(false)
      setStreamStatus('error')
      clearStreamContent()
      if (useSessionStore.getState().phase === 'init') {
        setInitError(error)
      }
      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'system',
        content: `Error: ${error}`,
        message_type: 'system_event',
        created_at: new Date().toISOString(),
      })
    }

    const connectTimeout = setTimeout(() => ws.connect(currentSession.id), 100)

    gameStorage.fetchCharacters(currentSession.id).then(setCharacters).catch(() => {})
    api.getSessionState(currentSession.id).then((state) => {
      setWorldState(state.world || {})
      // Restore cumulative token usage from backend
      const tu = state.token_usage
      if (tu && typeof tu === 'object' && (tu.total_prompt_tokens || tu.total_completion_tokens)) {
        useTokenStore.getState().updateUsage({
          promptTokens: 0,
          completionTokens: 0,
          totalTokens: 0,
          turnCost: 0,
          totalCost: Number(tu.total_cost || 0),
          totalPromptTokens: Number(tu.total_prompt_tokens || 0),
          totalCompletionTokens: Number(tu.total_completion_tokens || 0),
          contextUsage: 0,
          maxInputTokens: 0,
          model: '',
        })
      }
    }).catch(() => {})
    hydrateMessageImages(currentSession.id)

    if (currentSession.phase === 'playing' || currentSession.phase === 'character_creation') {
      gameStorage.fetchScenes(currentSession.id).then((loaded) => {
        setScenes(loaded)
        const current = loaded.find((s) => s.is_current)
        if (current) setCurrentScene(current)
      }).catch(() => {})
      gameStorage.fetchEvents(currentSession.id).then(setEvents).catch(() => {})
    }

    if (currentSession.phase) setPhase(currentSession.phase)

    return () => {
      clearTimeout(connectTimeout)
      ws.disconnect()
      wsRef.current = null
    }
  }, [currentSession?.id, flushPendingBlocksForTurn]) // eslint-disable-line react-hooks/exhaustive-deps

  const clearInitError = () => setInitError(null)

  return { wsRef, wsStatus, initError, clearInitError }
}
