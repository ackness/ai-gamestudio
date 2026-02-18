interface Props {
  onStart: () => void
  loading?: boolean
  error?: string | null
}

export function WelcomeScreen({ onStart, loading, error }: Props) {
  return (
    <div className="flex-1 flex items-center justify-center relative overflow-hidden">
      {/* Ambient background glow */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            'radial-gradient(ellipse 80% 60% at 50% 50%, rgba(16,185,129,0.06) 0%, transparent 70%), ' +
            'radial-gradient(ellipse 50% 40% at 70% 30%, rgba(139,92,246,0.04) 0%, transparent 60%)',
        }}
      />

      <div className="relative text-center space-y-8 max-w-sm px-6">
        {/* Icon */}
        <div className="flex justify-center">
          <div
            className="w-20 h-20 rounded-2xl flex items-center justify-center"
            style={{
              background: 'linear-gradient(135deg, rgba(16,185,129,0.12) 0%, rgba(139,92,246,0.12) 100%)',
              border: '1px solid rgba(16, 185, 129, 0.25)',
              boxShadow: '0 0 40px rgba(16,185,129,0.1), 0 0 80px rgba(139,92,246,0.06), inset 0 1px 0 rgba(255,255,255,0.05)',
            }}
          >
            <svg width="36" height="36" viewBox="0 0 36 36" fill="none">
              <path
                d="M18 4L22 13H32L24 19L27 29L18 23L9 29L12 19L4 13H14L18 4Z"
                fill="url(#welcome-star)"
                opacity="0.9"
              />
              <defs>
                <linearGradient id="welcome-star" x1="4" y1="4" x2="32" y2="32">
                  <stop offset="0%" stopColor="#10b981" />
                  <stop offset="100%" stopColor="#8b5cf6" />
                </linearGradient>
              </defs>
            </svg>
          </div>
        </div>

        {/* Text */}
        <div className="space-y-3">
          <h2
            className="font-cinzel text-2xl font-medium tracking-wide"
            style={{ color: '#dff0f7' }}
          >
            准备开始冒险
          </h2>
          <p className="text-sm leading-relaxed" style={{ color: 'rgba(127, 168, 196, 0.7)' }}>
            世界已就绪，命运等待书写。
            <br />
            点击下方按钮，开始你的旅程。
          </p>
        </div>

        {/* Error */}
        {error && (
          <div
            className="rounded-xl px-4 py-3 text-sm text-left"
            style={{
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.25)',
              color: '#fca5a5',
            }}
          >
            {error}
          </div>
        )}

        {/* CTA Button */}
        <button
          onClick={onStart}
          disabled={loading}
          className="relative w-full py-3 rounded-xl text-sm font-medium transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed"
          style={{
            background: loading
              ? 'rgba(16, 185, 129, 0.12)'
              : 'linear-gradient(135deg, rgba(16,185,129,0.22) 0%, rgba(6,182,212,0.15) 100%)',
            border: '1px solid rgba(16, 185, 129, 0.4)',
            color: '#34d399',
            boxShadow: loading ? 'none' : '0 0 24px rgba(16, 185, 129, 0.14)',
          }}
          onMouseEnter={(e) => {
            if (!loading) {
              e.currentTarget.style.boxShadow = '0 0 36px rgba(16,185,129,0.22), 0 4px 16px rgba(0,0,0,0.3)'
              e.currentTarget.style.transform = 'translateY(-1px)'
            }
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.boxShadow = '0 0 24px rgba(16, 185, 129, 0.14)'
            e.currentTarget.style.transform = 'translateY(0)'
          }}
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="w-3.5 h-3.5 rounded-full border-2 border-current border-t-transparent animate-spin" />
              正在初始化...
            </span>
          ) : (
            <span className="flex items-center justify-center gap-2">
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2">
                <polygon points="3,2 12,7 3,12" />
              </svg>
              {error ? '重试' : '开始冒险'}
            </span>
          )}
        </button>
      </div>
    </div>
  )
}
