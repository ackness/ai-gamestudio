import { useState, useRef, useEffect } from 'react'

interface Props {
  onSend: (message: string) => void
  disabled: boolean
}

export function ChatInput({ onSend, disabled }: Props) {
  const [value, setValue] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto'
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px'
    }
  }, [value])

  const handleSubmit = () => {
    const trimmed = value.trim()
    if (!trimmed || disabled) return
    onSend(trimmed)
    setValue('')
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit()
    }
  }

  return (
    <div
      className="px-3 py-3"
      style={{
        background: 'rgba(6, 13, 26, 0.8)',
        borderTop: '1px solid rgba(148, 163, 184, 0.07)',
        backdropFilter: 'blur(8px)',
      }}
    >
      <div
        className="flex gap-2 items-end rounded-2xl px-3 py-2 transition-all duration-200"
        style={{
          background: 'rgba(16, 28, 46, 0.7)',
          border: `1px solid ${disabled ? 'rgba(148,163,184,0.08)' : 'rgba(148,163,184,0.14)'}`,
        }}
        onFocusCapture={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.border = '1px solid rgba(16, 185, 129, 0.35)'
          el.style.boxShadow = '0 0 0 3px rgba(16, 185, 129, 0.06), 0 0 16px rgba(16, 185, 129, 0.06)'
        }}
        onBlurCapture={(e) => {
          const el = e.currentTarget as HTMLElement
          el.style.border = '1px solid rgba(148,163,184,0.14)'
          el.style.boxShadow = 'none'
        }}
      >
        <textarea
          ref={textareaRef}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          rows={1}
          className="flex-1 bg-transparent resize-none focus:outline-none text-sm leading-relaxed disabled:opacity-40"
          style={{
            color: '#dff0f7',
            caretColor: '#10b981',
          }}
          placeholder={disabled ? '等待响应...' : '你做什么？（Enter 发送，Shift+Enter 换行）'}
        />
        <button
          onClick={handleSubmit}
          disabled={disabled || !value.trim()}
          className="shrink-0 w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200 disabled:opacity-30 disabled:cursor-not-allowed"
          style={{
            background:
              disabled || !value.trim()
                ? 'rgba(148, 163, 184, 0.06)'
                : 'linear-gradient(135deg, rgba(16,185,129,0.25) 0%, rgba(6,182,212,0.2) 100%)',
            border:
              disabled || !value.trim()
                ? '1px solid rgba(148, 163, 184, 0.1)'
                : '1px solid rgba(16, 185, 129, 0.35)',
            color: disabled || !value.trim() ? 'rgba(148,163,184,0.3)' : '#34d399',
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <line x1="7" y1="12" x2="7" y2="2" />
            <polyline points="3,6 7,2 11,6" />
          </svg>
        </button>
      </div>
      <p className="text-center mt-1.5 text-[10px]" style={{ color: 'rgba(148,163,184,0.2)' }}>
        Enter 发送 · Shift+Enter 换行
      </p>
    </div>
  )
}
