import { Component, type ReactNode } from 'react'
import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Layout } from './components/Layout'
import { ProjectListPage } from './pages/ProjectListPage'
import { ProjectEditorPage } from './pages/ProjectEditorPage'
import { TooltipProvider } from '@/components/ui/tooltip'

interface ErrorBoundaryState {
  hasError: boolean
  error: Error | null
}

class ErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { hasError: false, error: null }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen bg-slate-900 flex items-center justify-center p-8">
          <div className="bg-slate-800 border border-red-700/50 rounded-xl p-6 max-w-lg w-full space-y-4">
            <h2 className="text-red-400 text-lg font-medium">Something went wrong</h2>
            <pre className="text-xs text-slate-400 bg-slate-900 rounded p-3 overflow-auto max-h-40">
              {this.state.error?.message}
            </pre>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              className="text-sm px-4 py-2 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded transition-colors"
            >
              Try Again
            </button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function App() {
  return (
    <ErrorBoundary>
      <TooltipProvider>
        <BrowserRouter>
          <Layout>
            <Routes>
              <Route path="/" element={<ProjectListPage />} />
              <Route path="/projects/:id" element={<ProjectEditorPage />} />
            </Routes>
          </Layout>
        </BrowserRouter>
      </TooltipProvider>
    </ErrorBoundary>
  )
}

export default App
