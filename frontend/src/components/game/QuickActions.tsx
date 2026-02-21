import { Zap } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface Props {
  onTrigger: (blockType: string) => void
  disabled: boolean
}

const TRIGGERS = [
  { type: 'guide', label: '输出指引' },
]

export function QuickActions({ onTrigger, disabled }: Props) {
  if (TRIGGERS.length === 0) return null
  
  return (
    <div className="flex gap-2 px-4 py-2 border-t bg-muted/10 shrink-0">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mr-1">
        <Zap className="w-3.5 h-3.5 text-amber-500" />
        快速行动
      </div>
      {TRIGGERS.map((t) => (
        <Button
          key={t.type}
          variant="outline"
          size="sm"
          className="h-6 px-2.5 text-[11px] rounded-full border-dashed hover:border-solid bg-background"
          onClick={() => onTrigger(t.type)}
          disabled={disabled}
        >
          {t.label}
        </Button>
      ))}
    </div>
  )
}
