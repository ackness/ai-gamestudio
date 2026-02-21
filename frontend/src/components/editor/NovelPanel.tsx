import { useState, useRef, useCallback } from 'react'
import { useSessionStore } from '../../stores/sessionStore'
import { useUiStore } from '../../stores/uiStore'
import { generateNovelStream, type NovelEvent } from '../../services/api'

interface ChapterData {
  title: string
  summary: string
  content: string
}

const uiText: Record<string, Record<string, string>> = {
  zh: {
    title: '小说生成',
    style: '风格',
    chapters: '章节数',
    generate: '生成小说',
    generating: '生成中...',
    download: '下载 Markdown',
    noSession: '请先开始一个游戏会话',
    noMessages: '会话中还没有对话记录',
    outline: '大纲生成完成',
    selectChapter: '点击左侧章节预览内容',
    stop: '停止',
  },
  en: {
    title: 'Novel',
    style: 'Style',
    chapters: 'Chapters',
    generate: 'Generate',
    generating: 'Generating...',
    download: 'Download .md',
    noSession: 'Start a game session first',
    noMessages: 'No messages in session yet',
    outline: 'Outline ready',
    selectChapter: 'Click a chapter to preview',
    stop: 'Stop',
  },
}

const STYLES = ['轻小说', '严肃文学', '武侠', '科幻', '都市言情', '奇幻冒险']

export function NovelPanel() {
  const { currentSession } = useSessionStore()
  const { language } = useUiStore()
  const t = uiText[language] ?? uiText.en

  const [style, setStyle] = useState(STYLES[0])
  const [chapterCount, setChapterCount] = useState(5)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [chapters, setChapters] = useState<ChapterData[]>([])
  const [activeIdx, setActiveIdx] = useState(0)
  const [streamingIdx, setStreamingIdx] = useState(-1)
  const abortRef = useRef<AbortController | null>(null)
  // Use ref to accumulate streaming content to avoid stale closure
  const chaptersRef = useRef<ChapterData[]>([])

  const handleGenerate = useCallback(async () => {
    if (!currentSession) return
    setLoading(true)
    setError('')
    setChapters([])
    chaptersRef.current = []
    setActiveIdx(0)
    setStreamingIdx(-1)

    const ctrl = new AbortController()
    abortRef.current = ctrl

    try {
      await generateNovelStream(
        currentSession.id,
        { style, chapter_count: chapterCount, language },
        (event: NovelEvent) => {
          switch (event.type) {
            case 'outline': {
              const initial = event.chapters.map((ch) => ({
                title: ch.title,
                summary: ch.summary,
                content: '',
              }))
              chaptersRef.current = initial
              setChapters([...initial])
              break
            }
            case 'chapter_chunk': {
              const chs = chaptersRef.current
              if (chs[event.index]) {
                chs[event.index].content += event.text
                setChapters([...chs])
                setStreamingIdx(event.index)
                setActiveIdx(event.index)
              }
              break
            }
            case 'chapter': {
              const chs = chaptersRef.current
              if (chs[event.index]) {
                chs[event.index].content = event.content
                setChapters([...chs])
              }
              setStreamingIdx(-1)
              break
            }
            case 'error':
              setError(event.message)
              break
            case 'done':
              setStreamingIdx(-1)
              break
          }
        },
        ctrl.signal,
      )
    } catch (e: unknown) {
      if ((e as Error).name !== 'AbortError') {
        setError(e instanceof Error ? e.message : 'Generation failed')
      }
    } finally {
      setLoading(false)
      abortRef.current = null
    }
  }, [currentSession, style, chapterCount, language])

  const handleStop = () => abortRef.current?.abort()

  const handleDownload = useCallback(() => {
    if (chapters.length === 0) return
    const md = chapters
      .map((ch, i) => `# 第${i + 1}章 ${ch.title}\n\n${ch.content}`)
      .join('\n\n---\n\n')
    const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'novel.md'
    a.click()
    URL.revokeObjectURL(url)
  }, [chapters])

  if (!currentSession) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-500 text-sm p-4">
        {t.noSession}
      </div>
    )
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      {/* Controls */}
      <div className="px-3 py-2 border-b border-slate-700 space-y-2">
        <div className="flex items-center gap-2 flex-wrap">
          <label className="text-xs text-slate-400">{t.style}</label>
          <select
            value={style}
            onChange={(e) => setStyle(e.target.value)}
            className="text-xs bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1"
            disabled={loading}
          >
            {STYLES.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
          <label className="text-xs text-slate-400">{t.chapters}</label>
          <input
            type="number"
            min={2}
            max={20}
            value={chapterCount}
            onChange={(e) => setChapterCount(Number(e.target.value))}
            className="text-xs bg-slate-800 text-slate-200 border border-slate-600 rounded px-2 py-1 w-14"
            disabled={loading}
          />
        </div>
        <div className="flex items-center gap-2">
          {!loading ? (
            <button
              onClick={handleGenerate}
              className="text-xs px-3 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded transition-colors"
            >
              {t.generate}
            </button>
          ) : (
            <button
              onClick={handleStop}
              className="text-xs px-3 py-1 bg-red-600 hover:bg-red-500 text-white rounded transition-colors"
            >
              {t.stop}
            </button>
          )}
          {chapters.length > 0 && chapters.some((c) => c.content) && (
            <button
              onClick={handleDownload}
              className="text-xs px-3 py-1 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
            >
              {t.download}
            </button>
          )}
          {loading && (
            <span className="text-xs text-indigo-400 animate-pulse">{t.generating}</span>
          )}
        </div>
        {error && <p className="text-xs text-red-400">{error}</p>}
      </div>

      {/* Chapter list + preview */}
      <div className="flex-1 flex overflow-hidden">
        {/* Sidebar: chapter list */}
        {chapters.length > 0 && (
          <div className="w-40 min-w-[140px] border-r border-slate-700 overflow-y-auto">
            {chapters.map((ch, i) => (
              <button
                key={i}
                onClick={() => setActiveIdx(i)}
                className={`w-full text-left px-3 py-2 text-xs border-b border-slate-700/50 transition-colors ${
                  activeIdx === i
                    ? 'bg-slate-700 text-slate-100'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-slate-200'
                }`}
              >
                <span className="font-medium">第{i + 1}章</span>
                <span className="block truncate text-[11px] opacity-70">{ch.title}</span>
                {streamingIdx === i && (
                  <span className="inline-block w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse ml-1" />
                )}
              </button>
            ))}
          </div>
        )}

        {/* Content preview */}
        <div className="flex-1 overflow-y-auto p-4">
          {chapters.length === 0 && !loading && (
            <p className="text-sm text-slate-500">{t.selectChapter}</p>
          )}
          {chapters[activeIdx] && (
            <div className="prose prose-invert prose-sm max-w-none">
              <h2 className="text-base font-bold text-slate-200 mb-3">
                第{activeIdx + 1}章 {chapters[activeIdx].title}
              </h2>
              {chapters[activeIdx].summary && (
                <p className="text-xs text-slate-500 italic mb-3">
                  {chapters[activeIdx].summary}
                </p>
              )}
              <div className="whitespace-pre-wrap text-slate-300 text-sm leading-relaxed">
                {chapters[activeIdx].content || (
                  <span className="text-slate-600">
                    {loading ? '...' : ''}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
