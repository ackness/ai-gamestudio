import { create } from 'zustand'
import type { Project } from '../types'
import * as api from '../services/api'

interface ProjectStore {
  projects: Project[]
  currentProject: Project | null
  loading: boolean
  fetchProjects: () => Promise<void>
  createProject: (data: { name: string; description?: string; world_doc?: string }) => Promise<Project>
  selectProject: (id: string) => Promise<void>
  updateWorldDoc: (worldDoc: string, projectId?: string) => Promise<void>
  updateProject: (data: Partial<Project>, projectId?: string) => Promise<void>
  setCurrentProject: (project: Project | null) => void
}

export const useProjectStore = create<ProjectStore>((set, get) => ({
  projects: [],
  currentProject: null,
  loading: false,

  fetchProjects: async () => {
    set({ loading: true })
    try {
      const projects = await api.getProjects()
      set({ projects, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  createProject: async (data) => {
    const project = await api.createProject(data)
    set((state) => ({ projects: [...state.projects, project] }))
    return project
  },

  selectProject: async (id) => {
    set({ loading: true })
    try {
      const project = await api.getProject(id)
      set({ currentProject: project, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  updateWorldDoc: async (worldDoc, projectId) => {
    const currentProject = get().currentProject
    const targetProjectId = projectId ?? currentProject?.id
    if (!targetProjectId) return
    const updated = await api.updateProject(targetProjectId, { world_doc: worldDoc })
    set((state) => (state.currentProject?.id === targetProjectId ? { currentProject: updated } : {}))
  },

  updateProject: async (data, projectId) => {
    const currentProject = get().currentProject
    const targetProjectId = projectId ?? currentProject?.id
    if (!targetProjectId) return
    const updated = await api.updateProject(targetProjectId, data)
    set((state) => (state.currentProject?.id === targetProjectId ? { currentProject: updated } : {}))
  },

  setCurrentProject: (project) => set({ currentProject: project }),
}))
