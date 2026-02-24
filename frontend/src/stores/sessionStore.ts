import { create } from 'zustand'
import type { Session, Message, Scene, StoryImageData } from '../types'
import * as api from '../services/api'
import { StorageFactory } from '../services/settingsStorage'
import { idbGetSessions } from '../services/localDb'
import { syncToIdb, syncToIdbFireAndForget } from '../services/idbSync'
import { attachPendingBlocksForTurn, type TurnPendingBlock } from './sessionTurnUtils'
import { useProjectStore } from './projectStore'
import { useTokenStore } from './tokenStore'
import * as gameStorage from '../services/gameStorage'

export type PendingBlock = TurnPendingBlock

export type StreamStatus = 'idle' | 'waiting' | 'streaming' | 'done' | 'error'

interface SessionStore {
  sessions: Session[]
  currentSession: Session | null
  messages: Message[]
  isStreaming: boolean
  streamingContent: string
  streamStatus: StreamStatus
  pendingBlocks: PendingBlock[]
  phase: string
  pluginProcessing: boolean
  pluginProgress: { round: number; tool_calls: string[]; blocks_so_far: string[] } | null
  lastPluginSummary: { rounds: number; tool_calls: string[]; blocks_emitted: string[] } | null
  currentScene: Scene | null
  scenes: Scene[]
  messageImages: Record<string, StoryImageData[]>
  imageLoadingMessages: Set<string>
  fetchSessions: (projectId: string) => Promise<void>
  createSession: (projectId: string) => Promise<Session>
  switchSession: (session: Session) => Promise<void>
  deleteSession: (sessionId: string) => Promise<void>
  setCurrentSession: (session: Session | null) => void
  fetchMessages: (sessionId: string) => Promise<void>
  addMessage: (message: Message) => void
  setStreaming: (streaming: boolean) => void
  setStreamStatus: (status: StreamStatus) => void
  appendStreamContent: (content: string) => void
  clearStreamContent: () => void
  addPendingBlock: (block: PendingBlock) => void
  flushPendingBlocksForTurn: (turnId: string) => void
  clearPendingBlocks: () => void
  setPhase: (phase: string) => void
  setPluginProcessing: (processing: boolean) => void
  setPluginProgress: (progress: { round: number; tool_calls: string[]; blocks_so_far: string[] } | null) => void
  setLastPluginSummary: (summary: { rounds: number; tool_calls: string[]; blocks_emitted: string[] } | null) => void
  setCurrentScene: (scene: Scene | null) => void
  setScenes: (scenes: Scene[]) => void
  addScene: (scene: Scene) => void
  removeLastAssistantMessage: () => void
  deleteMessage: (messageId: string) => void
  deleteMessagesFrom: (messageId: string) => void
  setMessageImage: (messageId: string, image: StoryImageData) => void
  setImageLoading: (messageId: string, loading: boolean) => void
  clearMessageImages: () => void
  hydrateMessageImages: (sessionId: string) => Promise<void>
  updateBlockData: (blockId: string, data: unknown) => void
  updateMessageBlocks: (messageId: string, blocks: { type: string; data: unknown; block_id?: string }[]) => void
}

export const useSessionStore = create<SessionStore>((set) => ({
  sessions: [],
  currentSession: null,
  messages: [],
  isStreaming: false,
  streamingContent: '',
  streamStatus: 'idle' as StreamStatus,
  pendingBlocks: [],
  phase: 'init',
  pluginProcessing: false,
  pluginProgress: null,
  lastPluginSummary: null,
  currentScene: null,
  scenes: [],
  messageImages: {},
  imageLoadingMessages: new Set<string>(),

  fetchSessions: async (projectId) => {
    try {
      const persistent = await StorageFactory.isStoragePersistent()
      if (!persistent) {
        const rows = await idbGetSessions(projectId)
        set({ sessions: rows as unknown as Session[] })
      } else {
        const sessions = await api.getSessions(projectId)
        set({ sessions })
      }
    } catch {
      // ignore
    }
  },

  createSession: async (projectId) => {
    try {
      const persistent = await StorageFactory.isStoragePersistent()

      if (!persistent) {
        // Ephemeral backend (Vercel + SQLite): ensure project exists in backend first,
        // then create the session there so the chat endpoint can find it.
        const project = useProjectStore.getState().currentProject
        if (project) {
          await useProjectStore.getState().syncProjectToBackend(project)
        }
      }

      const session = await api.createSession(projectId)

      if (!persistent) {
        await syncToIdb('session', session)
      }

      set((state) => ({
        sessions: [...state.sessions, session],
        currentSession: session,
        messages: [],
        pendingBlocks: [],
        phase: 'init',
        currentScene: null,
        scenes: [],
        streamingContent: '',
        streamStatus: 'idle' as StreamStatus,
        isStreaming: false,
        messageImages: {},
        imageLoadingMessages: new Set<string>(),
      }))
      useTokenStore.getState().reset()
      return session
    } catch (err) {
      console.error('Failed to create session:', err)
      throw err
    }
  },

  setCurrentSession: (session) => set({ currentSession: session }),

  switchSession: async (session) => {
    set({
      currentSession: session,
      messages: [],
      pendingBlocks: [],
      phase: session.phase || 'init',
      currentScene: null,
      scenes: [],
      streamingContent: '',
      streamStatus: 'idle' as StreamStatus,
      isStreaming: false,
      messageImages: {},
      imageLoadingMessages: new Set<string>(),
    })
    useTokenStore.getState().reset()
    try {
      const messages = await gameStorage.fetchMessages(session.id)
      set({ messages })
    } catch {
      // ignore
    }
  },

  deleteSession: async (sessionId) => {
    try {
      const persistent = await StorageFactory.isStoragePersistent()
      await api.deleteSession(sessionId)
      if (!persistent) {
        await syncToIdb('deleteSession', { id: sessionId })
      }
      set((state) => {
        const sessions = state.sessions.filter((s) => s.id !== sessionId)
        const isCurrent = state.currentSession?.id === sessionId
        if (isCurrent) {
          return {
            sessions,
            currentSession: null,
            messages: [],
            pendingBlocks: [],
            phase: 'init',
            currentScene: null,
            scenes: [],
            streamingContent: '',
            streamStatus: 'idle' as StreamStatus,
            isStreaming: false,
            messageImages: {},
            imageLoadingMessages: new Set<string>(),
          }
        }
        return { sessions }
      })
      useTokenStore.getState().reset()
    } catch (err) {
      console.error('Failed to delete session:', err)
      throw err
    }
  },

  fetchMessages: async (sessionId) => {
    try {
      const messages = await gameStorage.fetchMessages(sessionId)
      set({ messages })
    } catch {
      // ignore
    }
  },

  addMessage: (message) => {
    set((state) => ({ messages: [...state.messages, message] }))
    syncToIdbFireAndForget('message', message)
  },

  setStreaming: (isStreaming) => set({ isStreaming }),

  setStreamStatus: (streamStatus) => set({ streamStatus }),

  appendStreamContent: (content) =>
    set((state) => ({ streamingContent: state.streamingContent + content })),

  clearStreamContent: () => set({ streamingContent: '' }),

  addPendingBlock: (block) =>
    set((state) => ({ pendingBlocks: [...state.pendingBlocks, block] })),

  flushPendingBlocksForTurn: (turnId) =>
    set((state) => {
      const merged = attachPendingBlocksForTurn(
        state.messages,
        state.pendingBlocks,
        turnId,
      )
      if (
        merged.messages === state.messages
        && merged.pendingBlocks === state.pendingBlocks
      ) {
        return state
      }
      return { messages: merged.messages, pendingBlocks: merged.pendingBlocks }
    }),

  clearPendingBlocks: () => set({ pendingBlocks: [] }),

  setPhase: (phase) => set({ phase }),

  setPluginProcessing: (pluginProcessing) => set({ pluginProcessing, ...(pluginProcessing ? {} : { pluginProgress: null }) }),
  setPluginProgress: (pluginProgress) => set({ pluginProgress }),

  setLastPluginSummary: (lastPluginSummary) => set({ lastPluginSummary }),

  setCurrentScene: (currentScene) => set({ currentScene }),

  setScenes: (scenes) => {
    set({ scenes })
    if (scenes.length > 0) {
      scenes.forEach((s) => syncToIdbFireAndForget('scene', s))
    }
  },

  addScene: (scene) => {
    set((state) => ({ scenes: [...state.scenes, scene] }))
    syncToIdbFireAndForget('scene', scene)
  },

  removeLastAssistantMessage: () =>
    set((state) => {
      const msgs = [...state.messages]
      for (let i = msgs.length - 1; i >= 0; i--) {
        if (msgs[i].role === 'assistant') {
          msgs.splice(i, 1)
          return { messages: msgs, pendingBlocks: [] }
        }
      }
      return state
    }),

  deleteMessage: (messageId) =>
    set((state) => ({
      messages: state.messages.filter((m) => m.id !== messageId),
    })),

  deleteMessagesFrom: (messageId) =>
    set((state) => {
      const idx = state.messages.findIndex((m) => m.id === messageId)
      if (idx < 0) return state
      return { messages: state.messages.slice(0, idx), pendingBlocks: [] }
    }),

  setMessageImage: (messageId, image) =>
    set((state) => {
      const existing = state.messageImages[messageId] || []
      return {
        messageImages: {
          ...state.messageImages,
          [messageId]: [...existing, image],
        },
      }
    }),

  setImageLoading: (messageId, loading) =>
    set((state) => {
      const next = new Set(state.imageLoadingMessages)
      if (loading) {
        next.add(messageId)
      } else {
        next.delete(messageId)
      }
      return { imageLoadingMessages: next }
    }),

  clearMessageImages: () => set({ messageImages: {}, imageLoadingMessages: new Set<string>() }),

  hydrateMessageImages: async (sessionId) => {
    try {
      const images = await api.getSessionStoryImages(sessionId)
      const map: Record<string, StoryImageData[]> = {}
      for (const img of images) {
        if (img.message_id) {
          if (!map[img.message_id]) {
            map[img.message_id] = []
          }
          map[img.message_id].push(img)
        }
      }
      set({ messageImages: map })
    } catch {
      // ignore
    }
  },

  updateBlockData: (blockId, data) =>
    set((state) => {
      // Update block in messages (already flushed blocks)
      let found = false
      const nextMessages = state.messages.map((msg) => {
        if (!msg.blocks) return msg
        const updatedBlocks = msg.blocks.map((b) => {
          if (b.block_id === blockId) {
            found = true
            return { ...b, data }
          }
          return b
        })
        return found ? { ...msg, blocks: updatedBlocks } : msg
      })
      if (found) return { messages: nextMessages }

      // Update block in pendingBlocks (not yet flushed)
      const nextPending = state.pendingBlocks.map((b) => {
        if (b.blockId === blockId) {
          found = true
          return { ...b, data }
        }
        return b
      })
      if (found) return { pendingBlocks: nextPending }

      return state
    }),

  updateMessageBlocks: (messageId, blocks) =>
    set((state) => ({
      messages: state.messages.map((msg) =>
        msg.id === messageId ? { ...msg, blocks } : msg,
      ),
    })),
}))
