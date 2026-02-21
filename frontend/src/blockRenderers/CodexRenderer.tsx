import { useState } from 'react'
import type { BlockRendererProps } from '../services/blockRenderers'

interface CodexEntryData {
  action: 'unlock' | 'update'
  category: string
  entry_id: string
  title: string
  content: string
  tags?: string[]
  image_hint?: string
}

const categoryConfig: Record<string, { icon: string; label: string }> = {
  monster:   { icon: '\u{1F480}', label: 'Monster' },
  item:      { icon: '\u{1F48E}', label: 'Item' },
  location:  { icon: '\u{1F5FA}\uFE0F',  label: 'Location' },
  lore:      { icon: '\u{1F4D6}', label: 'Lore' },
  character: { icon: '\u{1F464}', label: 'Character' },
}

const TRUNCATE_LENGTH = 120

export function CodexRenderer({ data }: BlockRendererProps) {
  const d = data as CodexEntryData
  const [expanded, setExpanded] = useState(false)
  const cat = categoryConfig[d.category] || categoryConfig.lore
  const isUnlock = d.action === 'unlock'
  const needsTruncate = d.content.length > TRUNCATE_LENGTH

  return (
    <div className="bg-amber-500/10 border border-amber-500/40 rounded-xl px-4 py-3 max-w-[80%] space-y-2">
      <div className="flex items-center gap-2">
        <span className={`text-xs px-1.5 py-0.5 rounded font-medium ${isUnlock ? 'bg-amber-500/30 text-amber-300' : 'bg-muted text-muted-foreground'}`}>
          {isUnlock ? '\u2728 New Discovery!' : '\u{1F504} Updated'}
        </span>
        <span className="text-muted-foreground text-xs flex items-center gap-1">
          {cat.icon} {cat.label}
        </span>
      </div>
      <p className="text-amber-200 font-medium">{d.title}</p>
      <p className="text-foreground/80 text-sm">
        {needsTruncate && !expanded ? d.content.slice(0, TRUNCATE_LENGTH) + '...' : d.content}
        {needsTruncate && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-1 text-amber-400 hover:text-amber-300 text-xs underline"
          >
            {expanded ? 'Collapse' : 'Expand'}
          </button>
        )}
      </p>
      {d.tags && d.tags.length > 0 && (
        <div className="flex flex-wrap gap-1">
          {d.tags.map((tag) => (
            <span key={tag} className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
              {tag}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
