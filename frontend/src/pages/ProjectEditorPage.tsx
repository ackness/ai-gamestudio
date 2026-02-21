import { useEffect, useState, useRef, useCallback } from 'react'
import type { PanelImperativeHandle } from 'react-resizable-panels'
import { useParams } from 'react-router-dom'
import { FileText, MessageSquare, Settings, BookOpen, PanelLeftClose, PanelLeftOpen, PanelRightClose, PanelRightOpen, Terminal } from 'lucide-react'
import { useProjectStore } from '../stores/projectStore'
import { useSessionStore } from '../stores/sessionStore'
import { useUiStore } from '../stores/uiStore'
import { MarkdownEditor } from '../components/editor/MarkdownEditor'
import { InitPromptEditor } from '../components/editor/InitPromptEditor'
import { ModelSettings } from '../components/editor/ModelSettings'
import { NovelPanel } from '../components/editor/NovelPanel'
import { GamePanel } from '../components/game/GamePanel'
import { SidePanel } from '../components/status/SidePanel'
import { decideSessionBootstrap } from '../utils/sessionBootstrap'
import type { LlmInfo } from '../services/api'
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Loader2 } from 'lucide-react'

const SUPPORTED_LANGS = [
  { code: 'en', label: 'EN' },
  { code: 'zh', label: '中文' },
]

const editorUiText: Record<string, Record<string, string>> = {
  zh: { worldDoc: '世界文档', initPrompt: '初始提示', model: '模型', novel: '小说', status: '状态', loading: '加载项目中...' },
  en: { worldDoc: 'World Doc', initPrompt: 'Init Prompt', model: 'Model', novel: 'Novel', status: 'Status', loading: 'Loading project...' },
}

export function ProjectEditorPage() {
  const { id } = useParams<{ id: string }>()
  const { currentProject, selectProject, loading } = useProjectStore()
  const { sessions, fetchSessions, createSession, currentSession, setCurrentSession, fetchMessages } = useSessionStore()
  
  // Panel states
  const [leftCollapsed, setLeftCollapsed] = useState(false)
  const [rightCollapsed, setRightCollapsed] = useState(false)
  const leftPanelRef = useRef<PanelImperativeHandle | null>(null)
  const rightPanelRef = useRef<PanelImperativeHandle | null>(null)
  
  const [sessionsFetched, setSessionsFetched] = useState(false)
  const [llmInfo, setLlmInfo] = useState<LlmInfo | null>(null)
  
  // Use ref to track if we've checked sessions
  const sessionsCheckedRef = useRef(false)
  const [autoCreating, setAutoCreating] = useState(false)

  const { language, setLanguage } = useUiStore()
  const et = editorUiText[language] ?? editorUiText.en

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

  // Auto-select active session
  useEffect(() => {
    if (!id || !sessionsFetched || sessions.length === 0 || currentSession) return
    const active = sessions.find((s) => s.status === 'active')
    if (active) {
      setCurrentSession(active)
      fetchMessages(active.id)
    }
  }, [sessions, id, currentSession, setCurrentSession, fetchMessages, sessionsFetched])

  const handleLlmInfoChange = useCallback((info: LlmInfo | null) => setLlmInfo(info), [])

  const handleNewSession = async () => {
    if (!id) return
    await createSession(id)
  }

  if (loading || !currentProject) {
    return (
      <div className="flex-1 flex flex-col items-center justify-center text-muted-foreground gap-4 bg-background">
        <Loader2 className="w-8 h-8 animate-spin text-primary" />
        <span className="text-sm font-medium">{et.loading}</span>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-hidden bg-background flex flex-col">
      <div className="h-12 border-b flex items-center justify-between px-4 shrink-0 bg-muted/20">
        <div className="flex items-center gap-2">
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8"
            onClick={() => {
              if (leftCollapsed) {
                leftPanelRef.current?.expand()
                setLeftCollapsed(false)
              } else {
                leftPanelRef.current?.collapse()
                setLeftCollapsed(true)
              }
            }}
            title={leftCollapsed ? "Expand editor" : "Collapse editor"}
          >
            {leftCollapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </Button>
          <div className="h-4 w-px bg-border mx-2" />
          <h2 className="text-sm font-semibold truncate max-w-[200px] md:max-w-md">
            {currentProject.name}
          </h2>
        </div>
        
        <div className="flex items-center gap-2">
          <div className="flex items-center bg-muted rounded-md p-1 border">
            {SUPPORTED_LANGS.map((lang) => (
              <button
                key={lang.code}
                onClick={() => setLanguage(lang.code)}
                className={`text-xs px-2.5 py-1 rounded-sm font-medium transition-all ${
                  language === lang.code
                    ? 'bg-background text-foreground shadow-sm'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
          <div className="h-4 w-px bg-border mx-2" />
          <Button 
            variant="ghost" 
            size="icon" 
            className="h-8 w-8"
            onClick={() => {
              if (rightCollapsed) {
                rightPanelRef.current?.expand()
                setRightCollapsed(false)
              } else {
                rightPanelRef.current?.collapse()
                setRightCollapsed(true)
              }
            }}
            title={rightCollapsed ? "Expand status" : "Collapse status"}
          >
            {rightCollapsed ? <PanelRightOpen className="h-4 w-4" /> : <PanelRightClose className="h-4 w-4" />}
          </Button>
        </div>
      </div>

      <ResizablePanelGroup direction="horizontal" style={{ flex: '1 1 0', minHeight: 0, height: 'auto' }}>
        {/* Left Panel - Editor */}
        <ResizablePanel
          id="editor"
          defaultSize="32%"
          minSize="22%"
          maxSize="50%"
          collapsible
          collapsedSize="0%"
          panelRef={leftPanelRef}
          onResize={(size) => setLeftCollapsed(size.asPercentage < 1)}
        >
          <div className="h-full flex flex-col overflow-hidden">
            <Tabs defaultValue="world" className="flex-1 flex flex-col min-h-0">
              <div className="px-4 py-2 border-b bg-muted/10 shrink-0">
                <TabsList className="w-full justify-start h-9 p-1">
                  <TabsTrigger value="world" className="text-xs flex-1"><FileText className="w-3 h-3 mr-1.5 hidden sm:inline" />{et.worldDoc}</TabsTrigger>
                  <TabsTrigger value="prompt" className="text-xs flex-1"><Terminal className="w-3 h-3 mr-1.5 hidden sm:inline" />{et.initPrompt}</TabsTrigger>
                  <TabsTrigger value="model" className="text-xs flex-1 relative">
                    <Settings className="w-3 h-3 mr-1.5 hidden sm:inline" />{et.model}
                    {llmInfo && <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-primary" title={llmInfo.model_name} />}
                  </TabsTrigger>
                  <TabsTrigger value="novel" className="text-xs flex-1"><BookOpen className="w-3 h-3 mr-1.5 hidden sm:inline" />{et.novel}</TabsTrigger>
                </TabsList>
              </div>
              <div className="flex-1 overflow-hidden relative">
                <TabsContent value="world" className="absolute inset-0 m-0 border-0 data-[state=inactive]:hidden"><MarkdownEditor /></TabsContent>
                <TabsContent value="prompt" className="absolute inset-0 m-0 border-0 data-[state=inactive]:hidden"><InitPromptEditor /></TabsContent>
                <TabsContent value="model" className="absolute inset-0 m-0 border-0 data-[state=inactive]:hidden overflow-y-auto">
                  <ModelSettings onLlmInfoChange={handleLlmInfoChange} />
                </TabsContent>
                <TabsContent value="novel" className="absolute inset-0 m-0 border-0 data-[state=inactive]:hidden"><NovelPanel /></TabsContent>
              </div>
            </Tabs>
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Center Panel - Game Chat */}
        <ResizablePanel
          id="game"
          defaultSize="40%"
          minSize="25%"
        >
          <div className="h-full flex flex-col overflow-hidden">
            <GamePanel
              currentSession={currentSession}
              onNewSession={handleNewSession}
              llmInfo={llmInfo}
            />
          </div>
        </ResizablePanel>

        <ResizableHandle withHandle />

        {/* Right Panel - Status */}
        <ResizablePanel
          id="status"
          defaultSize="28%"
          minSize="22%"
          maxSize="45%"
          collapsible
          collapsedSize="0%"
          panelRef={rightPanelRef}
          onResize={(size) => setRightCollapsed(size.asPercentage < 1)}
        >
          <div className="h-full flex flex-col overflow-hidden">
            <div className="h-12 border-b flex items-center px-4 shrink-0 bg-muted/20">
              <span className="text-sm font-semibold flex items-center text-muted-foreground">
                <MessageSquare className="w-4 h-4 mr-2" />
                {et.status}
              </span>
            </div>
            <SidePanel />
          </div>
        </ResizablePanel>
      </ResizablePanelGroup>
    </div>
  )
}
