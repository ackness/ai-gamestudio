import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { FilePlus2, Sparkles, BookTemplate, ArrowLeft, Loader2 } from 'lucide-react'
import { useProjectStore } from '../../stores/projectStore'
import * as api from '../../services/api'
import type { WorldTemplate } from '../../types'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { ScrollArea } from '@/components/ui/scroll-area'
import { Badge } from '@/components/ui/badge'

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
      let doc = ''
      await api.generateWorldStream(
        {
          genre: aiGenre.trim(),
          setting: aiSetting.trim() || undefined,
          tone: aiTone.trim() || undefined,
          language: aiLang,
          extra_notes: aiExtra.trim() || undefined,
        },
        (chunk) => { doc += chunk; setGeneratedDoc(doc) },
      )
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

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent className="sm:max-w-[600px] max-h-[85vh] flex flex-col p-0 gap-0">
        <DialogHeader className="px-6 py-4 border-b shrink-0">
          <DialogTitle className="text-xl">
            {step === 'info' ? 'Create New World' : 'Choose World Setting'}
          </DialogTitle>
          <DialogDescription>
            {step === 'info' ? 'Step 1/2 — Basic Information' : 'Step 2/2 — World Document'}
          </DialogDescription>
        </DialogHeader>

        <ScrollArea className="flex-1 px-6 py-4">
          <div className="space-y-4 pb-2">
            {step === 'info' && (
              <div className="space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="name">Project Name</Label>
                  <Input
                    id="name"
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    placeholder="My Epic Quest"
                    autoFocus
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="desc">Description (Optional)</Label>
                  <Textarea
                    id="desc"
                    value={description}
                    onChange={(e) => setDescription(e.target.value)}
                    placeholder="Briefly describe your game world..."
                    className="resize-none"
                    rows={3}
                  />
                </div>
              </div>
            )}

            {step === 'world' && !worldMode && (
              <div className="grid grid-cols-1 gap-3">
                <Card 
                  className="cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => setWorldMode('blank')}
                >
                  <CardHeader className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="p-1.5 bg-primary/10 rounded-md text-primary">
                        <FilePlus2 className="w-4 h-4" />
                      </div>
                      <CardTitle className="text-base">Blank Start</CardTitle>
                    </div>
                    <CardDescription>Start from scratch and write the world document freely in the editor</CardDescription>
                  </CardHeader>
                </Card>
                <Card 
                  className="cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => setWorldMode('template')}
                >
                  <CardHeader className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="p-1.5 bg-primary/10 rounded-md text-primary">
                        <BookTemplate className="w-4 h-4" />
                      </div>
                      <CardTitle className="text-base">Choose Template</CardTitle>
                    </div>
                    <CardDescription>Select one of the preset world templates as a starting point</CardDescription>
                  </CardHeader>
                </Card>
                <Card 
                  className="cursor-pointer hover:border-primary/50 transition-colors"
                  onClick={() => setWorldMode('ai')}
                >
                  <CardHeader className="p-4">
                    <div className="flex items-center gap-2 mb-1">
                      <div className="p-1.5 bg-primary/10 rounded-md text-primary">
                        <Sparkles className="w-4 h-4" />
                      </div>
                      <CardTitle className="text-base">AI Generation</CardTitle>
                    </div>
                    <CardDescription>Describe your world and let AI generate the complete setting automatically</CardDescription>
                  </CardHeader>
                </Card>
              </div>
            )}

            {step === 'world' && worldMode === 'template' && (
              <div className="space-y-4">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="gap-2 -ml-2"
                  onClick={() => { setWorldMode(null); setSelectedSlug(null); setPreviewContent('') }}
                >
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>

                {!selectedSlug ? (
                  loadingTemplates ? (
                    <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      <span className="text-sm">Loading templates...</span>
                    </div>
                  ) : (
                    <div className="grid grid-cols-1 gap-3">
                      {templates.map((t) => (
                        <Card 
                          key={t.slug}
                          className="cursor-pointer hover:border-primary/50 transition-colors"
                          onClick={() => handleSelectTemplate(t.slug)}
                        >
                          <CardHeader className="p-4">
                            <CardTitle className="text-base">{t.name}</CardTitle>
                            <CardDescription className="mt-1">{t.description}</CardDescription>
                            <div className="flex gap-2 mt-3 flex-wrap">
                              {t.tags.map((tag) => (
                                <Badge key={tag} variant="secondary" className="font-normal text-xs">{tag}</Badge>
                              ))}
                            </div>
                          </CardHeader>
                        </Card>
                      ))}
                    </div>
                  )
                ) : (
                  <div className="space-y-3">
                    <Button 
                      variant="outline" 
                      size="sm"
                      onClick={() => { setSelectedSlug(null); setPreviewContent('') }}
                    >
                      Choose different template
                    </Button>
                    {loadingPreview ? (
                      <div className="flex items-center justify-center py-8 text-muted-foreground gap-2">
                        <Loader2 className="w-4 h-4 animate-spin" />
                        <span className="text-sm">Loading content...</span>
                      </div>
                    ) : (
                      <pre className="bg-muted p-4 rounded-lg text-sm whitespace-pre-wrap font-mono">
                        {previewContent}
                      </pre>
                    )}
                  </div>
                )}
              </div>
            )}

            {step === 'world' && worldMode === 'ai' && (
              <div className="space-y-4">
                <Button 
                  variant="ghost" 
                  size="sm" 
                  className="gap-2 -ml-2"
                  onClick={() => { setWorldMode(null); setGeneratedDoc(''); setGenerateError('') }}
                  disabled={generating}
                >
                  <ArrowLeft className="w-4 h-4" /> Back
                </Button>

                {generating ? (
                  <div className="flex flex-col items-center justify-center py-12 text-muted-foreground gap-4">
                    <Loader2 className="w-8 h-8 animate-spin text-primary" />
                    <div className="text-center">
                      <p className="font-medium text-foreground">AI is generating your world...</p>
                      <p className="text-sm mt-1">This may take a moment</p>
                    </div>
                  </div>
                ) : !generatedDoc ? (
                  <div className="space-y-4">
                    {generateError && (
                      <div className="p-3 bg-destructive/10 border border-destructive/20 text-destructive rounded-md text-sm">
                        {generateError}
                      </div>
                    )}
                    <div className="space-y-2">
                      <Label htmlFor="genre">Genre / Theme</Label>
                      <Input
                        id="genre"
                        value={aiGenre}
                        onChange={(e) => setAiGenre(e.target.value)}
                        placeholder="e.g. Dark Fantasy, Cyberpunk, Wuxia..."
                      />
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="aiSetting">World Setting Summary (Optional)</Label>
                      <Textarea
                        id="aiSetting"
                        value={aiSetting}
                        onChange={(e) => setAiSetting(e.target.value)}
                        className="resize-none"
                        rows={2}
                        placeholder="Describe the core setting of your world..."
                      />
                    </div>
                    <div className="grid grid-cols-2 gap-4">
                      <div className="space-y-2">
                        <Label htmlFor="tone">Narrative Tone (Optional)</Label>
                        <select
                          id="tone"
                          value={aiTone}
                          onChange={(e) => setAiTone(e.target.value)}
                          className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <option value="">Any</option>
                          <option value="暗黑">Dark</option>
                          <option value="轻松">Light-hearted</option>
                          <option value="史诗">Epic</option>
                          <option value="写实">Realistic</option>
                        </select>
                      </div>
                      <div className="space-y-2">
                        <Label htmlFor="lang">Generation Language</Label>
                        <select
                          id="lang"
                          value={aiLang}
                          onChange={(e) => setAiLang(e.target.value)}
                          className="flex h-9 w-full items-center justify-between rounded-md border border-input bg-transparent px-3 py-2 text-sm shadow-sm ring-offset-background placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring disabled:cursor-not-allowed disabled:opacity-50"
                        >
                          <option value="zh">中文</option>
                          <option value="en">English</option>
                          <option value="ja">日本語</option>
                          <option value="ko">한국어</option>
                        </select>
                      </div>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="extra">Additional Notes (Optional)</Label>
                      <Textarea
                        id="extra"
                        value={aiExtra}
                        onChange={(e) => setAiExtra(e.target.value)}
                        className="resize-none"
                        rows={2}
                        placeholder="Any other specific requirements..."
                      />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-2 flex flex-col h-[40vh]">
                    <Label>Generated Result (Editable)</Label>
                    <Textarea
                      value={generatedDoc}
                      onChange={(e) => setGeneratedDoc(e.target.value)}
                      className="flex-1 resize-none font-mono text-sm min-h-[300px]"
                    />
                  </div>
                )}
              </div>
            )}
          </div>
        </ScrollArea>

        <DialogFooter className="px-6 py-4 border-t sm:justify-between shrink-0">
          <div className="flex-1">
            {step === 'world' && !worldMode && (
              <Button variant="ghost" onClick={() => setStep('info')}>
                Previous
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>

            {step === 'info' && (
              <Button 
                onClick={() => setStep('world')} 
                disabled={!name.trim()}
              >
                Next
              </Button>
            )}

            {step === 'world' && worldMode === 'blank' && (
              <Button 
                onClick={() => handleCreate('')}
                disabled={creating}
              >
                {creating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating...</> : 'Create Project'}
              </Button>
            )}

            {step === 'world' && worldMode === 'template' && selectedSlug && previewContent && !loadingPreview && (
              <Button 
                onClick={() => handleCreate(previewContent)}
                disabled={creating}
              >
                {creating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating...</> : 'Use Template'}
              </Button>
            )}

            {step === 'world' && worldMode === 'ai' && !generatedDoc && !generating && (
              <Button 
                onClick={handleGenerate}
                disabled={!aiGenre.trim()}
              >
                <Sparkles className="w-4 h-4 mr-2" />
                Generate World
              </Button>
            )}

            {step === 'world' && worldMode === 'ai' && generatedDoc && (
              <Button 
                onClick={() => handleCreate(generatedDoc)}
                disabled={creating}
              >
                {creating ? <><Loader2 className="w-4 h-4 mr-2 animate-spin" /> Creating...</> : 'Create Project'}
              </Button>
            )}
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
