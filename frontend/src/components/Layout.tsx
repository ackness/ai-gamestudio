import { useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useUiStore } from '../stores/uiStore'

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const isEditor = location.pathname.startsWith('/projects/')
  const { checkStoragePersistence, language } = useUiStore()

  useEffect(() => {
    checkStoragePersistence()
  }, [checkStoragePersistence])

  return (
    <div className="flex flex-col h-screen">
      <header
        className="shrink-0 px-5 py-0 flex items-center justify-between"
        style={{
          background: 'rgba(6, 13, 26, 0.92)',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          borderBottom: '1px solid rgba(148, 163, 184, 0.08)',
          boxShadow: '0 1px 0 rgba(16, 185, 129, 0.06)',
          height: '52px',
        }}
      >
        <div className="flex items-center gap-5">
          <Link to="/" className="flex items-center gap-2.5 no-underline group">
            {/* Arcane sigil icon */}
            <div
              className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
              style={{
                background: 'linear-gradient(135deg, rgba(16,185,129,0.2) 0%, rgba(139,92,246,0.2) 100%)',
                border: '1px solid rgba(16, 185, 129, 0.3)',
                boxShadow: '0 0 12px rgba(16, 185, 129, 0.15)',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M8 2L10.5 6.5H14L10.8 9.2L12 14L8 11.5L4 14L5.2 9.2L2 6.5H5.5L8 2Z"
                  fill="url(#star-grad)" stroke="rgba(16,185,129,0.6)" strokeWidth="0.5" />
                <defs>
                  <linearGradient id="star-grad" x1="2" y1="2" x2="14" y2="14">
                    <stop offset="0%" stopColor="#10b981" stopOpacity="0.9" />
                    <stop offset="100%" stopColor="#8b5cf6" stopOpacity="0.9" />
                  </linearGradient>
                </defs>
              </svg>
            </div>
            <span
              className="font-cinzel text-base font-medium tracking-wide"
              style={{
                background: 'linear-gradient(135deg, #34d399 0%, #10b981 40%, #06b6d4 100%)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}
            >
              AI GameStudio
            </span>
          </Link>

          {isEditor && (
            <Link
              to="/"
              className="flex items-center gap-1.5 no-underline group"
              style={{ color: 'rgba(127, 168, 196, 0.7)' }}
            >
              <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path d="M8 2L4 6l4 4" />
              </svg>
              <span className="text-xs transition-colors group-hover:text-[#7fa8c4]">{language === 'zh' ? '项目' : 'Projects'}</span>
            </Link>
          )}
        </div>

        <div
          className="text-[10px] font-mono tracking-widest uppercase px-2 py-0.5 rounded"
          style={{
            color: 'rgba(139, 92, 246, 0.6)',
            background: 'rgba(139, 92, 246, 0.08)',
            border: '1px solid rgba(139, 92, 246, 0.15)',
          }}
        >
          ALPHA
        </div>
      </header>
      <main className="flex-1 flex flex-col overflow-hidden">
        {children}
      </main>
    </div>
  )
}
