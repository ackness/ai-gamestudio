import { useEffect, useRef, useState } from 'react'
import type { Session, Character, GameEvent, StoryImageData, Scene } from '../types'
import { useSessionStore } from '../stores/sessionStore'
import { useGameStateStore } from '../stores/gameStateStore'
import { useProjectStore } from '../stores/projectStore'
import { useBlockInteractionStore } from '../stores/blockInteractionStore'
import { useNotificationStore } from '../stores/notificationStore'
import { GameWebSocket } from '../services/websocket'
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
    setCurrentScene,
    setScenes,
    flushPendingBlocksForTurn,
    setMessageImage,
    setImageLoading,
    hydrateMessageImages,
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

    ws.onConnected = () => setWsStatus('connected')
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

    ws.onDone = (fullContent, turnId, hasBlocks, messageId) => {
      setStreaming(false)
      setStreamStatus('done')
      if (fullContent || hasBlocks) {
        addMessage({
          id: messageId || crypto.randomUUID(),
          session_id: currentSession.id,
          role: 'assistant',
          content: fullContent || '（结构化响应）',
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

    ws.onPhaseChange = (newPhase) => {
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
      const sceneId = (data as any)?.scene_id
      const sceneName = (data as any)?.name
      if (!sceneId || !sceneName) return

      const scene: Scene = {
        id: sceneId,
        session_id: currentSession.id,
        name: sceneName,
        description: (data as any)?.description || undefined,
        is_current: true,
        metadata: (data as any)?.npcs ? { npcs: (data as any).npcs } : undefined,
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
      if (type === 'event') {
        if (isGameEvent(data)) addEvent(data)
        return
      }
      const enrichedData =
        data && typeof data === 'object' && !Array.isArray(data)
          ? { ...(data as Record<string, unknown>), _block_type: type }
          : data
      const resolvedBlockId = blockId || `${turnId || 'turnless'}:${crypto.randomUUID()}`
      addPendingBlock({ type, data: enrichedData, turnId: turnId || undefined, blockId: resolvedBlockId })
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
    api.getSessionState(currentSession.id).then((state) => setWorldState(state.world || {})).catch(() => {})
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
