import { useCallback, useEffect, useRef, useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'

const DEFAULT_INIT_PROMPT =
  '玩家开始了一场新游戏。请根据世界观文档生成一段沉浸式的开场叙事。' +
  '在叙事末尾包含一个 json:character_sheet 代码块用于角色创建，' +
  '其中 editable_fields 需包含 \'name\'。' +
  '同时包含一个 json:scene_update 代码块来建立起始场景。'

export function InitPromptEditor() {
  const { currentProject, updateProject } = useProjectStore()
  const [content, setContent] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved'>('idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (currentProject) {
      setContent(currentProject.init_prompt || '')
    }
  }, [currentProject?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  const debouncedSave = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      setSaveStatus('idle')
      timerRef.current = setTimeout(async () => {
        setSaveStatus('saving')
        try {
          await updateProject({ init_prompt: value || undefined })
          setSaveStatus('saved')
          setTimeout(() => setSaveStatus('idle'), 2000)
        } catch {
          setSaveStatus('idle')
        }
      }, 1000)
    },
    [updateProject],
  )

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setContent(value)
    debouncedSave(value)
  }

  const handleReset = () => {
    setContent('')
    debouncedSave('')
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1 bg-slate-900/50">
        <span className="text-xs text-slate-500">
          {content ? 'Custom' : 'Using default'}
        </span>
        <div className="flex items-center gap-2">
          {content && (
            <button
              onClick={handleReset}
              className="text-xs text-slate-500 hover:text-slate-300 transition-colors"
            >
              Reset to default
            </button>
          )}
          <span className="text-xs text-slate-500">
            {saveStatus === 'saving' && 'Saving...'}
            {saveStatus === 'saved' && 'Saved'}
          </span>
        </div>
      </div>
      <textarea
        value={content}
        onChange={handleChange}
        className="flex-1 w-full p-4 bg-slate-950 text-slate-200 text-sm font-mono resize-none focus:outline-none leading-relaxed"
        placeholder={DEFAULT_INIT_PROMPT}
        spellCheck={false}
      />
    </div>
  )
}
