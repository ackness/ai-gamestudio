import { useState, useEffect, useRef } from 'react'
import type { LlmProfile, PresetModel } from '../../types'
import { useProjectStore } from '../../stores/projectStore'
import * as api from '../../services/api'
import type { LlmInfo } from '../../services/api'
import {
  clearBrowserLlmConfig,
  getBrowserLlmConfig,
  saveBrowserLlmConfig,
} from '../../utils/browserLlmConfig'

interface Props {
  llmInfo: LlmInfo | null
  onClose: () => void
  onSaved: () => void
}

export function ModelConfigPanel({ llmInfo, onClose, onSaved }: Props) {
  const { currentProject, updateProject } = useProjectStore()
  const panelRef = useRef<HTMLDivElement>(null)

  const [profiles, setProfiles] = useState<LlmProfile[]>([])
  const [presetModels, setPresetModels] = useState<PresetModel[]>([])
  const [selectedProfileId, setSelectedProfileId] = useState<string>('')
  const [selectedPresetId, setSelectedPresetId] = useState<string>('')
  const [model, setModel] = useState('')
  const [apiKey, setApiKey] = useState('')
  const [apiBase, setApiBase] = useState('')
  const [imageModel, setImageModel] = useState('')
  const [imageApiKey, setImageApiKey] = useState('')
  const [imageApiBase, setImageApiBase] = useState('')
  const [saving, setSaving] = useState(false)
  const [saveProfileName, setSaveProfileName] = useState('')
  const [showSaveProfile, setShowSaveProfile] = useState(false)
  const browserConfig = currentProject ? getBrowserLlmConfig(currentProject.id) : {}

  // Load profiles and preset models on mount
  useEffect(() => {
    api.getLlmProfiles().then((loadedProfiles) => {
      setProfiles(loadedProfiles)
      // Auto-match profile if current project config matches a profile
      if (currentProject) {
        const projectModel = currentProject.llm_model || ''
        const projectApiBase = currentProject.llm_api_base || ''
        
        const matchedProfile = loadedProfiles.find((p) => {
          // Match by model name
          if (p.model !== projectModel) return false
          // If profile has api_base, project should match (or both empty)
          const profileApiBase = p.api_base || ''
          if (profileApiBase && profileApiBase !== projectApiBase) return false
          return true
        })
        
        if (matchedProfile) {
          setSelectedProfileId(matchedProfile.id)
        }
      }
    }).catch(() => {})
    api.getPresetModels().then(setPresetModels).catch(() => {})
  }, [currentProject])

  // Initialize fields from current project
  useEffect(() => {
    if (currentProject) {
      const local = getBrowserLlmConfig(currentProject.id)
      setModel(local.model || currentProject.llm_model || '')
      setApiKey(local.apiKey || '')
      setApiBase(local.apiBase || currentProject.llm_api_base || '')
      setImageModel(local.imageModel || currentProject.image_model || '')
      setImageApiKey(local.imageApiKey || '')
      setImageApiBase(local.imageApiBase || currentProject.image_api_base || '')
    }
  }, [currentProject])

  // Close on click outside
  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        onClose()
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [onClose])

  const handleProfileSelect = async (profileId: string) => {
    setSelectedProfileId(profileId)
    setSelectedPresetId('') // Clear preset selection when profile is selected
    
    if (profileId === '') {
      // Reset to project values or empty
      const local = currentProject ? getBrowserLlmConfig(currentProject.id) : {}
      setModel(local.model || currentProject?.llm_model || '')
      setApiKey(local.apiKey || '')
      setApiBase(local.apiBase || currentProject?.llm_api_base || '')
      return
    }
    
    const profile = profiles.find((p) => p.id === profileId)
    if (!profile || !currentProject) return
    
    // Auto-apply profile to project immediately (API key is browser-local by default)
    setSaving(true)
    try {
      await updateProject({
        llm_model: profile.model || undefined,
        llm_api_key: '',
        llm_api_base: profile.api_base || undefined,
      })
      saveBrowserLlmConfig(currentProject.id, {
        model: profile.model,
        apiBase: profile.api_base || undefined,
      })
      // Update local state to reflect applied profile
      setModel(profile.model)
      setApiKey(getBrowserLlmConfig(currentProject.id).apiKey || '')
      setApiBase(profile.api_base || '')
      onSaved() // Refresh parent component
    } catch {
      // Error handling - revert selection
      setSelectedProfileId('')
    } finally {
      setSaving(false)
    }
  }

  const handlePresetSelect = async (presetId: string) => {
    setSelectedPresetId(presetId)
    setSelectedProfileId('') // Clear profile selection when preset is selected
    
    if (presetId === '') {
      // Reset to project values or empty
      const local = currentProject ? getBrowserLlmConfig(currentProject.id) : {}
      setModel(local.model || currentProject?.llm_model || '')
      setApiKey(local.apiKey || '')
      setApiBase(local.apiBase || currentProject?.llm_api_base || '')
      return
    }
    
    const preset = presetModels.find((p) => p.id === presetId)
    if (!preset || !currentProject) return
    
    // Auto-apply preset to project immediately
    setSaving(true)
    try {
      let newModel = preset.model
      let newApiBase = preset.api_base
      
      // Special handling for openrouter-custom
      if (presetId === 'openrouter-custom') {
        newModel = '' // Leave empty for user to input
        newApiBase = 'https://openrouter.ai/api/v1'
      }
      
      await updateProject({
        llm_model: newModel || undefined,
        llm_api_key: '',
        llm_api_base: newApiBase || undefined,
      })
      saveBrowserLlmConfig(currentProject.id, {
        model: newModel || undefined,
        apiKey: undefined,
        apiBase: newApiBase || undefined,
      })
      
      setModel(newModel)
      setApiKey('') // Clear API key - user must enter their own
      setApiBase(newApiBase)
      onSaved() // Refresh parent component
    } catch {
      setSelectedPresetId('')
    } finally {
      setSaving(false)
    }
  }

  const handleSaveToProject = async () => {
    if (!currentProject) return
    setSaving(true)
    try {
      saveBrowserLlmConfig(currentProject.id, {
        model,
        apiKey,
        apiBase,
        imageModel,
        imageApiKey,
        imageApiBase,
      })
      await updateProject({
        llm_model: model || undefined,
        llm_api_key: '',
        llm_api_base: apiBase || undefined,
        image_model: imageModel || undefined,
        image_api_key: '',
        image_api_base: imageApiBase || undefined,
      })
      onSaved()
    } catch {
      // error is visible via UI state
    } finally {
      setSaving(false)
    }
  }

  const handleSaveAsProfile = async () => {
    if (!saveProfileName.trim() || !model.trim()) return
    setSaving(true)
    try {
      const newProfile = await api.createLlmProfile({
        name: saveProfileName.trim(),
        model: model.trim(),
        // API key stays in browser storage by default.
        api_key: undefined,
        api_base: apiBase || undefined,
      })
      setProfiles((prev) => [newProfile, ...prev])
      setSelectedProfileId(newProfile.id)
      setShowSaveProfile(false)
      setSaveProfileName('')
    } catch {
      // ignore
    } finally {
      setSaving(false)
    }
  }

  const handleDeleteProfile = async (profileId: string) => {
    try {
      await api.deleteLlmProfile(profileId)
      setProfiles((prev) => prev.filter((p) => p.id !== profileId))
      if (selectedProfileId === profileId) {
        setSelectedProfileId('')
      }
    } catch {
      // ignore
    }
  }

  const handleClearProjectConfig = async () => {
    if (!currentProject) return
    setSaving(true)
    try {
      await updateProject({
        llm_model: undefined,
        llm_api_key: '',
        llm_api_base: undefined,
        image_model: undefined,
        image_api_key: '',
        image_api_base: undefined,
      })
      clearBrowserLlmConfig(currentProject.id)
      setModel('')
      setApiKey('')
      setApiBase('')
      setImageModel('')
      setImageApiKey('')
      setImageApiBase('')
      setSelectedProfileId('')
      onSaved()
    } finally {
      setSaving(false)
    }
  }

  // Determine source for each field
  const getSource = (field: 'model' | 'api_key' | 'api_base') => {
    const browserVal = field === 'model' ? browserConfig.model :
                       field === 'api_key' ? browserConfig.apiKey :
                       browserConfig.apiBase
    if (browserVal) return 'browser'
    const projectVal = field === 'model' ? currentProject?.llm_model :
                       field === 'api_key' ? (currentProject?.has_llm_api_key ? '***' : null) :
                       currentProject?.llm_api_base
    if (projectVal) return 'project'
    const envVal = field === 'model' ? llmInfo?.model :
                   field === 'api_key' ? (llmInfo?.has_key ? '***' : null) :
                   llmInfo?.api_base
    if (envVal) return 'env'
    return 'none'
  }

  const sourceLabel = (field: 'model' | 'api_key' | 'api_base') => {
    const src = getSource(field)
    if (src === 'browser') return 'browser'
    if (src === 'project') return 'project'
    if (src === 'env') return '.env'
    return ''
  }

  return (
    <div
      ref={panelRef}
      className="absolute top-full left-0 mt-1 w-80 bg-popover border rounded-lg shadow-xl z-50 overflow-hidden"
    >
      <div className="p-3 border-b flex items-center justify-between">
        <span className="text-sm font-medium">Model Configuration</span>
        <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">&times;</button>
      </div>

      <div className="p-3 space-y-3 max-h-96 overflow-y-auto">
        {/* Preset Model selector */}
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Model Preset</label>
          <select
            value={selectedPresetId}
            onChange={(e) => handlePresetSelect(e.target.value)}
            className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            <option value="">-- Select a preset --</option>
            <optgroup label="DeepSeek">
              {presetModels
                .filter((p) => p.provider === 'deepseek')
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </optgroup>
            <optgroup label="OpenRouter">
              {presetModels
                .filter((p) => p.provider === 'openrouter')
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </optgroup>
            <option value="custom">Custom...</option>
          </select>
        </div>

        {/* Profile selector */}
        <div>
          <label className="text-xs text-muted-foreground block mb-1">Saved Profile</label>
          <div className="flex gap-1">
            <select
              value={selectedProfileId}
              onChange={(e) => handleProfileSelect(e.target.value)}
              className="flex-1 bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="">-- Use global default --</option>
              {profiles.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name} ({p.model})
                </option>
              ))}
            </select>
            {selectedProfileId && (
              <button
                onClick={() => handleDeleteProfile(selectedProfileId)}
                className="px-2 py-1 text-xs text-destructive hover:text-destructive/80 hover:bg-muted rounded"
                title="Delete preset"
              >
                Del
              </button>
            )}
          </div>
        </div>

        {/* Model */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="text-xs text-muted-foreground">Model</label>
            {sourceLabel('model') && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {sourceLabel('model')}
              </span>
            )}
          </div>
          <input
            type="text"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder={llmInfo?.model || 'gpt-4o-mini'}
            className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* API Key */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="text-xs text-muted-foreground">API Key</label>
            {sourceLabel('api_key') && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {sourceLabel('api_key')}
              </span>
            )}
          </div>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder={llmInfo?.has_key ? '(set in .env)' : 'sk-...'}
            className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* API Base */}
        <div>
          <div className="flex items-center gap-2 mb-1">
            <label className="text-xs text-muted-foreground">API Base</label>
            {sourceLabel('api_base') && (
              <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">
                {sourceLabel('api_base')}
              </span>
            )}
          </div>
          <input
            type="text"
            value={apiBase}
            onChange={(e) => setApiBase(e.target.value)}
            placeholder={llmInfo?.api_base || 'https://api.openai.com/v1'}
            className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          />
        </div>

        {/* Actions */}
        <div className="pt-1 border-t" />

        {/* Image generation config */}
        <div className="space-y-2">
          <div className="text-xs text-muted-foreground">Image Generation</div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Image Model</label>
            <input
              type="text"
              value={imageModel}
              onChange={(e) => setImageModel(e.target.value)}
              placeholder={currentProject?.image_model || 'gemini-2.5-flash-image-preview'}
              className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Image API Key</label>
            <input
              type="password"
              value={imageApiKey}
              onChange={(e) => setImageApiKey(e.target.value)}
              placeholder={
                browserConfig.imageApiKey
                  ? '(set in browser)'
                  : currentProject?.has_image_api_key
                    ? '(set in project/.env)'
                    : 'sk-...'
              }
              className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>

          <div>
            <label className="text-xs text-muted-foreground block mb-1">Image API Base</label>
            <input
              type="text"
              value={imageApiBase}
              onChange={(e) => setImageApiBase(e.target.value)}
              placeholder={currentProject?.image_api_base || 'https://api.whatai.cc/v1/chat/completions'}
              className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            />
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-1">
          <button
            onClick={handleSaveToProject}
            disabled={saving}
            className="flex-1 px-3 py-1.5 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded text-xs font-medium transition-colors"
          >
            {saving ? 'Saving...' : 'Save to Project'}
          </button>
          <button
            onClick={() => setShowSaveProfile(true)}
            disabled={!model.trim()}
            className="px-3 py-1.5 bg-secondary text-secondary-foreground hover:bg-secondary/80 disabled:opacity-50 rounded text-xs font-medium transition-colors"
          >
            Save as Preset
          </button>
        </div>

        {/* Save as profile form */}
        {showSaveProfile && (
          <div className="border rounded p-2 space-y-2">
            <input
              type="text"
              value={saveProfileName}
              onChange={(e) => setSaveProfileName(e.target.value)}
              placeholder="Preset name, e.g. GPT-4o"
              className="w-full bg-background border border-input rounded px-2 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
              autoFocus
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSaveAsProfile()
                if (e.key === 'Escape') setShowSaveProfile(false)
              }}
            />
            <div className="flex gap-2">
              <button
                onClick={handleSaveAsProfile}
                disabled={saving || !saveProfileName.trim()}
                className="flex-1 px-2 py-1 bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 rounded text-xs transition-colors"
              >
                Confirm
              </button>
              <button
                onClick={() => setShowSaveProfile(false)}
                className="px-2 py-1 bg-muted hover:bg-muted/80 text-foreground rounded text-xs transition-colors"
              >
                Cancel
              </button>
            </div>
          </div>
        )}

        {/* Reset to default */}
        {(currentProject?.llm_model || currentProject?.has_llm_api_key || currentProject?.llm_api_base) && (
          <button
            onClick={handleClearProjectConfig}
            disabled={saving}
            className="w-full px-3 py-1.5 border hover:bg-muted text-muted-foreground hover:text-foreground rounded text-xs transition-colors"
          >
            Reset to Global Default
          </button>
        )}
      </div>
    </div>
  )
}
