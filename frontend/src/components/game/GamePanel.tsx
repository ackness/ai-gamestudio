import { useEffect, useState } from 'react'
import type { Session } from '../../types'
import { useSessionStore } from '../../stores/sessionStore'
import { useGameStateStore } from '../../stores/gameStateStore'
import { useProjectStore } from '../../stores/projectStore'
import { useBlockSchemaStore } from '../../stores/blockSchemaStore'
import { useNotificationStore } from '../../stores/notificationStore'
import { ChatMessages } from './ChatMessages'
import { ChatInput } from './ChatInput'
import { SceneBar } from './SceneBar'
import { QuickActions } from './QuickActions'
import { ArchiveRestoreModal } from './ArchiveRestoreModal'
import { WelcomeScreen } from './WelcomeScreen'
import { DebugLogPanel } from './DebugLogPanel'
import { SessionSelector } from './SessionSelector'
import type { LlmInfo } from '../../services/api'
import { useUiStore } from '../../stores/uiStore'
import { useGameWebSocket } from '../../hooks/useGameWebSocket'
import { useGameActions } from '../../hooks/useGameActions'
import { useArchive } from '../../hooks/useArchive'

const gamePanelText: Record<string, Record<string, string>> = {
  zh: {
    noSession: '无活跃存档',
    selectSession: '选择或创建存档以开始',
    gameSession: '游戏存档',
    save: '存档',
    restore: '恢复',
    debug: '调试',
    saveTip: '手动生成一个存档版本',
    restoreTip: '恢复到任意历史版本',
    debugTip: '切换调试日志',
  },
  en: {
    noSession: 'No Active Session',
    selectSession: 'Select or create a session to begin',
    gameSession: 'Game Session',
    save: 'Save',
    restore: 'Restore',
    debug: 'Debug',
    saveTip: 'Manually create an archive version',
    restoreTip: 'Restore to any previous version',
    debugTip: 'Toggle debug log',
  },
}

interface Props {
  currentSession: Session | null
  onNewSession: () => void
  llmInfo?: LlmInfo | null
}

export function GamePanel({ currentSession, onNewSession, llmInfo }: Props) {
  const [showDebugLog, setShowDebugLog] = useState(false)
  const { currentProject } = useProjectStore()
  const language = useUiStore((s) => s.language)
  const gpt = gamePanelText[language] ?? gamePanelText.en
  const {
    sessions,
    messages,
    isStreaming,
    phase,
    currentScene,
    scenes,
    switchSession,
    deleteSession,
    setScenes,
    setCurrentScene,
  } = useSessionStore()
  const { setCharacters, setWorldState, setEvents } = useGameStateStore()

  // Fetch block schemas when project changes
  const { fetchSchemas, clear: clearSchemas } = useBlockSchemaStore()
  useEffect(() => {
    if (currentProject?.id) {
      fetchSchemas(currentProject.id)
    } else {
      clearSchemas()
    }
  }, [currentProject?.id, fetchSchemas, clearSchemas])

  // Hydrate notifications from messages
  useEffect(() => {
    if (!currentSession) {
      useNotificationStore.getState().clear()
      return
    }
    useNotificationStore.getState().hydrateFromMessages(currentSession.id, messages)
  }, [currentSession?.id, messages])

  // Defensive clear for init sessions
  useEffect(() => {
    if (!currentSession) return
    if (currentSession.phase !== 'init') return
    setScenes([])
    setCurrentScene(null)
    setEvents([])
    setCharacters([])
    setWorldState({})
  }, [currentSession?.id, currentSession?.phase, setScenes, setCurrentScene, setEvents, setCharacters, setWorldState])

  const { wsRef, wsStatus, initError, clearInitError } = useGameWebSocket(currentSession)
  const {
    handleSend,
    handleInitGame,
    handleRetry,
    handleForceTrigger,
    handleGenerateImage,
    handleSceneSwitch,
  } = useGameActions(currentSession, wsRef, clearInitError)
  const {
    archiveVersions,
    archiveBusy,
    showRestoreModal,
    setShowRestoreModal,
    handleArchiveNow,
    handleRestoreArchive,
    handleRestoreVersion,
  } = useArchive(currentSession)

  const effectiveModel = llmInfo?.model || ''
  const effectiveProvider = llmInfo?.provider || 'openai'
  const effectiveModelName = llmInfo?.model_name || ''
  const modelBadge = effectiveModel ? (
    <span className="text-xs text-slate-500 font-mono truncate max-w-[200px]" title={effectiveModel}>
      {effectiveProvider}/{effectiveModelName}
    </span>
  ) : null

  if (!currentSession) {
    return (
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
          <div className="flex items-center gap-3 min-w-0">
            <span className="text-sm font-medium text-slate-300 shrink-0">{gpt.noSession}</span>
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
          {gpt.selectSession}
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2 bg-slate-900 border-b border-slate-700">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-sm font-medium text-slate-300 shrink-0">{gpt.gameSession}</span>
          {modelBadge}
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleArchiveNow}
            disabled={archiveBusy || !currentSession}
            className="text-xs px-2 py-1 rounded transition-colors bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-300"
            title={gpt.saveTip}
          >
            {gpt.save}
          </button>
          <button
            onClick={handleRestoreArchive}
            disabled={archiveBusy || !currentSession}
            className="text-xs px-2 py-1 rounded transition-colors bg-slate-700 hover:bg-slate-600 disabled:opacity-50 disabled:cursor-not-allowed text-slate-300"
            title={gpt.restoreTip}
          >
            {gpt.restore}
          </button>
          <button
            onClick={() => setShowDebugLog((v) => !v)}
            className={`text-xs px-2 py-1 rounded transition-colors ${
              showDebugLog
                ? 'bg-amber-700 text-amber-100'
                : 'bg-slate-700 hover:bg-slate-600 text-slate-400'
            }`}
            title={gpt.debugTip}
          >
            {gpt.debug}
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
            <SceneBar currentScene={currentScene} scenes={scenes} onSceneSwitch={handleSceneSwitch} />
          )}
          <ChatMessages onAction={handleSend} onRetry={handleRetry} onGenerateImage={handleGenerateImage} />
          <QuickActions onTrigger={handleForceTrigger} disabled={isStreaming} />
          <ChatInput onSend={handleSend} disabled={isStreaming} />
        </>
      )}

      {showDebugLog && currentSession && (
        <DebugLogPanel sessionId={currentSession.id} onClose={() => setShowDebugLog(false)} />
      )}

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
