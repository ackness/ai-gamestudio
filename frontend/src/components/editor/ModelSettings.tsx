import { useState, useEffect, useCallback } from 'react'
import type { PresetModel } from '../../types'
import { useProjectStore } from '../../stores/projectStore'
import { useUiStore } from '../../stores/uiStore'
import * as api from '../../services/api'
import type { LlmInfo } from '../../services/api'
import {
  getBrowserLlmConfig,
  saveBrowserLlmConfig,
  clearBrowserLlmConfig,
} from '../../utils/browserLlmConfig'

const T = {
  zh: {
    effectiveLabel: '当前生效',
    sourceEnv: '服务器环境变量',
    sourceProject: '项目配置',
    sourceBrowser: '浏览器本地',
    sourceDefault: '系统默认',
    keySet: 'API Key 已配置',
    keyServer: '服务器已配置',
    keyNotSet: '未配置',
    cloudProviders: '云端服务',
    localProviders: '本地兼容',
    customSection: '自定义（OpenAI 兼容）',
    customNote: '任何兼容 OpenAI 格式的服务均可使用：填写 API Base URL，模型名用 openai/<model-name> 格式。',
    model: '模型',
    modelPlaceholder: '例：deepseek/deepseek-chat',
    apiKey: 'API Key',
    apiKeyPlaceholder: '输入 API Key',
    apiKeyNote: '仅存储在你的浏览器中，不会上传到服务器',
    apiBase: 'API Base URL（可选）',
    apiBasePlaceholder: '例：https://api.deepseek.com',
    imageSection: '图片生成（可选）',
    imageModel: '图片模型',
    imageApiKey: '图片 API Key',
    imageApiBase: '图片 API Base',
    save: '保存',
    saving: '保存中…',
    saved: '已保存 ✓',
    reset: '清除项目配置，恢复服务器默认',
  },
  en: {
    effectiveLabel: 'Effective',
    sourceEnv: 'Server .env',
    sourceProject: 'Project',
    sourceBrowser: 'Browser (local)',
    sourceDefault: 'Default',
    keySet: 'API Key set',
    keyServer: 'Set on server',
    keyNotSet: 'Not set',
    cloudProviders: 'Cloud',
    localProviders: 'Local (OpenAI-compat)',
    customSection: 'Custom (OpenAI-compatible)',
    customNote: 'Any OpenAI-compatible service works: set API Base URL and use openai/<model-name> as the model.',
    model: 'Model',
    modelPlaceholder: 'e.g. deepseek/deepseek-chat',
    apiKey: 'API Key',
    apiKeyPlaceholder: 'Enter API Key',
    apiKeyNote: 'Stored in your browser only — never uploaded to the server',
    apiBase: 'API Base URL (optional)',
    apiBasePlaceholder: 'e.g. https://api.deepseek.com',
    imageSection: 'Image Generation (optional)',
    imageModel: 'Image Model',
    imageApiKey: 'Image API Key',
    imageApiBase: 'Image API Base',
    save: 'Save',
    saving: 'Saving…',
    saved: 'Saved ✓',
    reset: 'Clear project config, revert to server default',
  },
}

// OpenAI-compatible local service presets
const LOCAL_PRESETS = [
  { id: 'ollama', name: 'Ollama', model: 'openai/llama3.2', apiBase: 'http://localhost:11434/v1', apiKey: 'ollama' },
  { id: 'lmstudio', name: 'LM Studio', model: 'openai/local-model', apiBase: 'http://localhost:1234/v1', apiKey: 'lm-studio' },
  { id: 'openai-compat', name: 'Custom', model: 'openai/', apiBase: '', apiKey: '' },
]

// Friendly provider display names
const PROVIDER_NAMES: Record<string, string> = {
  deepseek: 'DeepSeek',
  openai: 'OpenAI',
  openrouter: 'OpenRouter',
  anthropic: 'Anthropic',
  gemini: 'Gemini',
  google: 'Google',
}

interface Props {
  onLlmInfoChange?: (info: LlmInfo | null) => void
}

export function ModelSettings({ onLlmInfoChange }: Props) {
  const { currentProject, updateProject } = useProjectStore()
  const { language } = useUiStore()
  const t = T[language === 'zh' ? 'zh' : 'en']

  const [llmInfo, setLlmInfo] = useState<LlmInfo | null>(null)
  const [presets, setPresets] = useState<PresetModel[]>([])
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [imageModel, setImageModel] = useState('')
  const [imageApiKey, setImageApiKey] = useState('')
  const [imageApiBase, setImageApiBase] = useState('')
  const [showImage, setShowImage] = useState(false)
  const [saving, setSaving] = useState(false)
  const [savedMsg, setSavedMsg] = useState(false)

  const loadLlmInfo = useCallback(() => {
    api
      .getLlmInfo(currentProject?.id)
      .then((info) => {
        setLlmInfo(info)
        onLlmInfoChange?.(info)
      })
      .catch(() => {})
  }, [currentProject?.id, onLlmInfoChange])

  useEffect(() => {
    loadLlmInfo()
    api.getPresetModels().then(setPresets).catch(() => {})
  }, [loadLlmInfo])

  useEffect(() => {
    if (!currentProject) return
    const local = getBrowserLlmConfig(currentProject.id)
    setModel(local.model || currentProject.llm_model || '')
    setApiKey(local.apiKey || '')
    setApiBase(local.apiBase || currentProject.llm_api_base || '')
    setImageModel(local.imageModel || currentProject.image_model || '')
    setImageApiKey(local.imageApiKey || '')
    setImageApiBase(local.imageApiBase || currentProject.image_api_base || '')
  }, [currentProject?.id]) // eslint-disable-line react-hooks/exhaustive-deps

  // Determine where the current config comes from
  const configSource = (): string => {
    const local = currentProject ? getBrowserLlmConfig(currentProject.id) : {}
    if (local.apiKey || local.model) return t.sourceBrowser
    if (currentProject?.llm_model || currentProject?.has_llm_api_key) return t.sourceProject
    if (llmInfo?.source === 'env') return t.sourceEnv
    return t.sourceDefault
  }

  const apiKeyStatus = (): { label: string; ok: boolean } => {
    const local = currentProject ? getBrowserLlmConfig(currentProject.id) : {}
    if (local.apiKey) return { label: `${t.keySet} (${t.sourceBrowser})`, ok: true }
    if (llmInfo?.has_key) return { label: t.keyServer, ok: true }
    return { label: t.keyNotSet, ok: false }
  }

  // Group presets by provider
  const presetGroups = presets.reduce<Record<string, PresetModel[]>>((acc, p) => {
    const key = p.provider || 'other'
    ;(acc[key] ??= []).push(p)
    return acc
  }, {})

  const handlePresetClick = (preset: PresetModel) => {
    setModel(preset.model)
    setApiBase(preset.api_base || '')
    setApiKey('')
  }

  const handleSave = async () => {
    if (!currentProject) return
    setSaving(true)
    try {
      saveBrowserLlmConfig(currentProject.id, {
        model: model || undefined,
        apiKey: apiKey || undefined,
        apiBase: apiBase || undefined,
        imageModel: imageModel || undefined,
        imageApiKey: imageApiKey || undefined,
        imageApiBase: imageApiBase || undefined,
      })
      await updateProject({
        llm_model: model || undefined,
        llm_api_key: '',
        llm_api_base: apiBase || undefined,
        image_model: imageModel || undefined,
        image_api_key: '',
        image_api_base: imageApiBase || undefined,
      })
      loadLlmInfo()
      setSavedMsg(true)
      setTimeout(() => setSavedMsg(false), 2500)
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!currentProject) return
    setSaving(true)
    try {
      clearBrowserLlmConfig(currentProject.id)
      await updateProject({
        llm_model: undefined,
        llm_api_key: '',
        llm_api_base: undefined,
        image_model: undefined,
        image_api_key: '',
        image_api_base: undefined,
      })
      setModel('')
      setApiKey('')
      setApiBase('')
      setImageModel('')
      setImageApiKey('')
      setImageApiBase('')
      loadLlmInfo()
    } finally {
      setSaving(false)
    }
  }

  const keyStatus = apiKeyStatus()

  return (
    <div className="flex flex-col h-full overflow-hidden text-sm">
      <div className="flex-1 overflow-y-auto p-4 space-y-5">

        {/* Current effective config banner */}
        <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">{t.effectiveLabel}</span>
            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-700 text-slate-400">
              {configSource()}
            </span>
          </div>
          <div className="font-mono text-emerald-400 text-sm truncate">
            {llmInfo?.model || '—'}
          </div>
          <div className="flex items-center gap-1.5 text-xs">
            <span
              className={`w-1.5 h-1.5 rounded-full shrink-0 ${keyStatus.ok ? 'bg-emerald-500' : 'bg-slate-600'}`}
            />
            <span className={keyStatus.ok ? 'text-slate-400' : 'text-slate-600'}>
              {keyStatus.label}
            </span>
          </div>
        </div>

        {/* Quick preset buttons — cloud providers */}
        {Object.keys(presetGroups).length > 0 && (
          <div>
            <div className="text-xs text-slate-500 mb-2">{t.cloudProviders}</div>
            <div className="space-y-2">
              {Object.entries(presetGroups).map(([provider, items]) => (
                <div key={provider}>
                  <div className="text-[10px] text-slate-600 uppercase tracking-wider mb-1">
                    {PROVIDER_NAMES[provider] ?? provider}
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {items.map((p) => (
                      <button
                        key={p.id}
                        onClick={() => handlePresetClick(p)}
                        className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                          model === p.model
                            ? 'bg-emerald-700/30 border-emerald-600 text-emerald-300'
                            : 'bg-slate-700/40 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'
                        }`}
                      >
                        {p.name}
                      </button>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Local / OpenAI-compatible presets */}
        <div>
          <div className="text-xs text-slate-500 mb-2">{t.localProviders}</div>
          <div className="flex flex-wrap gap-1.5 mb-2">
            {LOCAL_PRESETS.map((p) => (
              <button
                key={p.id}
                onClick={() => {
                  setModel(p.model)
                  setApiBase(p.apiBase)
                  setApiKey(p.apiKey)
                }}
                className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                  apiBase === p.apiBase && p.apiBase
                    ? 'bg-violet-700/30 border-violet-600 text-violet-300'
                    : 'bg-slate-700/40 border-slate-600 text-slate-300 hover:bg-slate-700 hover:border-slate-500'
                }`}
              >
                {p.name}
              </button>
            ))}
          </div>
          <p className="text-[11px] text-slate-600">{t.customNote}</p>
        </div>

        {/* Model */}
        <div>
          <label className="text-xs text-slate-400 block mb-1.5">{t.model}</label>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={llmInfo?.model || t.modelPlaceholder}
            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
          />
        </div>

        {/* API Key */}
        <div>
          <label className="text-xs text-slate-400 block mb-1.5">{t.apiKey}</label>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llmInfo?.has_key ? `(${t.keyServer})` : t.apiKeyPlaceholder}
            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
          />
          <p className="text-[11px] text-slate-600 mt-1">{t.apiKeyNote}</p>
        </div>

        {/* API Base */}
        <div>
          <label className="text-xs text-slate-400 block mb-1.5">{t.apiBase}</label>
          <input
            type="text"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder={llmInfo?.api_base || t.apiBasePlaceholder}
            className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
          />
        </div>

        {/* Image generation — collapsible */}
        <div>
          <button
            onClick={() => setShowImage(!showImage)}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-400 transition-colors"
          >
            <span className="text-[10px]">{showImage ? '▾' : '▸'}</span>
            {t.imageSection}
          </button>
          {showImage && (
            <div className="mt-3 space-y-3 pl-1 border-l border-slate-700">
              <div>
                <label className="text-xs text-slate-400 block mb-1.5">{t.imageModel}</label>
                <input
                  type="text"
                  value={imageModel}
                  onChange={(e) => setImageModel(e.target.value)}
                  placeholder={currentProject?.image_model || 'gemini-2.5-flash-image-preview'}
                  className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1.5">{t.imageApiKey}</label>
                <input
                  type="password"
                  value={imageApiKey}
                  onChange={(e) => setImageApiKey(e.target.value)}
                  placeholder={currentProject?.has_image_api_key ? '(set)' : t.apiKeyPlaceholder}
                  className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                />
              </div>
              <div>
                <label className="text-xs text-slate-400 block mb-1.5">{t.imageApiBase}</label>
                <input
                  type="text"
                  value={imageApiBase}
                  onChange={(e) => setImageApiBase(e.target.value)}
                  placeholder={currentProject?.image_api_base || 'https://...'}
                  className="w-full bg-slate-800 border border-slate-600 rounded px-3 py-2 text-slate-100 placeholder-slate-600 focus:outline-none focus:border-emerald-500 text-sm"
                />
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Footer */}
      <div className="border-t border-slate-700 p-4 space-y-2 shrink-0">
        <button
          onClick={handleSave}
          disabled={saving}
          className="w-full py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white rounded text-sm font-medium transition-colors"
        >
          {savedMsg ? t.saved : saving ? t.saving : t.save}
        </button>
        <button
          onClick={handleReset}
          disabled={saving}
          className="w-full py-1.5 text-xs text-slate-600 hover:text-slate-400 hover:bg-slate-800 rounded transition-colors"
        >
          {t.reset}
        </button>
      </div>
    </div>
  )
}
