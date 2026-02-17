import { useCallback, useEffect, useRef, useState } from 'react'
import { useProjectStore } from '../../stores/projectStore'

export function MarkdownEditor() {
  const { currentProject, updateWorldDoc } = useProjectStore()
  const [content, setContent] = useState('')
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const resetStatusTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const lastQueuedValueRef = useRef('')

  useEffect(() => {
    if (currentProject) {
      setContent(currentProject.world_doc || '')
    }
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
    if (resetStatusTimerRef.current) {
      clearTimeout(resetStatusTimerRef.current)
      resetStatusTimerRef.current = null
    }
    setSaveStatus('idle')
  }, [currentProject?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (resetStatusTimerRef.current) clearTimeout(resetStatusTimerRef.current)
    }
  }, [])

  const saveNow = useCallback(
    async (value: string) => {
      const projectId = currentProject?.id
      if (!projectId) return
      setSaveStatus('saving')
      try {
        await updateWorldDoc(value, projectId)
        setSaveStatus('saved')
        if (resetStatusTimerRef.current) clearTimeout(resetStatusTimerRef.current)
        resetStatusTimerRef.current = setTimeout(() => setSaveStatus('idle'), 2000)
      } catch (error) {
        console.error('Failed to save world doc:', error)
        setSaveStatus('error')
      }
    },
    [currentProject?.id, updateWorldDoc],
  )

  const debouncedSave = useCallback(
    (value: string) => {
      if (timerRef.current) clearTimeout(timerRef.current)
      if (resetStatusTimerRef.current) {
        clearTimeout(resetStatusTimerRef.current)
        resetStatusTimerRef.current = null
      }
      lastQueuedValueRef.current = value
      setSaveStatus('idle')
      timerRef.current = setTimeout(async () => {
        timerRef.current = null
        await saveNow(value)
      }, 1000)
    },
    [saveNow],
  )

  const handleChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setContent(value)
    debouncedSave(value)
  }

  const handleBlur = () => {
    if (!currentProject?.id) return
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
      void saveNow(lastQueuedValueRef.current || content)
    }
  }

  return (
    <div className="flex-1 flex flex-col overflow-hidden">
      <div className="flex items-center justify-end px-3 py-1 bg-slate-900/50">
        <span className="text-xs text-slate-500">
          {saveStatus === 'saving' && 'Saving...'}
          {saveStatus === 'saved' && 'Saved'}
          {saveStatus === 'error' && 'Save failed'}
        </span>
      </div>
      <textarea
        value={content}
        onChange={handleChange}
        onBlur={handleBlur}
        className="flex-1 w-full p-4 bg-slate-950 text-slate-200 text-sm font-mono resize-none focus:outline-none leading-relaxed"
        placeholder="# My Game World&#10;&#10;Describe your world, characters, rules, and lore here...&#10;&#10;The DM will use this document to guide gameplay."
        spellCheck={false}
      />
    </div>
  )
}
