import { useCallback, useEffect, useMemo, useState } from 'react'
import type { RuntimeSettingField } from '../../types'
import { useProjectStore } from '../../stores/projectStore'
import { useSessionStore } from '../../stores/sessionStore'
import * as api from '../../services/api'

type Scope = 'project' | 'session'

function normalizeValueForField(field: RuntimeSettingField, raw: unknown): unknown {
  if (raw === null || raw === undefined) return null
  if (field.type === 'boolean') return Boolean(raw)
  if (field.type === 'integer') {
    if (typeof raw === 'number') return Number.isFinite(raw) ? Math.round(raw) : null
    if (typeof raw === 'string') {
      const trimmed = raw.trim()
      if (!trimmed) return null
      const parsed = Number.parseInt(trimmed, 10)
      return Number.isFinite(parsed) ? parsed : null
    }
    return null
  }
  if (field.type === 'number') {
    if (typeof raw === 'number') return Number.isFinite(raw) ? raw : null
    if (typeof raw === 'string') {
      const trimmed = raw.trim()
      if (!trimmed) return null
      const parsed = Number(trimmed)
      return Number.isFinite(parsed) ? parsed : null
    }
    return null
  }
  if (field.type === 'enum') return String(raw)
  return String(raw)
}

function displayValue(field: RuntimeSettingField, value: unknown): string {
  if (value === null || value === undefined) return ''
  if (field.type === 'boolean') return value ? 'true' : 'false'
  return String(value)
}

export function RuntimeSettingsPanel() {
  const currentProject = useProjectStore((s) => s.currentProject)
  const currentSession = useSessionStore((s) => s.currentSession)
  const [scope, setScope] = useState<Scope>('project')
  const [loading, setLoading] = useState(false)
  const [fields, setFields] = useState<RuntimeSettingField[]>([])
  const [values, setValues] = useState<Record<string, unknown>>({})
  const [projectOverrides, setProjectOverrides] = useState<Record<string, unknown>>({})
  const [sessionOverrides, setSessionOverrides] = useState<Record<string, unknown>>({})
  const [savingKey, setSavingKey] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const refresh = useCallback(async () => {
    if (!currentProject?.id) {
      setFields([])
      setValues({})
      setProjectOverrides({})
      setSessionOverrides({})
      return
    }
    setLoading(true)
    setError(null)
    try {
      const [schemaRes, valuesRes] = await Promise.all([
        api.getRuntimeSettingsSchema(currentProject.id),
        api.getRuntimeSettings(currentProject.id, currentSession?.id),
      ])
      setFields(schemaRes.fields || [])
      setValues(valuesRes.values || {})
      setProjectOverrides(valuesRes.project_overrides || {})
      setSessionOverrides(valuesRes.session_overrides || {})
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load runtime settings')
      setFields([])
      setValues({})
    } finally {
      setLoading(false)
    }
  }, [currentProject?.id, currentSession?.id])

  useEffect(() => {
    refresh()
  }, [refresh])

  useEffect(() => {
    if (!currentSession && scope === 'session') {
      setScope('project')
    }
  }, [currentSession, scope])

  const fieldsByPlugin = useMemo(() => {
    const grouped: Record<string, RuntimeSettingField[]> = {}
    for (const field of fields) {
      if (!grouped[field.plugin_name]) grouped[field.plugin_name] = []
      grouped[field.plugin_name].push(field)
    }
    for (const key of Object.keys(grouped)) {
      grouped[key].sort((a, b) => {
        const ao = Number(a.order || 0)
        const bo = Number(b.order || 0)
        if (ao !== bo) return ao - bo
        return a.key.localeCompare(b.key)
      })
    }
    return grouped
  }, [fields])

  const patchField = useCallback(
    async (field: RuntimeSettingField, rawValue: unknown, reset = false) => {
      if (!currentProject?.id) return
      const targetScope: Scope = field.scope === 'both' ? scope : field.scope
      if (targetScope === 'session' && !currentSession?.id) return

      const normalized = reset ? null : normalizeValueForField(field, rawValue)
      setSavingKey(field.key)
      setError(null)
      setValues((prev) => ({ ...prev, [field.key]: normalized }))

      try {
        const patched = await api.patchRuntimeSettings({
          project_id: currentProject.id,
          session_id: targetScope === 'session' ? currentSession?.id : undefined,
          scope: targetScope,
          values: { [field.key]: normalized },
        })
        setValues(patched.values || {})
        setProjectOverrides(patched.project_overrides || {})
        setSessionOverrides(patched.session_overrides || {})
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to update setting')
        await refresh()
      } finally {
        setSavingKey(null)
      }
    },
    [currentProject?.id, currentSession?.id, scope, refresh],
  )

  if (!currentProject) {
    return (
      <div className="text-center text-slate-500 py-8 text-sm">
        Select a project to configure runtime settings.
      </div>
    )
  }

  if (loading && fields.length === 0) {
    return <div className="text-center text-slate-500 py-8 text-sm">Loading runtime settings...</div>
  }

  return (
    <div className="space-y-3">
      <div className="bg-slate-800/70 border border-slate-700 rounded-lg px-3 py-2 space-y-2">
        <p className="text-xs text-slate-300">
          Runtime settings affect narration, image generation, and choices from the next turn.
        </p>
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400">Edit scope</span>
          <button
            onClick={() => setScope('project')}
            className={`text-xs px-2 py-1 rounded ${
              scope === 'project'
                ? 'bg-emerald-700 text-emerald-100'
                : 'bg-slate-700 text-slate-300'
            }`}
          >
            Project
          </button>
          <button
            onClick={() => setScope('session')}
            disabled={!currentSession}
            className={`text-xs px-2 py-1 rounded disabled:opacity-40 ${
              scope === 'session'
                ? 'bg-emerald-700 text-emerald-100'
                : 'bg-slate-700 text-slate-300'
            }`}
          >
            Session
          </button>
        </div>
      </div>

      {error && (
        <div className="text-xs text-red-300 bg-red-900/30 border border-red-700/40 rounded px-2 py-1.5">
          {error}
        </div>
      )}

      {Object.keys(fieldsByPlugin).length === 0 && (
        <div className="text-center text-slate-500 py-8 text-sm">
          No runtime settings declared by currently enabled plugins.
        </div>
      )}

      {Object.entries(fieldsByPlugin).map(([pluginName, pluginFields]) => (
        <div key={pluginName} className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <p className="text-sm font-medium text-slate-200">{pluginName}</p>
          </div>
          {pluginFields.map((field) => {
            const currentValue = values[field.key]
            const effectiveScope = field.scope === 'both' ? scope : field.scope
            const isOverridden = effectiveScope === 'project'
              ? Object.prototype.hasOwnProperty.call(projectOverrides, field.key)
              : Object.prototype.hasOwnProperty.call(sessionOverrides, field.key)
            const disabledByScope = field.scope === 'session' && !currentSession

            return (
              <div key={field.key} className="space-y-1 border border-slate-700/70 rounded-md p-2">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-xs text-slate-200 font-medium">{field.label}</p>
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-slate-700 text-slate-400">
                      {field.scope}
                    </span>
                    {isOverridden && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-cyan-900/40 text-cyan-300">
                        overridden
                      </span>
                    )}
                    {savingKey === field.key && (
                      <span className="text-[10px] text-emerald-300">saving...</span>
                    )}
                  </div>
                </div>

                {field.description && (
                  <p className="text-[11px] text-slate-500">{field.description}</p>
                )}

                {field.type === 'boolean' ? (
                  <label className="inline-flex items-center gap-2 text-xs text-slate-300">
                    <input
                      type="checkbox"
                      checked={Boolean(currentValue)}
                      disabled={disabledByScope}
                      onChange={(e) => patchField(field, e.target.checked)}
                    />
                    Enabled
                  </label>
                ) : field.type === 'enum' ? (
                  <select
                    value={displayValue(field, currentValue)}
                    disabled={disabledByScope}
                    onChange={(e) => patchField(field, e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 disabled:opacity-50"
                  >
                    {(field.options || []).map((opt) => (
                      <option key={String(opt.value)} value={String(opt.value)}>
                        {opt.label}
                      </option>
                    ))}
                  </select>
                ) : field.component === 'textarea' ? (
                  <textarea
                    value={displayValue(field, currentValue)}
                    disabled={disabledByScope}
                    onChange={(e) => patchField(field, e.target.value)}
                    className="w-full min-h-20 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 disabled:opacity-50"
                  />
                ) : (
                  <input
                    type={field.type === 'number' || field.type === 'integer' ? 'number' : 'text'}
                    min={field.min}
                    max={field.max}
                    step={field.step || (field.type === 'integer' ? 1 : undefined)}
                    value={displayValue(field, currentValue)}
                    disabled={disabledByScope}
                    onChange={(e) => patchField(field, e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 disabled:opacity-50"
                  />
                )}

                <div className="flex items-center justify-between">
                  <p className="text-[10px] text-slate-500">
                    key: <code>{field.key}</code>
                  </p>
                  <button
                    onClick={() => patchField(field, null, true)}
                    disabled={disabledByScope}
                    className="text-[10px] px-2 py-0.5 rounded bg-slate-700 text-slate-300 hover:bg-slate-600 disabled:opacity-50"
                  >
                    Reset
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      ))}
    </div>
  )
}
