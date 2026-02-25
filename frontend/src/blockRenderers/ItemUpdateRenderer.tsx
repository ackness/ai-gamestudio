import type { BlockRendererProps } from '../services/blockRenderers'

interface ItemUpdateData {
  action: 'gain' | 'lose' | 'use' | 'equip' | 'unequip'
  item_name: string
  quantity: number
  item_type?: string
  description?: string
  stats?: Record<string, unknown>
}

const actionStyles: Record<string, { icon: string; label: string; color: string }> = {
  gain: { icon: '📦', label: '获得', color: 'text-emerald-400' },
  lose: { icon: '💨', label: '失去', color: 'text-red-400' },
  use: { icon: '✨', label: '使用', color: 'text-cyan-400' },
  equip: { icon: '🛡️', label: '装备', color: 'text-amber-400' },
  unequip: { icon: '📤', label: '卸下', color: 'text-muted-foreground' },
}

const typeLabels: Record<string, string> = {
  weapon: '武器',
  armor: '护甲',
  consumable: '消耗品',
  quest: '任务物品',
  misc: '杂物',
  currency: '货币',
  material: '材料',
  key: '钥匙',
}

export function ItemUpdateRenderer({ data }: BlockRendererProps) {
  const d = data as ItemUpdateData
  if (!d || !d.item_name) return null

  const style = actionStyles[d.action] || actionStyles.gain
  const typeLabel = d.item_type ? typeLabels[d.item_type] || d.item_type : undefined

  return (
    <div className="bg-card border border-border/50 rounded-xl px-4 py-3 max-w-[80%] space-y-1">
      <div className="flex items-center gap-2">
        <span className="text-sm">{style.icon}</span>
        <span className={`text-sm font-medium ${style.color}`}>
          {style.label}
        </span>
        <span className="text-sm font-medium">{d.item_name}</span>
        {d.quantity > 1 && (
          <span className="text-muted-foreground text-xs">x{d.quantity}</span>
        )}
        {typeLabel && (
          <span className="text-xs bg-muted text-muted-foreground px-1.5 py-0.5 rounded">
            {typeLabel}
          </span>
        )}
      </div>
      {d.description && (
        <p className="text-muted-foreground text-xs leading-relaxed ml-6">
          {d.description}
        </p>
      )}
      {d.stats && Object.keys(d.stats).length > 0 && (
        <div className="flex flex-wrap gap-2 ml-6">
          {Object.entries(d.stats).map(([k, v]) => (
            <span key={k} className="text-xs text-cyan-400">
              {k}: {String(v)}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}
