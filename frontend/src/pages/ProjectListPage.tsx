import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../stores/projectStore'
import { CreateProjectWizard } from '../components/editor/CreateProjectWizard'

export function ProjectListPage() {
  const { projects, loading, fetchProjects } = useProjectStore()
  const navigate = useNavigate()
  const [showWizard, setShowWizard] = useState(false)

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  return (
    <div className="p-6 max-w-6xl mx-auto w-full">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-slate-100">Your Projects</h1>
          <p className="text-slate-400 mt-1">Create and manage your game worlds</p>
        </div>
        <button
          onClick={() => setShowWizard(true)}
          className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white rounded-lg font-medium transition-colors"
        >
          + New Project
        </button>
      </div>

      <CreateProjectWizard open={showWizard} onClose={() => setShowWizard(false)} />

      {loading && projects.length === 0 ? (
        <div className="text-center text-slate-400 py-20">Loading projects...</div>
      ) : projects.length === 0 ? (
        <div className="text-center py-20">
          <p className="text-slate-400 text-lg">No projects yet</p>
          <p className="text-slate-500 mt-2">Create your first game world to get started</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <div
              key={project.id}
              onClick={() => navigate(`/projects/${project.id}`)}
              className="bg-slate-800 border border-slate-700 rounded-xl p-5 cursor-pointer hover:border-emerald-500/50 hover:bg-slate-750 transition-all group"
            >
              <h3 className="text-lg font-semibold text-slate-100 group-hover:text-emerald-400 transition-colors">
                {project.name}
              </h3>
              {project.description && (
                <p className="text-slate-400 mt-2 text-sm line-clamp-2">{project.description}</p>
              )}
              <p className="text-slate-500 text-xs mt-3">
                {new Date(project.created_at).toLocaleDateString()}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
