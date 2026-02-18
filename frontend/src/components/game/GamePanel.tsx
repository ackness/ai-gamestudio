import { useEffect, useRef, useCallback, useState } from 'react'
import type { ArchiveVersion, Session, Character, GameEvent, StoryImageData } from '../../types'
import { useSessionStore } from '../../stores/sessionStore'
import { useGameStateStore } from '../../stores/gameStateStore'
import { useProjectStore } from '../../stores/projectStore'
import { useBlockSchemaStore } from '../../stores/blockSchemaStore'
import { useBlockInteractionStore } from '../../stores/blockInteractionStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { GameWebSocket } from '../../services/websocket'
import { ChatMessages } from './ChatMessages'
import { ChatInput } from './ChatInput'
import { SceneBar } from './SceneBar'
import { QuickActions } from './QuickActions'
import { ArchiveRestoreModal } from './ArchiveRestoreModal'
import { WelcomeScreen } from './WelcomeScreen'
import { ModelConfigPanel } from './ModelConfigPanel'
import { DebugLogPanel } from './DebugLogPanel'
import { SessionSelector } from './SessionSelector'
import * as api from '../../services/api'
import type { LlmInfo } from '../../services/api'
import {
  buildBrowserImageOverrides,
  buildBrowserLlmOverrides,
} from '../../utils/browserLlmConfig'

interface Props {
  currentSession: Session | null
  onNewSession: () => void
}

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

export function GamePanel({ currentSession, onNewSession }: Props) {
  const wsRef = useRef<GameWebSocket | null>(null)
  const lastActionRef = useRef<{ type: string; content?: string; data?: unknown } | null>(null)
  const [llmInfo, setLlmInfo] = useState<LlmInfo | null>(null)
  const [showModelConfig, setShowModelConfig] = useState(false)
  const [showDebugLog, setShowDebugLog] = useState(false)
  const [archiveVersions, setArchiveVersions] = useState<ArchiveVersion[]>([])
  const [archiveBusy, setArchiveBusy] = useState(false)
  const [showRestoreModal, setShowRestoreModal] = useState(false)
  const [initError, setInitError] = useState<string | null>(null)
  const [wsStatus, setWsStatus] = useState<'connected' | 'reconnecting' | 'disconnected'>('connected')
  const { currentProject } = useProjectStore()
  const {
    sessions,
    messages,
    addMessage,
    fetchMessages,
    setStreaming,
    setStreamStatus,
    appendStreamContent,
    clearStreamContent,
    addPendingBlock,
    isStreaming,
    phase,
    setPhase,
    currentScene,
    setCurrentScene,
    scenes,
    setScenes,
    flushPendingBlocksForTurn,
    clearPendingBlocks,
    switchSession,
    fetchSessions,
    deleteSession,
    setMessageImage,
    setImageLoading,
    hydrateMessageImages,
  } = useSessionStore()
  const { setCharacters, mergeCharacters, setWorldState, addEvent, setEvents } = useGameStateStore()

  const refreshLlmInfo = useCallback(() => {
    // Use currentProject.id directly from store to ensure fresh value
    const pid = useProjectStore.getState().currentProject?.id
    api.getLlmInfo(pid).then(setLlmInfo).catch(() => {})
  }, [])

  const refreshArchiveVersions = useCallback(() => {
    if (!currentSession) {
      setArchiveVersions([])
      return
    }
    api.getArchiveVersions(currentSession.id).then(setArchiveVersions).catch(() => setArchiveVersions([]))
  }, [currentSession])

  useEffect(() => {
    refreshLlmInfo()
  }, [refreshLlmInfo])

  useEffect(() => {
    refreshArchiveVersions()
  }, [refreshArchiveVersions])

  // Fetch block schemas when project changes
  const { fetchSchemas, clear: clearSchemas } = useBlockSchemaStore()
  useEffect(() => {
    if (currentProject?.id) {
      fetchSchemas(currentProject.id)
    } else {
      clearSchemas()
    }
  }, [currentProject?.id, fetchSchemas, clearSchemas])

  // Compute effective model: use API returned values directly
  const effectiveModel = llmInfo?.model || ''
  const effectiveProvider = llmInfo?.provider || 'openai'
  const effectiveModelName = llmInfo?.model_name || ''

  useEffect(() => {
    if (!currentSession) return
    useBlockInteractionStore.getState().clear()
    useNotificationStore.getState().resetForSession(currentSession.id)

    // Reset game state from previous session
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

    // Reset connection status for new session
    setWsStatus('connected')

    ws.onConnected = () => {
      setWsStatus('connected')
    }

    ws.onReconnecting = () => {
      setWsStatus('reconnecting')
    }

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
      // Auto-clear "done" status after a short delay
      setTimeout(() => {
        setStreamStatus('idle')
      }, 3000)
    }

    ws.onStateUpdate = (state) => {
      const characters = state?.characters
      if (Array.isArray(characters)) {
        mergeCharacters(characters as Character[])
      }
      const world = state?.world
      if (isRecord(world)) {
        setWorldState(world)
      }
    }

    ws.onPhaseChange = (newPhase) => {
      setPhase(newPhase)
      if ((newPhase === 'playing' || newPhase === 'character_creation') && currentSession) {
        api.getScenes(currentSession.id).then(setScenes).catch(() => {})
        api.getEvents(currentSession.id).then(setEvents).catch(() => {})
        api.getCharacters(currentSession.id).then(setCharacters).catch(() => {})
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
      // Backend sends {action, name, description?, scene_id, npcs?}
      const sceneId = (data as any)?.scene_id
      const sceneName = (data as any)?.name
      if (!sceneId || !sceneName) return

      const scene: import('../../types').Scene = {
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
      // Also update in scenes list
      const existing = useSessionStore.getState().scenes
      // Mark all existing scenes as not current
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
        {
          id: blockId || undefined,
          turnId: turnId || undefined,
        },
      )
    }

    ws.onBlock = (type, data, turnId, blockId) => {
      if (type === 'state_update') return
      if (type === 'scene_update') return // handled by onSceneUpdate
      if (type === 'event') {
        if (isGameEvent(data)) {
          addEvent(data)
        }
        return
      }
      const enrichedData =
        data && typeof data === 'object' && !Array.isArray(data)
          ? { ...(data as Record<string, unknown>), _block_type: type }
          : data
      const resolvedBlockId = blockId || `${turnId || 'turnless'}:${crypto.randomUUID()}`
      addPendingBlock({
        type,
        data: enrichedData,
        turnId: turnId || undefined,
        blockId: resolvedBlockId,
      })
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

    ws.onMessageImageLoading = (messageId) => {
      setImageLoading(messageId, true)
    }

    ws.onError = (error) => {
      setStreaming(false)
      setStreamStatus('error')
      clearStreamContent()

      // Track error for init phase (where ChatMessages isn't visible)
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

    // Delay connection to avoid React StrictMode double-render issues
    const connectTimeout = setTimeout(() => {
      ws.connect(currentSession.id)
    }, 100)

    // Load persisted game state for this session
    api.getCharacters(currentSession.id).then(setCharacters).catch(() => {})
    api.getSessionState(currentSession.id).then((state) => setWorldState(state.world || {})).catch(() => {})

    // Hydrate message images from API
    hydrateMessageImages(currentSession.id)

    // Load scenes and events if session is already in a progressed phase
    if (currentSession.phase === 'playing' || currentSession.phase === 'character_creation') {
      api.getScenes(currentSession.id).then((loaded) => {
        setScenes(loaded)
        const current = loaded.find((s) => s.is_current)
        if (current) setCurrentScene(current)
      }).catch(() => {})
      api.getEvents(currentSession.id).then(setEvents).catch(() => {})
    }

    // Set initial phase from session
    if (currentSession.phase) {
      setPhase(currentSession.phase)
    }

    return () => {
      clearTimeout(connectTimeout)
      ws.disconnect()
      wsRef.current = null
    }
  }, [currentSession?.id, flushPendingBlocksForTurn]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!currentSession) {
      useNotificationStore.getState().clear()
      return
    }
    useNotificationStore
      .getState()
      .hydrateFromMessages(currentSession.id, messages)
  }, [currentSession?.id, messages])

  useEffect(() => {
    if (!currentSession) return
    if (currentSession.phase !== 'init') return
    // Defensive clear: avoid stale runtime state when revisiting an init session.
    setScenes([])
    setCurrentScene(null)
    setEvents([])
    setCharacters([])
    setWorldState({})
  }, [
    currentSession?.id,
    currentSession?.phase,
    setScenes,
    setCurrentScene,
    setEvents,
    setCharacters,
    setWorldState,
  ])

  const handleSend = useCallback(
    (message: string) => {
      if (!currentSession || !wsRef.current) return

      // Prevent sending while a response is in progress (block renderers can bypass ChatInput's disabled state)
      if (useSessionStore.getState().isStreaming) return

      // Check if this is a structured action from a block renderer (e.g. form_submit, character_edit)
      try {
        const parsed = JSON.parse(message)
        if (parsed.type && typeof parsed.type === 'string' && parsed.type !== 'message') {
          // Structured action — send directly as a WebSocket command, don't show as user message
          lastActionRef.current = { type: 'structured', data: parsed }
          wsRef.current.send(parsed)
          setStreaming(true)
          setStreamStatus('waiting')
          clearStreamContent()
          return
        }
      } catch {
        // Not JSON — treat as regular chat message
      }

      // Pending blocks should already be attached by turn_id at turn_end.
      if (useSessionStore.getState().pendingBlocks.length > 0) {
        clearPendingBlocks()
      }

      lastActionRef.current = { type: 'message', content: message }

      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'user',
        content: message,
        message_type: 'chat',
        created_at: new Date().toISOString(),
      })

      setStreaming(true)
      setStreamStatus('waiting')
      clearStreamContent()
      wsRef.current.sendMessage(message)
    },
    [currentSession, addMessage, setStreaming, setStreamStatus, clearStreamContent, clearPendingBlocks],
  )

  const handleInitGame = useCallback(() => {
    if (!wsRef.current) return
    setInitError(null)
    lastActionRef.current = { type: 'init_game' }
    setStreaming(true)
    setStreamStatus('waiting')
    clearStreamContent()
    wsRef.current.sendInitGame()
  }, [setStreaming, setStreamStatus, clearStreamContent])

  const handleRetry = useCallback(() => {
    const last = lastActionRef.current
    if (!last || !wsRef.current) return

    // Remove the last assistant response before regenerating
    useSessionStore.getState().removeLastAssistantMessage()
    setStreamStatus('idle')

    if (last.type === 'init_game') {
      handleInitGame()
    } else if (last.type === 'message' && last.content) {
      setStreaming(true)
      setStreamStatus('waiting')
      clearStreamContent()
      wsRef.current.sendMessage(last.content)
    } else if (last.type === 'structured' && last.data) {
      setStreaming(true)
      setStreamStatus('waiting')
      clearStreamContent()
      wsRef.current.send(last.data as import('../../services/websocket').StructuredMessage)
    }
  }, [handleInitGame, setStreaming, setStreamStatus, clearStreamContent])

  const handleForceTrigger = useCallback(
    (blockType: string) => {
      if (!wsRef.current || isStreaming) return
      setStreaming(true)
      setStreamStatus('waiting')
      clearStreamContent()
      wsRef.current.sendForceTrigger(blockType)
    },
    [isStreaming, setStreaming, setStreamStatus, clearStreamContent],
  )

  const handleGenerateImage = useCallback(
    (messageId: string) => {
      if (!wsRef.current || isStreaming) return
      wsRef.current.sendGenerateMessageImage(messageId)
    },
    [isStreaming],
  )

  const handleSceneSwitch = useCallback(
    (sceneId: string) => {
      if (!wsRef.current) return
      wsRef.current.sendSceneSwitch(sceneId)
    },
    [],
  )

  const handleArchiveNow = useCallback(async () => {
    if (!currentSession || archiveBusy) return
    setArchiveBusy(true)
    try {
      const created = await api.summarizeArchive(currentSession.id, 'manual')
      await refreshArchiveVersions()
      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'system',
        content: `已生成存档版本 v${created.version}`,
        message_type: 'system_event',
        created_at: new Date().toISOString(),
      })
    } catch {
      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'system',
        content: '手动存档失败',
        message_type: 'system_event',
        created_at: new Date().toISOString(),
      })
    } finally {
      setArchiveBusy(false)
    }
  }, [currentSession, archiveBusy, refreshArchiveVersions, addMessage])

  const handleRestoreArchive = useCallback(async () => {
    if (!currentSession || archiveBusy) return

    let versions = archiveVersions
    if (versions.length === 0) {
      try {
        versions = await api.getArchiveVersions(currentSession.id)
        setArchiveVersions(versions)
      } catch {
        versions = []
      }
    }

    if (versions.length === 0) {
      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'system',
        content: '当前没有可恢复的存档版本',
        message_type: 'system_event',
        created_at: new Date().toISOString(),
      })
      return
    }

    setShowRestoreModal(true)
  }, [currentSession, archiveBusy, archiveVersions, addMessage])

  const handleRestoreVersion = useCallback(async (version: number, mode: 'hard' | 'fork') => {
    if (!currentSession) return
    setShowRestoreModal(false)
    setArchiveBusy(true)
    try {
      const restored = await api.restoreArchiveVersion(currentSession.id, version, mode)
      let targetSessionId = restored.session_id || currentSession.id

      if (restored.mode === 'fork' && restored.new_session_id && currentProject?.id) {
        await fetchSessions(currentProject.id)
        const forkSession = useSessionStore
          .getState()
          .sessions.find((s) => s.id === restored.new_session_id)
        if (forkSession) {
          await switchSession(forkSession)
          targetSessionId = forkSession.id
        } else {
          targetSessionId = restored.new_session_id
        }
      }

      await fetchMessages(targetSessionId)
      const [loadedScenes, loadedEvents, loadedVersions, loadedCharacters, loadedState] = await Promise.all([
        api.getScenes(targetSessionId),
        api.getEvents(targetSessionId),
        api.getArchiveVersions(targetSessionId),
        api.getCharacters(targetSessionId),
        api.getSessionState(targetSessionId),
      ])
      setScenes(loadedScenes)
      setCurrentScene(loadedScenes.find((s) => s.is_current) ?? null)
      setEvents(loadedEvents)
      setArchiveVersions(loadedVersions)
      setCharacters(loadedCharacters)
      setWorldState(loadedState.world || {})
      setPhase(restored.phase || 'playing')
    } catch {
      addMessage({
        id: crypto.randomUUID(),
        session_id: currentSession.id,
        role: 'system',
        content: `恢复存档 v${version} 失败`,
        message_type: 'system_event',
        created_at: new Date().toISOString(),
      })
    } finally {
      setArchiveBusy(false)
    }
  }, [
    currentSession,
    addMessage,
    fetchMessages,
    fetchSessions,
    setScenes,
    setCurrentScene,
    setEvents,
    setCharacters,
    setWorldState,
    setPhase,
    switchSession,
    currentProject?.id,
  ])

  // Phase-aware rendering
  const modelBadge = effectiveModel ? (
    <div className="relative">
      <button
        onClick={() => setShowModelConfig((v) => !v)}
        className="text-xs text-slate-500 hover:text-slate-300 font-mono truncate max-w-[200px] cursor-pointer transition-colors"
        title="Click to configure model"
      >
        {effectiveProvider}/{effectiveModelName}
      </button>
      {showModelConfig && (
        <ModelConfigPanel
          llmInfo={llmInfo}
          onClose={() => setShowModelConfig(false)}
          onSaved={() => {
            setShowModelConfig(false)
            refreshLlmInfo()
          }}
        />
      )}
    </div>
  ) : null

  if (!currentSession) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-sm font-medium text-slate-300 shrink-0">No Active Session</span>
            {modelBadge}
          </div>
          <SessionSelector
            sessions={sessions}
            currentSession={null}
            onSwitch={(s) => switchSession(s)}
            onNew={onNewSession}
            onDelete={(id) => deleteSession(id)}
          />
        </div>
        <div className="flex-1 flex items-center justify-center text-slate-500">
          Select or create a session to begin
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-slate-300 shrink-0">Game Session</span>
          {modelBadge}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleArchiveNow}
            disabled={archiveBusy || !currentSession}
            className="text-xs px-2 py-1 rounded transition-colors bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-300"
            title="手动生成一个存档版本"
          >
            Save
          </button>
          <button
            onClick={handleRestoreArchive}
            disabled={archiveBusy || !currentSession}
            className="text-xs px-2 py-1 rounded transition-colors bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-300"
            title="恢复到任意历史版本"
          >
            Restore
          </button>
          <button
            onClick={() => setShowDebugLog((v) => !v)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              showDebugLog
                ? 'bg-amber-700 text-amber-100'
                : 'bg-slate-700 hover:bg-slate-600 text-slate-400'
            }`}
            title="Toggle debug log"
          >
            Debug
          </button>
          <SessionSelector
            sessions={sessions}
            currentSession={currentSession}
            onSwitch={(s) => switchSession(s)}
            onNew={onNewSession}
            onDelete={(id) => deleteSession(id)}
          />
        </div>
      </div>

      {/* Connection status banner */}
      {wsStatus !== 'connected' && (
        <div className={`flex items-center gap-2 px-4 py-1.5 text-xs border-b ${
          wsStatus === 'reconnecting'
            ? 'bg-amber-900/30 border-amber-700/50 text-amber-300'
            : 'bg-red-900/30 border-red-700/50 text-red-300'
        }`}>
          {wsStatus === 'reconnecting' ? (
            <>
              <span className="w-2.5 h-2.5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin shrink-0" />
              <span>正在重连后端...</span>
            </>
          ) : (
            <>
              <span className="text-red-400 shrink-0">&#10007;</span>
              <span>连接已断开，请检查后端服务是否运行</span>
            </>
          )}
        </div>
      )}

      {phase === 'init' && <WelcomeScreen onStart={handleInitGame} loading={isStreaming} error={initError} />}

      {phase === 'ended' && (
        <>
          <ChatMessages onAction={handleSend} onRetry={handleRetry} onGenerateImage={handleGenerateImage} />
          <div className="px-4 py-3 bg-slate-900/80 border-t border-slate-700 text-center">
            <p className="text-slate-400 text-sm mb-2">游戏结束</p>
            <button
              onClick={onNewSession}
              className="text-xs px-4 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white rounded transition-colors"
            >
              开始新游戏
            </button>
          </div>
        </>
      )}

      {(phase === 'character_creation' || phase === 'playing') && (
        <>
          {currentScene && (
            <SceneBar
              currentScene={currentScene}
              scenes={scenes}
              onSceneSwitch={handleSceneSwitch}
            />
          )}
          <ChatMessages onAction={handleSend} onRetry={handleRetry} onGenerateImage={handleGenerateImage} />
          <QuickActions onTrigger={handleForceTrigger} disabled={isStreaming} />
          <ChatInput onSend={handleSend} disabled={isStreaming} />
        </>
      )}

      {/* Floating debug log window */}
      {showDebugLog && currentSession && (
        <DebugLogPanel
          sessionId={currentSession.id}
          onClose={() => setShowDebugLog(false)}
        />
      )}

      {/* Archive restore modal */}
      {showRestoreModal && (
        <ArchiveRestoreModal
          versions={archiveVersions}
          onSelect={handleRestoreVersion}
          onClose={() => setShowRestoreModal(false)}
        />
      )}
    </div>
  )
}
