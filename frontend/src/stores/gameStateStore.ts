import { create } from 'zustand'
import type { Character, GameEvent } from '../types'
import { StorageFactory } from '../services/settingsStorage'
import { idbPutCharacter, idbPutEvent } from '../services/localDb'
import { useSessionStore } from './sessionStore'

interface GameStateStore {
  characters: Character[]
  worldState: Record<string, unknown>
  events: GameEvent[]
  setCharacters: (characters: Character[]) => void
  mergeCharacters: (incoming: Character[]) => void
  updateCharacter: (character: Character) => void
  setWorldState: (state: Record<string, unknown>) => void
  setEvents: (events: GameEvent[]) => void
  addEvent: (event: GameEvent) => void
  updateEvent: (event: GameEvent) => void
}

function writeCharsToIdb(characters: Character[]) {
  if (characters.length === 0) return
  StorageFactory.isStoragePersistent()
    .then((persistent) => {
      if (!persistent) {
        const sessionId = useSessionStore.getState().currentSession?.id
        characters.forEach((c) => {
          const record = c as unknown as Record<string, unknown>
          const withSession =
            record.session_id || !sessionId
              ? record
              : { ...record, session_id: sessionId }
          idbPutCharacter(withSession).catch(() => {})
        })
      }
    })
    .catch(() => {})
}

function writeEventsToIdb(events: GameEvent[]) {
  if (events.length === 0) return
  StorageFactory.isStoragePersistent()
    .then((persistent) => {
      if (!persistent) {
        events.forEach((e) =>
          idbPutEvent(e as unknown as Record<string, unknown>).catch(() => {}),
        )
      }
    })
    .catch(() => {})
}

export const useGameStateStore = create<GameStateStore>((set) => ({
  characters: [],
  worldState: {},
  events: [],

  setCharacters: (characters) => {
    set({ characters })
    writeCharsToIdb(characters)
  },

  mergeCharacters: (incoming) => {
    let merged: Character[] = []
    set((state) => {
      const map = new Map(state.characters.map((c) => [c.id, c]))
      // Also build a name index for matching when incoming data lacks id
      const nameToId = new Map(state.characters.map((c) => [c.name, c.id]))
      for (const c of incoming) {
        const key = c.id || nameToId.get(c.name)
        if (key) {
          const existing = map.get(key)
          // Merge: keep existing fields, override with incoming non-undefined fields
          map.set(key, { ...existing, ...c, id: key } as Character)
        } else {
          // Truly new character
          const id = c.id || `temp-${c.name}`
          map.set(id, { ...c, id } as Character)
        }
      }
      merged = Array.from(map.values())
      return { characters: merged }
    })
    writeCharsToIdb(merged)
  },

  updateCharacter: (character) => {
    set((state) => ({
      characters: state.characters.map((c) => (c.id === character.id ? character : c)),
    }))
    writeCharsToIdb([character])
  },

  setWorldState: (worldState) => set({ worldState }),

  setEvents: (events) => {
    set({ events })
    writeEventsToIdb(events)
  },

  addEvent: (event) => {
    set((state) => ({ events: [...state.events, event] }))
    writeEventsToIdb([event])
  },

  updateEvent: (event) => {
    set((state) => ({
      events: state.events.map((e) => (e.id === event.id ? event : e)),
    }))
    writeEventsToIdb([event])
  },
}))
