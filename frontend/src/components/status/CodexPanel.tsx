import { useEffect, useMemo } from 'react'
import { Search, Skull, Gem, MapPin, BookOpen, User } from 'lucide-react'
import { useCodexStore, type CodexEntry } from '../../stores/codexStore'
import { useProjectStore } from '../../stores/projectStore'
import { useUiStore } from '../../stores/uiStore'
import { Input } from '@/components/ui/input'
import { Badge } from '@/components/ui/badge'

const CATEGORY_META: Record<
  string,
  { icon: React.ElementType; label: Record<string, string>; color: string }
> = {
  monster: { icon: Skull, label: { zh: '怪物', en: 'Monsters' }, color: 'text-red-400' },
  item: { icon: Gem, label: { zh: '物品', en: 'Items' }, color: 'text-blue-400' },
  location: { icon: MapPin, label: { zh: '地点', en: 'Locations' }, color: 'text-green-400' },
  lore: { icon: BookOpen, label: { zh: '传说', en: 'Lore' }, color: 'text-amber-400' },
  character: { icon: User, label: { zh: '角色', en: 'Characters' }, color: 'text-purple-400' },
}

const panelText: Record<string, Record<string, string>> = {
  zh: { empty: '暂无图鉴条目', search: '搜索图鉴…', newBadge: '新' },
  en: { empty: 'No codex entries yet', search: 'Search codex…', newBadge: 'NEW' },
}

function EntryCard({ entry, language }: { entry: CodexEntry; language: string }) {
  const t = panelText[language] ?? panelText.en
  return (
    <div
      className={`rounded-lg border p-2.5 ${
        entry._isNew ? 'border-amber-500/50 bg-amber-500/5' : 'border-border/50'
      }`}
    >
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium truncate flex-1">{entry.title}</span>
        {entry._isNew && (
          <Badge variant="outline" className="text-[10px] px-1.5 py-0 h-auto border-amber-500/50 text-amber-400">
            {t.newBadge}
          </Badge>
        )}
      </div>
      <p className="text-xs text-muted-foreground mt-1 line-clamp-3">{entry.content}</p>
      {entry.tags && entry.tags.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {entry.tags.map((tag) => (
            <Badge key={tag} variant="secondary" className="text-[10px] px-1.5 py-0 h-auto">
              {tag}
            </Badge>
          ))}
        </div>
      )}
    </div>
  )
}

export function CodexPanel() {
  const projectId = useProjectStore((s) => s.currentProject?.id)
  const language = useUiStore((s) => s.language)
  const { entries, loading, searchQuery, setSearchQuery, fetchEntries, clearNewFlags } = useCodexStore()
  const t = panelText[language] ?? panelText.en

  useEffect(() => {
    if (projectId) fetchEntries(projectId)
  }, [projectId, fetchEntries])

  useEffect(() => {
    return () => clearNewFlags()
  }, [clearNewFlags])

  const filtered = useMemo(() => {
    if (!searchQuery.trim()) return entries
    const q = searchQuery.toLowerCase()
    return entries.filter(
      (e) =>
        e.title.toLowerCase().includes(q) ||
        e.content.toLowerCase().includes(q) ||
        e.tags?.some((tag) => tag.toLowerCase().includes(q)),
    )
  }, [entries, searchQuery])

  const grouped = useMemo(() => {
    const map = new Map<string, CodexEntry[]>()
    for (const entry of filtered) {
      const list = map.get(entry.category) || []
      list.push(entry)
      map.set(entry.category, list)
    }
    return map
  }, [filtered])

  if (loading) {
    return <p className="text-muted-foreground text-sm text-center py-4">Loading…</p>
  }

  return (
    <div className="space-y-3">
      <div className="relative">
        <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground" />
        <Input
          value={searchQuery}
          onChange={(e) => setSearchQuery(e.target.value)}
          placeholder={t.search}
          className="pl-8 h-8 text-sm"
        />
      </div>

      {filtered.length === 0 && (
        <p className="text-muted-foreground text-sm text-center py-4">{t.empty}</p>
      )}

      {Array.from(grouped.entries()).map(([category, items]) => {
        const meta = CATEGORY_META[category]
        if (!meta) return null
        const Icon = meta.icon
        const label = meta.label[language] ?? meta.label.en
        return (
          <div key={category}>
            <div className={`flex items-center gap-1.5 mb-2 ${meta.color}`}>
              <Icon className="w-3.5 h-3.5" />
              <h4 className="text-xs font-medium uppercase">{label}</h4>
              <span className="text-[10px] text-muted-foreground">({items.length})</span>
            </div>
            <div className="space-y-2">
              {items.map((entry) => (
                <EntryCard key={entry.entry_id} entry={entry} language={language} />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
