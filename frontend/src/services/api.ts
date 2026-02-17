import type {
  Project,
  Session,
  Message,
  Plugin,
  Scene,
  GameEvent,
  Character,
  LlmProfile,
  ArchiveVersion,
  WorldTemplate,
  WorldTemplateDetail,
  PresetModel,
  RuntimeSettingField,
} from '../types'

const BASE_URL = '/api'

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
    ...options,
  })
  if (!res.ok) {
    const error = await res.text()
    throw new Error(`API Error ${res.status}: ${error}`)
  }
  return res.json()
}

// Projects
export function getProjects(): Promise<Project[]> {
  return request('/projects')
}

export function createProject(data: { name: string; description?: string; world_doc?: string }): Promise<Project> {
  return request('/projects', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function getProject(id: string): Promise<Project> {
  return request(`/projects/${id}`)
}

export function updateProject(id: string, data: Partial<Project>): Promise<Project> {
  return request(`/projects/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteProject(id: string): Promise<void> {
  return request(`/projects/${id}`, { method: 'DELETE' })
}

// Sessions
export function getSessions(projectId: string): Promise<Session[]> {
  return request(`/projects/${projectId}/sessions`)
}

export function createSession(projectId: string): Promise<Session> {
  return request(`/projects/${projectId}/sessions`, { method: 'POST' })
}

export function deleteSession(sessionId: string): Promise<void> {
  return request(`/sessions/${sessionId}`, { method: 'DELETE' })
}

export function getSessionState(sessionId: string): Promise<{
  world: Record<string, unknown>
  turn_count: number
}> {
  return request(`/sessions/${sessionId}/state`)
}

// Archive Versions
export function getArchiveVersions(sessionId: string): Promise<ArchiveVersion[]> {
  return request(`/sessions/${sessionId}/archives`)
}

export function summarizeArchive(sessionId: string, reason?: string): Promise<ArchiveVersion> {
  return request(`/sessions/${sessionId}/archives/summarize`, {
    method: 'POST',
    body: JSON.stringify({ reason }),
  })
}

export function restoreArchiveVersion(
  sessionId: string,
  version: number,
  mode: 'hard' | 'fork' = 'fork',
): Promise<{
  ok: boolean
  mode: 'hard' | 'fork'
  session_id: string
  new_session_id?: string
  source_session_id?: string
  version: number
  title: string
  summary: string
  phase: string
}> {
  return request(`/sessions/${sessionId}/archives/${version}/restore`, {
    method: 'POST',
    body: JSON.stringify({ mode }),
  })
}

// Messages
export function getMessages(sessionId: string): Promise<Message[]> {
  return request(`/sessions/${sessionId}/messages`)
}

// Plugins
export function getPlugins(): Promise<Plugin[]> {
  return request('/plugins')
}

export function getEnabledPlugins(projectId: string): Promise<{
  plugin_name: string
  enabled: boolean
  required: boolean
  auto_enabled: boolean
  explicitly_disabled: boolean
  dependencies: string[]
  required_by: string[]
}[]> {
  return request(`/plugins/enabled/${projectId}`)
}

export function getPluginBlockConflicts(projectId: string): Promise<{
  block_type: string
  overridden_plugin: string
  winner_plugin: string
}[]> {
  return request(`/plugins/block-conflicts?project_id=${encodeURIComponent(projectId)}`)
}

export function togglePlugin(name: string, projectId: string, enabled: boolean): Promise<{ ok: boolean }> {
  return request(`/plugins/${name}/toggle`, {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId, enabled }),
  })
}

// Scenes
export function getScenes(sessionId: string): Promise<Scene[]> {
  return request(`/sessions/${sessionId}/scenes`)
}

export function getCurrentScene(sessionId: string): Promise<Scene> {
  return request(`/sessions/${sessionId}/scenes/current`)
}

// Events
export function getEvents(sessionId: string, status?: string): Promise<GameEvent[]> {
  const query = status ? `?status=${encodeURIComponent(status)}` : ''
  return request(`/sessions/${sessionId}/events${query}`)
}

// Characters
export function getCharacters(sessionId: string): Promise<Character[]> {
  return request(`/sessions/${sessionId}/characters`)
}

export function updateCharacter(characterId: string, changes: Record<string, unknown>): Promise<Character> {
  return request(`/characters/${characterId}`, {
    method: 'PUT',
    body: JSON.stringify(changes),
  })
}

// LLM Info
export interface LlmInfo {
  model: string
  model_name: string
  provider: string
  api_base: string | null
  has_key: boolean
  source: 'project' | 'profile' | 'env' | 'default'
}

export function getLlmInfo(projectId?: string): Promise<LlmInfo> {
  const query = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
  return request(`/llm/info${query}`)
}

// LLM Profiles
export function getLlmProfiles(): Promise<LlmProfile[]> {
  return request('/llm/profiles')
}

export function getPresetModels(): Promise<PresetModel[]> {
  return request('/llm/preset-models')
}

export function createLlmProfile(data: { name: string; model: string; api_key?: string; api_base?: string }): Promise<LlmProfile> {
  return request('/llm/profiles', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

export function updateLlmProfile(
  id: string,
  data: { name?: string; model?: string; api_key?: string; api_base?: string },
): Promise<LlmProfile> {
  return request(`/llm/profiles/${id}`, {
    method: 'PUT',
    body: JSON.stringify(data),
  })
}

export function deleteLlmProfile(id: string): Promise<void> {
  return request(`/llm/profiles/${id}`, { method: 'DELETE' })
}

export function applyLlmProfile(profileId: string, projectId: string): Promise<{ ok: boolean }> {
  return request(`/llm/profiles/${profileId}/apply`, {
    method: 'POST',
    body: JSON.stringify({ project_id: projectId }),
  })
}

// World Templates
export function getWorldTemplates(): Promise<WorldTemplate[]> {
  return request('/templates/worlds')
}

export function getWorldTemplate(slug: string): Promise<WorldTemplateDetail> {
  return request(`/templates/worlds/${slug}`)
}

export function generateWorld(data: {
  genre: string
  setting?: string
  tone?: string
  language?: string
  extra_notes?: string
}): Promise<{ world_doc: string }> {
  return request('/templates/worlds/generate', {
    method: 'POST',
    body: JSON.stringify(data),
  })
}

// Runtime settings
export interface RuntimeSettingsSchemaResponse {
  fields: RuntimeSettingField[]
  by_plugin: Record<string, string[]>
  enabled_plugins: string[]
}

export interface RuntimeSettingsValuesResponse {
  values: Record<string, unknown>
  by_plugin: Record<string, Record<string, unknown>>
  project_overrides: Record<string, unknown>
  session_overrides: Record<string, unknown>
}

export function getRuntimeSettingsSchema(projectId: string): Promise<RuntimeSettingsSchemaResponse> {
  return request(`/runtime-settings/schema?project_id=${encodeURIComponent(projectId)}`)
}

export function getRuntimeSettings(projectId: string, sessionId?: string): Promise<RuntimeSettingsValuesResponse> {
  const params = new URLSearchParams({ project_id: projectId })
  if (sessionId) params.set('session_id', sessionId)
  return request(`/runtime-settings?${params.toString()}`)
}

export function patchRuntimeSettings(data: {
  project_id: string
  session_id?: string
  scope: 'project' | 'session'
  values: Record<string, unknown>
}): Promise<RuntimeSettingsValuesResponse & { ok: boolean }> {
  return request('/runtime-settings', {
    method: 'PATCH',
    body: JSON.stringify(data),
  })
}
