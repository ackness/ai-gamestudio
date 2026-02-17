import { Link, useLocation } from 'react-router-dom'

export function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const isEditor = location.pathname.startsWith('/projects/')

  return (
    <div className="flex flex-col h-screen">
      <header className="bg-slate-900 border-b border-slate-700 px-6 py-3 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <Link to="/" className="text-xl font-bold text-emerald-400 hover:text-emerald-300 no-underline">
            AI GameStudio
          </Link>
          {isEditor && (
            <Link
              to="/"
              className="text-sm text-slate-400 hover:text-slate-200 no-underline"
            >
              &larr; Projects
            </Link>
          )}
        </div>
        <div className="text-xs text-slate-500">MVP</div>
      </header>
      <main className="flex-1 flex flex-col overflow-hidden">
        {children}
      </main>
    </div>
  )
}
