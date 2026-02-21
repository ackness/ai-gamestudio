import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useProjectStore } from '../../stores/projectStore'
import * as api from '../../services/api'
import type { WorldTemplate } from '../../types'

type Step = 'info' | 'world'
type WorldMode = null | 'blank' | 'template' | 'ai'

interface Props {
  open: boolean
  onClose: () => void
}

export function CreateProjectWizard({ open, onClose }: Props) {
  const navigate = useNavigate()
  const { createProject } = useProjectStore()

  // Step 1: basic info
  const [step, setStep] = useState<Step>('info')
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')

  // Step 2: world setup
  const [worldMode, setWorldMode] = useState<WorldMode>(null)
  const [templates, setTemplates] = useState<WorldTemplate[]>([])
  const [loadingTemplates, setLoadingTemplates] = useState(false)
  const [selectedSlug, setSelectedSlug] = useState<string | null>(null)
  const [previewContent, setPreviewContent] = useState('')
  const [loadingPreview, setLoadingPreview] = useState(false)

  // AI generation
  const [aiGenre, setAiGenre] = useState('')
  const [aiSetting, setAiSetting] = useState('')
  const [aiTone, setAiTone] = useState('')
  const [aiLang, setAiLang] = useState('zh')
  const [aiExtra, setAiExtra] = useState('')
  const [generating, setGenerating] = useState(false)
  const [generateError, setGenerateError] = useState('')
  const [generatedDoc, setGeneratedDoc] = useState('')

  const [creating, setCreating] = useState(false)

  // Reset state when opening/closing
  useEffect(() => {
    if (open) {
      setStep('info')
      setName('')
      setDescription('')
      setWorldMode(null)
      setTemplates([])
      setSelectedSlug(null)
      setPreviewContent('')
      setAiGenre('')
      setAiSetting('')
      setAiTone('')
      setAiLang('zh')
      setAiExtra('')
      setGenerateError('')
      setGeneratedDoc('')
    }
  }, [open])

  // Load templates when selecting template mode
  useEffect(() => {
    if (worldMode === 'template' && templates.length === 0) {
      setLoadingTemplates(true)
      api.getWorldTemplates().then(setTemplates).finally(() => setLoadingTemplates(false))
    }
  }, [worldMode, templates.length])

  const handleSelectTemplate = async (slug: string) => {
    setSelectedSlug(slug)
    setLoadingPreview(true)
    try {
      const detail = await api.getWorldTemplate(slug)
      setPreviewContent(detail.content)
    } finally {
      setLoadingPreview(false)
    }
  }

  const handleGenerate = async () => {
    if (!aiGenre.trim()) return
    setGenerating(true)
    setGenerateError('')
    try {
      const result = await api.generateWorld({
        genre: aiGenre.trim(),
        setting: aiSetting.trim() || undefined,
        tone: aiTone.trim() || undefined,
        language: aiLang,
        extra_notes: aiExtra.trim() || undefined,
      })
      setGeneratedDoc(result.world_doc)
    } catch (err) {
      console.error('Failed to generate world:', err)
      setGenerateError(err instanceof Error ? err.message : '生成失败，请重试')
    } finally {
      setGenerating(false)
    }
  }

  const handleCreate = async (worldDoc: string) => {
    setCreating(true)
    try {
      const project = await createProject({
        name: name.trim(),
        description: description.trim() || undefined,
        world_doc: worldDoc,
      })
      onClose()
      navigate(`/projects/${project.id}`)
    } finally {
      setCreating(false)
    }
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-slate-800 border border-slate-700 rounded-xl w-full max-w-2xl max-h-[85vh] flex flex-col">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-700 flex items-center justify-between flex-shrink-0">
          <div>
            <h2 className="text-lg font-semibold text-slate-100">
              {step === 'info' ? '创建新项目' : '选择世界设定'}
            </h2>
            <p className="text-sm text-slate-400 mt-0.5">
              {step === 'info' ? '步骤 1/2 — 基本信息' : '步骤 2/2 — 世界文档'}
            </p>
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-200 text-xl leading-none">
            &times;
          </button>
        </div>

        {/* Body */}
        <div className="px-6 py-4 overflow-y-auto flex-1">
          {step === 'info' && (
            <div className="space-y-4">
              <div>
                <label className="block text-sm text-slate-300 mb-1">项目名称</label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                  placeholder="My Epic Quest"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">描述（可选）</label>
                <textarea
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 resize-none"
                  rows={3}
                  placeholder="简要描述你的游戏世界..."
                />
              </div>
            </div>
          )}

          {step === 'world' && !worldMode && (
            <div className="grid grid-cols-1 gap-3">
              <button
                onClick={() => setWorldMode('blank')}
                className="text-left p-4 bg-slate-900 border border-slate-600 rounded-lg hover:border-emerald-500/50 transition-colors"
              >
                <div className="text-slate-100 font-medium">空白开始</div>
                <div className="text-slate-400 text-sm mt-1">从零开始，在编辑器中自由编写世界文档</div>
              </button>
              <button
                onClick={() => setWorldMode('template')}
                className="text-left p-4 bg-slate-900 border border-slate-600 rounded-lg hover:border-emerald-500/50 transition-colors"
              >
                <div className="text-slate-100 font-medium">选择模板</div>
                <div className="text-slate-400 text-sm mt-1">从预置的世界模板中选择一个作为起点</div>
              </button>
              <button
                onClick={() => setWorldMode('ai')}
                className="text-left p-4 bg-slate-900 border border-slate-600 rounded-lg hover:border-emerald-500/50 transition-colors"
              >
                <div className="text-slate-100 font-medium">AI 生成</div>
                <div className="text-slate-400 text-sm mt-1">描述你想要的世界，由 AI 自动生成完整设定</div>
              </button>
            </div>
          )}

          {step === 'world' && worldMode === 'template' && (
            <div>
              <button
                onClick={() => { setWorldMode(null); setSelectedSlug(null); setPreviewContent('') }}
                className="text-sm text-slate-400 hover:text-slate-200 mb-3 inline-block"
              >
                &larr; 返回
              </button>

              {!selectedSlug ? (
                loadingTemplates ? (
                  <div className="text-slate-400 text-center py-8">加载模板...</div>
                ) : (
                  <div className="grid grid-cols-1 gap-3">
                    {templates.map((t) => (
                      <button
                        key={t.slug}
                        onClick={() => handleSelectTemplate(t.slug)}
                        className="text-left p-4 bg-slate-900 border border-slate-600 rounded-lg hover:border-emerald-500/50 transition-colors"
                      >
                        <div className="text-slate-100 font-medium">{t.name}</div>
                        <div className="text-slate-400 text-sm mt-1">{t.description}</div>
                        <div className="flex gap-2 mt-2 flex-wrap">
                          {t.tags.map((tag) => (
                            <span
                              key={tag}
                              className="text-xs px-2 py-0.5 bg-slate-700 text-slate-300 rounded"
                            >
                              {tag}
                            </span>
                          ))}
                        </div>
                      </button>
                    ))}
                  </div>
                )
              ) : (
                <div>
                  <button
                    onClick={() => { setSelectedSlug(null); setPreviewContent('') }}
                    className="text-sm text-slate-400 hover:text-slate-200 mb-3 inline-block"
                  >
                    &larr; 选择其他模板
                  </button>
                  {loadingPreview ? (
                    <div className="text-slate-400 text-center py-8">加载内容...</div>
                  ) : (
                    <div>
                      <pre className="bg-slate-900 border border-slate-600 rounded-lg p-4 text-slate-300 text-sm whitespace-pre-wrap max-h-64 overflow-y-auto">
                        {previewContent}
                      </pre>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {step === 'world' && worldMode === 'ai' && (
            <div>
              <button
                onClick={() => { setWorldMode(null); setGeneratedDoc(''); setGenerateError('') }}
                className="text-sm text-slate-400 hover:text-slate-200 mb-3 inline-block"
                disabled={generating}
              >
                &larr; 返回
              </button>

              {generating ? (
                <div className="flex flex-col items-center justify-center py-12">
                  <div className="w-8 h-8 border-2 border-slate-600 border-t-emerald-500 rounded-full animate-spin mb-4" />
                  <p className="text-slate-300 font-medium">AI 正在生成世界文档...</p>
                  <p className="text-slate-500 text-sm mt-1">这可能需要一些时间，请耐心等待</p>
                </div>
              ) : !generatedDoc ? (
                <div className="space-y-4">
                  {generateError && (
                    <div className="p-3 bg-red-900/30 border border-red-700 rounded-lg text-red-300 text-sm">
                      {generateError}
                    </div>
                  )}
                  <div>
                    <label className="block text-sm text-slate-300 mb-1">类型 / 题材</label>
                    <input
                      type="text"
                      value={aiGenre}
                      onChange={(e) => setAiGenre(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                      placeholder="如：暗黑奇幻、赛博朋克、武侠..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-slate-300 mb-1">世界设定简述（可选）</label>
                    <textarea
                      value={aiSetting}
                      onChange={(e) => setAiSetting(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 resize-none"
                      rows={2}
                      placeholder="描述你想要的世界设定..."
                    />
                  </div>
                  <div>
                    <label className="block text-sm text-slate-300 mb-1">叙事基调（可选）</label>
                    <select
                      value={aiTone}
                      onChange={(e) => setAiTone(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    >
                      <option value="">不指定</option>
                      <option value="暗黑">暗黑</option>
                      <option value="轻松">轻松</option>
                      <option value="史诗">史诗</option>
                      <option value="写实">写实</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-slate-300 mb-1">生成语言</label>
                    <select
                      value={aiLang}
                      onChange={(e) => setAiLang(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500"
                    >
                      <option value="zh">中文</option>
                      <option value="en">English</option>
                      <option value="ja">日本語</option>
                      <option value="ko">한국어</option>
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm text-slate-300 mb-1">补充说明（可选）</label>
                    <textarea
                      value={aiExtra}
                      onChange={(e) => setAiExtra(e.target.value)}
                      className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 resize-none"
                      rows={2}
                      placeholder="任何额外要求..."
                    />
                  </div>
                </div>
              ) : (
                <div>
                  <label className="block text-sm text-slate-300 mb-1">生成结果（可编辑）</label>
                  <textarea
                    value={generatedDoc}
                    onChange={(e) => setGeneratedDoc(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-900 border border-slate-600 rounded-lg text-slate-100 focus:outline-none focus:border-emerald-500 resize-none font-mono text-sm"
                    rows={12}
                  />
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-4 border-t border-slate-700 flex justify-between flex-shrink-0">
          <div>
            {step === 'world' && !worldMode && (
              <button
                onClick={() => setStep('info')}
                className="px-4 py-2 text-slate-300 hover:text-slate-100 transition-colors"
              >
                上一步
              </button>
            )}
          </div>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 text-slate-300 hover:text-slate-100 transition-colors"
            >
              取消
            </button>

            {step === 'info' && (
              <button
                onClick={() => setStep('world')}
                disabled={!name.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
              >
                下一步
              </button>
            )}

            {step === 'world' && worldMode === 'blank' && (
              <button
                onClick={() => handleCreate('')}
                disabled={creating}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
              >
                {creating ? '创建中...' : '创建项目'}
              </button>
            )}

            {step === 'world' && worldMode === 'template' && selectedSlug && previewContent && !loadingPreview && (
              <button
                onClick={() => handleCreate(previewContent)}
                disabled={creating}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
              >
                {creating ? '创建中...' : '使用此模板'}
              </button>
            )}

            {step === 'world' && worldMode === 'ai' && !generatedDoc && !generating && (
              <button
                onClick={handleGenerate}
                disabled={!aiGenre.trim()}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
              >
                生成世界
              </button>
            )}

            {step === 'world' && worldMode === 'ai' && generatedDoc && (
              <button
                onClick={() => handleCreate(generatedDoc)}
                disabled={creating}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed text-white rounded-lg font-medium transition-colors"
              >
                {creating ? '创建中...' : '创建项目'}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
