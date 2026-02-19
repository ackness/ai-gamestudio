import { useEffect, useState, useRef, useCallback } from 'react'
import { useParams } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUiStore } from '../stores/uiStore'
import { MarkdownEditor } from '../components/editor/MarkdownEditor'
import { InitPromptEditor } from '../components/editor/InitPromptEditor'
import { ModelSettings } from '../components/editor/ModelSettings'
import { GamePanel } from '../components/game/GamePanel'
import { SidePanel } from '../components/status/SidePanel'
import { decideSessionBootstrap } from '../utils/sessionBootstrap'
import type { LlmInfo } from '../services/api'

const SUPPORTED_LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
]

const editorUiText: Record<string, Record<string, string>> = {
  zh: { worldDoc: '世界文档', initPrompt: '初始提示', status: '状态', loading: '加载项目中...' },
  en: { worldDoc: 'World Doc', initPrompt: 'Init Prompt', status: 'Status', loading: 'Loading project...' },
}

type LeftTab = 'world' | 'init-prompt' | 'model'

export function ProjectEditorPage() {
  const { id } = useParams<{ id: string }>()
  const { currentProject, selectProject, loading } = useProjectStore()
  const { sessions, fetchSessions, createSession, currentSession, setCurrentSession, fetchMessages } = useSessionStore()
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const [leftTab, setLeftTab] = useState<LeftTab>('world')
  const [sessionsFetched, setSessionsFetched] = useState(false)
  const [llmInfo, setLlmInfo] = useState<LlmInfo | null>(null)
  // Use ref to track if we've checked sessions (persists across StrictMode double-render)
  const sessionsCheckedRef = useRef(false)
  const [autoCreating, setAutoCreating] = useState(false)

  useEffect(() => {
    sessionsCheckedRef.current = false
    setSessionsFetched(false)
    if (id) {
      selectProject(id)
      fetchSessions(id).finally(() => setSessionsFetched(true))
    }
  }, [id, selectProject, fetchSessions])

  useEffect(() => {
    const decision = decideSessionBootstrap({
      projectId: id,
      loading,
      autoCreating,
      sessionsFetched,
      checked: sessionsCheckedRef.current,
      sessions,
      currentSession,
    })
    if (!decision.reuseSession && !decision.shouldCreate) return

    // Mark as checked immediately to prevent duplicate runs
    sessionsCheckedRef.current = true

    if (decision.reuseSession) {
      setCurrentSession(decision.reuseSession)
      return
    }

    if (decision.shouldCreate && id) {
      setAutoCreating(true)
      createSession(id).finally(() => setAutoCreating(false))
    }
  }, [id, loading, sessions, autoCreating, createSession, currentSession, setCurrentSession, sessionsFetched])

  // Auto-select active session on initial load (only if no session is selected yet)
  useEffect(() => {
    if (!id || !sessionsFetched || sessions.length === 0 || currentSession) return
    const active = sessions.find((s) => s.status === 'active')
    if (active) {
      setCurrentSession(active)
      fetchMessages(active.id)
    }
  }, [sessions, id, currentSession, setCurrentSession, fetchMessages, sessionsFetched])

  const { language, setLanguage } = useUiStore()
  const et = editorUiText[language] ?? editorUiText.en
  const handleLlmInfoChange = useCallback((info: LlmInfo | null) => setLlmInfo(info), [])

  const handleNewSession = async () => {
    if (!id) return
    await createSession(id)
  }

  if (loading || !currentProject) {
    return <div className="flex-1 flex items-center justify-center text-slate-400">{et.loading}</div>
  }

  return (
    <div className="flex-1 flex overflow-hidden">
      {/* Left Panel - World Doc / Init Prompt Editor */}
      <div
        className={`border-r border-slate-700 flex flex-col transition-all ${
          leftCollapsed ? 'w-10' : 'w-[30%] min-w-[280px]'
        }`}
      >
        <div className="flex items-center justify-between px-3 py-2 bg-slate-900 border-b border-slate-700">
          {!leftCollapsed && (
            <div className="flex items-center gap-1">
              <button
                onClick={() => setLeftTab('world')}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  leftTab === 'world'
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {et.worldDoc}
              </button>
              <button
                onClick={() => setLeftTab('init-prompt')}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  leftTab === 'init-prompt'
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {et.initPrompt}
              </button>
              <button
                onClick={() => setLeftTab('model')}
                className={`text-xs px-2 py-1 rounded transition-colors ${
                  leftTab === 'model'
                    ? 'bg-slate-700 text-slate-200'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {language === 'zh' ? '模型' : 'Model'}
                {llmInfo && (
                  <span className="ml-1 font-mono text-[10px] text-slate-500">
                    {llmInfo.model_name}
                  </span>
                )}
              </button>
            </div>
          )}
          <button
            onClick={() => setLeftCollapsed(!leftCollapsed)}
            className="text-slate-400 hover:text-slate-200 text-sm px-1"
          >
            {leftCollapsed ? '>' : '<'}
          </button>
        </div>
        {!leftCollapsed && leftTab === 'world' && <MarkdownEditor />}
        {!leftCollapsed && leftTab === 'init-prompt' && <InitPromptEditor />}
        {!leftCollapsed && leftTab === 'model' && (
          <ModelSettings onLlmInfoChange={handleLlmInfoChange} />
        )}
      </div>

      {/* Center Panel - Game Chat */}
      <div className="flex-1 flex flex-col min-w-[300px] overflow-hidden">
        <GamePanel
          currentSession={currentSession}
          onNewSession={handleNewSession}
          llmInfo={llmInfo}
        />
      </div>

      {/* Right Panel - Status & Plugins */}
      <div
        className={`border-l border-slate-700 flex flex-col transition-all ${
          rightCollapsed ? 'w-10' : 'w-[30%] min-w-[300px] max-w-[460px]'
        }`}
      >
        <div className="flex items-center justify-between px-3 py-2 bg-slate-900 border-b border-slate-700">
          <button
            onClick={() => setRightCollapsed(!rightCollapsed)}
            className="text-slate-400 hover:text-slate-200 text-sm px-1"
          >
            {rightCollapsed ? '<' : '>'}
          </button>
          {!rightCollapsed && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-slate-300">{et.status}</span>
              <div className="flex items-center gap-1">
                {SUPPORTED_LANGS.map((lang) => (
                  <button
                    key={lang.code}
                    onClick={() => setLanguage(lang.code)}
                    className={`text-xs px-2 py-1 rounded font-medium transition-colors ${
                      language === lang.code
                        ? 'bg-slate-600 text-slate-100'
                        : 'text-slate-500 hover:text-slate-300 hover:bg-slate-700/50'
                    }`}
                  >
                    {lang.label}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
        {!rightCollapsed && <SidePanel />}
      </div>
    </div>
  )
}
