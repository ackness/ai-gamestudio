export interface BrowserLlmConfig {
  model?: string
  apiKey?: string
  apiBase?: string
  imageModel?: string
  imageApiKey?: string
  imageApiBase?: string
}

export interface LlmOverridePayload {
  model?: string
  api_key?: string
  api_base?: string
}

export interface ImageOverridePayload {
  model?: string
  api_key?: string
  api_base?: string
}

const GLOBAL_KEY = 'ai-gamestudio:llm-config:global'
const PROJECT_KEY_PREFIX = 'ai-gamestudio:llm-config:project:'

function getStorage(): Storage | null {
  if (typeof window === 'undefined') return null
  try {
    return window.localStorage
  } catch {
    return null
  }
}

function normalize(value: unknown): string | undefined {
  if (typeof value !== 'string') return undefined
  const trimmed = value.trim()
  return trimmed ? trimmed : undefined
}

function normalizeConfig(raw: Partial<BrowserLlmConfig>): BrowserLlmConfig {
  return {
    model: normalize(raw.model),
    apiKey: normalize(raw.apiKey),
    apiBase: normalize(raw.apiBase),
    imageModel: normalize(raw.imageModel),
    imageApiKey: normalize(raw.imageApiKey),
    imageApiBase: normalize(raw.imageApiBase),
  }
}

function projectKey(projectId: string): string {
  return `${PROJECT_KEY_PREFIX}${projectId}`
}

function readConfig(key: string): BrowserLlmConfig {
  const storage = getStorage()
  if (!storage) return {}
  const raw = storage.getItem(key)
  if (!raw) return {}
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {}
    return normalizeConfig(parsed as Partial<BrowserLlmConfig>)
  } catch {
    return {}
  }
}

function writeConfig(key: string, cfg: BrowserLlmConfig) {
  const storage = getStorage()
  if (!storage) return
  const normalized = normalizeConfig(cfg)
  const hasAnyValue = Object.values(normalized).some((item) => !!item)
  if (!hasAnyValue) {
    storage.removeItem(key)
    return
  }
  storage.setItem(key, JSON.stringify(normalized))
}

export function getBrowserLlmConfig(projectId?: string | null): BrowserLlmConfig {
  const global = readConfig(GLOBAL_KEY)
  if (!projectId) return global
  const project = readConfig(projectKey(projectId))
  return {
    ...global,
    ...project,
  }
}

export function saveBrowserLlmConfig(projectId: string, cfg: Partial<BrowserLlmConfig>): void {
  writeConfig(projectKey(projectId), normalizeConfig(cfg))
}

export function clearBrowserLlmConfig(projectId: string): void {
  const storage = getStorage()
  if (!storage) return
  storage.removeItem(projectKey(projectId))
}

export function buildBrowserLlmHeaders(projectId?: string | null): Record<string, string> {
  const cfg = getBrowserLlmConfig(projectId)
  const headers: Record<string, string> = {}
  if (cfg.model) headers['X-LLM-Model'] = cfg.model
  if (cfg.apiKey) headers['X-LLM-Api-Key'] = cfg.apiKey
  if (cfg.apiBase) headers['X-LLM-Api-Base'] = cfg.apiBase
  return headers
}

export function buildBrowserLlmOverrides(projectId?: string | null): LlmOverridePayload | undefined {
  const cfg = getBrowserLlmConfig(projectId)
  const overrides: LlmOverridePayload = {}
  if (cfg.model) overrides.model = cfg.model
  if (cfg.apiKey) overrides.api_key = cfg.apiKey
  if (cfg.apiBase) overrides.api_base = cfg.apiBase
  if (!overrides.model && !overrides.api_key && !overrides.api_base) {
    return undefined
  }
  return overrides
}

export function buildBrowserImageOverrides(projectId?: string | null): ImageOverridePayload | undefined {
  const cfg = getBrowserLlmConfig(projectId)
  const overrides: ImageOverridePayload = {}
  if (cfg.imageModel) overrides.model = cfg.imageModel
  if (cfg.imageApiKey) overrides.api_key = cfg.imageApiKey
  if (cfg.imageApiBase) overrides.api_base = cfg.imageApiBase
  if (!overrides.model && !overrides.api_key && !overrides.api_base) {
    return undefined
  }
  return overrides
}
