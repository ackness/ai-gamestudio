import type { BlockRendererProps } from '../services/blockRenderers'
import { useBlockI18n } from './i18n'

interface CodexEntryData {
  action: 'unlock' | 'update'
  category: string
  entry_id: string
  title: string
  content: string
  tags?: string[]
  image_hint?: string
}

const categoryKeys = {
  monster: 'codex.monster',
  item: 'codex.item',
  location: 'codex.location',
  lore: 'codex.lore',
  character: 'codex.character',
} as const

const categoryIcons: Record<string, string> = {
  monster: '\u{1F480}',
  item: '\u{1F48E}',
  location: '\u{1F5FA}\uFE0F',
  lore: '\u{1F4D6}',
  character: '\u{1F464}',
}

export function CodexRenderer({ data }: BlockRendererProps) {
  const { t } = useBlockI18n()
  const d = data as CodexEntryData
  const catKey = categoryKeys[d.category as keyof typeof categoryKeys]
  const catIcon = categoryIcons[d.category] || categoryIcons.lore
  const isUnlock = d.action === 'unlock'

  return (
    <div className="bg-amber-500/8 border border-amber-500/30 rounded-lg px-3 py-2.5 max-w-[72%] space-y-1.5">
      <div className="flex items-center gap-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${isUnlock ? 'bg-amber-500/30 text-amber-300' : 'bg-muted text-muted-foreground'}`}>
          {isUnlock ? `\u2728 ${t('codex.newDiscovery')}` : `\u{1F504} ${t('codex.updated')}`}
        </span>
        <span className="text-muted-foreground text-xs flex items-center gap-1">
          {catIcon} {catKey ? t(catKey) : d.category}
        </span>
      </div>
      <p className="text-foreground text-sm font-medium truncate">{d.title}</p>
      <p className="text-[11px] text-muted-foreground">{t('codex.viewInPanel')}</p>
    </div>
  )
}
