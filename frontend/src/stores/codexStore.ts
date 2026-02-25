import { create } from 'zustand'

export interface CodexEntry {
  action: 'unlock' | 'update'
  category: 'monster' | 'item' | 'location' | 'lore' | 'character'
  entry_id: string
  title: string
  content: string
  tags?: string[]
  image_hint?: string
  _isNew?: boolean
}

interface CodexState {
  entries: CodexEntry[]
  loading: boolean
  searchQuery: string
  setSearchQuery: (q: string) => void
  fetchEntries: (projectId: string) => Promise<void>
  addEntry: (entry: CodexEntry) => void
  clearNewFlags: () => void
}

export const useCodexStore = create<CodexState>((set, get) => ({
  entries: [],
  loading: false,
  searchQuery: '',
  setSearchQuery: (q) => set({ searchQuery: q }),

  fetchEntries: async (projectId: string) => {
    set({ loading: true })
    try {
      const resp = await fetch(`/api/plugins/codex/${projectId}`)
      if (resp.ok) {
        const data = await resp.json()
        set({ entries: data.entries || [], loading: false })
      } else {
        set({ loading: false })
      }
    } catch {
      set({ loading: false })
    }
  },

  addEntry: (entry: CodexEntry) => {
    const entries = get().entries
    const idx = entries.findIndex((e) => e.entry_id === entry.entry_id)
    const tagged = { ...entry, _isNew: true }
    if (idx >= 0) {
      const updated = [...entries]
      updated[idx] = tagged
      set({ entries: updated })
    } else {
      set({ entries: [...entries, tagged] })
    }
  },

  clearNewFlags: () => {
    set({ entries: get().entries.map((e) => ({ ...e, _isNew: false })) })
  },
}))
