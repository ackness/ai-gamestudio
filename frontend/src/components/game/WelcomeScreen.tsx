interface Props {
  onStart: () => void
  loading?: boolean
  error?: string | null
}

export function WelcomeScreen({ onStart, loading, error }: Props) {
  return (
    <div className="flex-1 flex items-center justify-center">
      <div className="text-center space-y-6 max-w-md px-6">
        <div className="space-y-2">
          <h2 className="text-2xl font-bold text-slate-200">准备开始冒险</h2>
          <p className="text-slate-400 text-sm">
            世界已就绪，点击下方按钮开始你的旅程。
          </p>
        </div>

        {error && (
          <div className="bg-red-900/30 border border-red-800/50 rounded-lg px-4 py-3 text-sm text-red-300">
            {error}
          </div>
        )}

        <button
          onClick={onStart}
          disabled={loading}
          className="px-6 py-3 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors text-sm"
        >
          {loading ? '正在初始化...' : error ? '重试' : '开始冒险'}
        </button>
      </div>
    </div>
  )
}
