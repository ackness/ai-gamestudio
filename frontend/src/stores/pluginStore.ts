import { create } from 'zustand'
import type { Plugin } from '../types'
import * as api from '../services/api'

interface PluginStore {
  plugins: Plugin[]
  blockConflicts: { block_type: string; overridden_plugin: string; winner_plugin: string }[]
  loading: boolean
  fetchPlugins: (projectId?: string) => Promise<void>
  togglePlugin: (name: string, projectId: string, enabled: boolean) => Promise<void>
}

interface EnabledPluginState {
  plugin_name: string
  enabled: boolean
  required: boolean
  auto_enabled: boolean
  explicitly_disabled: boolean
  dependencies: string[]
  required_by: string[]
}

export const usePluginStore = create<PluginStore>((set) => ({
  plugins: [],
  blockConflicts: [],
  loading: false,

  fetchPlugins: async (projectId) => {
    set({ loading: true })
    try {
      const raw = await api.getPlugins()

      // Fetch project-specific plugin state if a projectId is given
      let enabledMap = new Map<string, EnabledPluginState>()
      let conflicts: { block_type: string; overridden_plugin: string; winner_plugin: string }[] = []
      if (projectId) {
        try {
          const enabled = await api.getEnabledPlugins(projectId)
          enabledMap = new Map(enabled.map((e) => [e.plugin_name, e] as const))
        } catch {
          // ignore — fall back to defaults
        }
        try {
          conflicts = await api.getPluginBlockConflicts(projectId)
        } catch {
          // ignore — fall back to defaults
        }
      }

      const plugins: Plugin[] = raw.map((p) => ({
        name: p.name,
        description: p.description,
        type: p.type,
        required: p.required,
        default_enabled: p.default_enabled || false,
        supersedes: p.supersedes || [],
        enabled: p.required ? true : enabledMap.has(p.name),
        auto_enabled: enabledMap.get(p.name)?.auto_enabled ?? false,
        explicitly_disabled: enabledMap.get(p.name)?.explicitly_disabled ?? false,
        dependencies: p.dependencies || enabledMap.get(p.name)?.dependencies || [],
        required_by: enabledMap.get(p.name)?.required_by || [],
        version: p.version || '',
        manifest_source: p.manifest_source || 'v1_fallback',
        capabilities: p.capabilities || [],
        has_script_capability: !!p.has_script_capability,
        i18n: p.i18n || {},
      }))
      set({ plugins, blockConflicts: conflicts, loading: false })
    } catch {
      set({ loading: false })
    }
  },

  togglePlugin: async (name, projectId, enabled) => {
    try {
      await api.togglePlugin(name, projectId, enabled)
      await usePluginStore.getState().fetchPlugins(projectId)
    } catch {
      // ignore
    }
  },
}))
