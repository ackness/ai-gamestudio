import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { useUiStore } from '../stores/uiStore'
import { CreateProjectWizard } from '../components/editor/CreateProjectWizard'

export function ProjectListPage() {
  const { projects, loading, fetchProjects } = useProjectStore()
  const navigate = useNavigate()
  const [showWizard, setShowWizard] = useState(false)
  const storagePersistent = useUiStore((s) => s.storagePersistent)
  const [bannerDismissed, setBannerDismissed] = useState(
    () => localStorage.getItem('ai-gamestudio:ephemeral-banner-dismissed') === '1'
  )

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  const dismissBanner = () => {
    localStorage.setItem('ai-gamestudio:ephemeral-banner-dismissed', '1')
    setBannerDismissed(true)
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Ephemeral storage notice */}
      {storagePersistent === false && !bannerDismissed && (
        <div
          className="flex items-start gap-3 px-5 py-3"
          style={{
            background: 'rgba(245, 158, 11, 0.07)',
            borderBottom: '1px solid rgba(245, 158, 11, 0.2)',
          }}
        >
          <svg className="shrink-0 mt-0.5" width="15" height="15" viewBox="0 0 15 15" fill="none">
            <path d="M7.5 1L1 13h13L7.5 1z" stroke="rgba(245,158,11,0.8)" strokeWidth="1.4" strokeLinejoin="round"/>
            <path d="M7.5 6v3.5M7.5 11v.5" stroke="rgba(245,158,11,0.8)" strokeWidth="1.4" strokeLinecap="round"/>
          </svg>
          <div className="flex-1 min-w-0">
            <p className="text-xs font-medium" style={{ color: 'rgba(245,158,11,0.9)' }}>
              数据不会持久保存
            </p>
            <p className="text-xs mt-0.5" style={{ color: 'rgba(245,158,11,0.6)' }}>
              当前部署使用临时存储，刷新或重启后数据将丢失。
              部署到本地可获得完整的历史记录与持久化功能。
            </p>
          </div>
          <button
            onClick={dismissBanner}
            className="shrink-0 text-xs px-2 py-0.5 rounded transition-colors"
            style={{ color: 'rgba(245,158,11,0.5)' }}
            onMouseEnter={(e) => { e.currentTarget.style.color = 'rgba(245,158,11,0.9)' }}
            onMouseLeave={(e) => { e.currentTarget.style.color = 'rgba(245,158,11,0.5)' }}
          >
            ✕
          </button>
        </div>
      )}
      {/* Hero */}
      <div
        className="relative px-8 pt-16 pb-12 text-center overflow-hidden"
        style={{
          background: 'linear-gradient(180deg, rgba(16,185,129,0.05) 0%, transparent 100%)',
          borderBottom: '1px solid rgba(148, 163, 184, 0.07)',
        }}
      >
        {/* Decorative rings */}
        <div
          className="absolute left-1/2 top-0 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] rounded-full pointer-events-none"
          style={{
            background: 'radial-gradient(circle, rgba(16,185,129,0.04) 0%, transparent 70%)',
          }}
        />
        <p
          className="font-cinzel text-xs tracking-[0.25em] uppercase mb-4"
          style={{ color: 'rgba(16, 185, 129, 0.6)' }}
        >
          Narrative AI Engine
        </p>
        <h1
          className="font-cinzel text-3xl font-semibold mb-3 tracking-wide"
          style={{
            background: 'linear-gradient(135deg, #dff0f7 0%, #a0c4d8 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            backgroundClip: 'text',
          }}
        >
          Your Worlds
        </h1>
        <p className="text-sm mb-8" style={{ color: 'rgba(127, 168, 196, 0.7)' }}>
          Forge your story. Shape your world. Begin your legend.
        </p>
        <button
          onClick={() => setShowWizard(true)}
          className="relative inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-sm font-medium transition-all duration-200"
          style={{
            background: 'linear-gradient(135deg, rgba(16,185,129,0.2) 0%, rgba(6,182,212,0.15) 100%)',
            border: '1px solid rgba(16, 185, 129, 0.35)',
            color: '#34d399',
            boxShadow: '0 0 20px rgba(16, 185, 129, 0.12)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'rgba(16, 185, 129, 0.6)'
            e.currentTarget.style.boxShadow = '0 0 28px rgba(16, 185, 129, 0.2), 0 4px 12px rgba(0,0,0,0.3)'
            e.currentTarget.style.transform = 'translateY(-1px)'
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(16, 185, 129, 0.35)'
            e.currentTarget.style.boxShadow = '0 0 20px rgba(16, 185, 129, 0.12)'
            e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
            <line x1="7" y1="1" x2="7" y2="13" />
            <line x1="1" y1="7" x2="13" y2="7" />
          </svg>
          New World
        </button>
      </div>

      {/* Content */}
      <div className="max-w-5xl mx-auto px-6 py-8">
        <CreateProjectWizard open={showWizard} onClose={() => setShowWizard(false)} />

        {loading && projects.length === 0 ? (
          <div className="flex items-center justify-center py-24 gap-3" style={{ color: 'rgba(127,168,196,0.5)' }}>
            <span className="w-4 h-4 rounded-full border-2 border-current border-t-transparent animate-spin" />
            <span className="text-sm">Loading worlds...</span>
          </div>
        ) : projects.length === 0 ? (
          <div className="text-center py-24 space-y-3">
            <div
              className="w-16 h-16 mx-auto rounded-2xl flex items-center justify-center mb-6"
              style={{
                background: 'rgba(139, 92, 246, 0.08)',
                border: '1px solid rgba(139, 92, 246, 0.2)',
              }}
            >
              <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="rgba(139,92,246,0.6)" strokeWidth="1.5">
                <circle cx="12" cy="12" r="10" />
                <path d="M2 12h20M12 2a15.3 15.3 0 010 20M12 2a15.3 15.3 0 000 20" />
              </svg>
            </div>
            <p className="text-base font-medium" style={{ color: 'rgba(223,240,247,0.7)' }}>No worlds yet</p>
            <p className="text-sm" style={{ color: 'rgba(127,168,196,0.5)' }}>Create your first world to begin your adventure</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <div
                key={project.id}
                onClick={() => navigate(`/projects/${project.id}`)}
                className="cursor-pointer rounded-2xl p-5 transition-all duration-200 group"
                style={{
                  background: 'rgba(16, 28, 46, 0.6)',
                  border: '1px solid rgba(148, 163, 184, 0.1)',
                  boxShadow: '0 4px 20px rgba(0, 0, 0, 0.25)',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.border = '1px solid rgba(16, 185, 129, 0.25)'
                  e.currentTarget.style.boxShadow = '0 0 30px rgba(16,185,129,0.08), 0 8px 32px rgba(0,0,0,0.35)'
                  e.currentTarget.style.transform = 'translateY(-2px)'
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.border = '1px solid rgba(148, 163, 184, 0.1)'
                  e.currentTarget.style.boxShadow = '0 4px 20px rgba(0, 0, 0, 0.25)'
                  e.currentTarget.style.transform = 'translateY(0)'
                }}
              >
                <div
                  className="w-8 h-8 rounded-lg mb-4 flex items-center justify-center"
                  style={{
                    background: 'rgba(139, 92, 246, 0.12)',
                    border: '1px solid rgba(139, 92, 246, 0.2)',
                  }}
                >
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="rgba(139,92,246,0.7)" strokeWidth="1.8">
                    <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                  </svg>
                </div>
                <h3
                  className="text-base font-semibold mb-1.5 transition-colors"
                  style={{ color: '#c5e0ee' }}
                >
                  {project.name}
                </h3>
                {project.description && (
                  <p className="text-sm line-clamp-2 mb-3" style={{ color: 'rgba(127,168,196,0.6)' }}>
                    {project.description}
                  </p>
                )}
                <div className="flex items-center justify-between mt-3 pt-3" style={{ borderTop: '1px solid rgba(148,163,184,0.07)' }}>
                  <span className="text-xs" style={{ color: 'rgba(127,168,196,0.4)' }}>
                    {new Date(project.created_at).toLocaleDateString()}
                  </span>
                  <span
                    className="text-xs opacity-0 group-hover:opacity-100 transition-opacity flex items-center gap-1"
                    style={{ color: '#10b981' }}
                  >
                    Open
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="1.8">
                      <path d="M2 8L8 2M8 2H4M8 2v4" />
                    </svg>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
