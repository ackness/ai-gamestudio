interface Props {
  onTrigger: (blockType: string) => void
  disabled: boolean
}

const TRIGGERS = [
  { type: 'guide', label: '输出指引' },
]

export function QuickActions({ onTrigger, disabled }: Props) {
  return (
    <div className="flex gap-1.5 px-3 py-1.5 border-t border-slate-700/50">
      {TRIGGERS.map((t) => (
        <button
          key={t.type}
          onClick={() => onTrigger(t.type)}
          disabled={disabled}
          className="text-xs px-2.5 py-1 bg-slate-800 hover:bg-slate-700
            border border-slate-600/50 text-slate-400 hover:text-slate-200
            rounded-full transition-colors disabled:opacity-40"
        >
          {t.label}
        </button>
      ))}
    </div>
  )
}
