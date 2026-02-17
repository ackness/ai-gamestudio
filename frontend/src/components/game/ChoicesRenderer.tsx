import { useState } from 'react'
import type { BlockRendererProps } from '../../services/blockRenderers'
import {
  EMPTY_BLOCK_INTERACTION,
  useBlockInteractionStore,
} from '../../stores/blockInteractionStore'
import { buildChoicesInteractionState } from './blockInteractionState'

interface ChoicesData {
  prompt: string
  type: 'single' | 'multi'
  options: string[]
}

export function ChoicesRenderer({ data, blockId, onAction, locked }: BlockRendererProps) {
  if (!data || typeof data !== 'object') return null

  const { prompt, type = 'single', options = [] } = data as ChoicesData
  const interaction = useBlockInteractionStore(
    (s) => s.interactions[blockId] ?? EMPTY_BLOCK_INTERACTION,
  )
  const setInteraction = useBlockInteractionStore((s) => s.setInteraction)
  const interactionState = buildChoicesInteractionState(options, interaction)
  const chosen = interactionState.chosen
  const [selected, setSelected] = useState<Set<number>>(
    () => new Set(interactionState.selectedIndexes)
  )
  const submitted = interactionState.submitted

  // If locked (attached to old message) or already submitted, show read-only view
  if (locked || submitted) {
    const chosenText = chosen.length > 0 ? chosen : [...selected].map((i) => options[i])
    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 space-y-2 max-w-[80%] opacity-70">
        <p className="text-slate-400 text-sm">{prompt}</p>
        {chosenText.length > 0 ? (
          <p className="text-emerald-400 text-sm">
            已选择：{chosenText.join('、')}
          </p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {options.map((opt, i) => (
              <span key={i} className="text-sm px-3 py-1.5 bg-slate-700/50 text-slate-500 rounded-lg cursor-not-allowed">
                {opt}
              </span>
            ))}
          </div>
        )}
      </div>
    )
  }

  if (type === 'multi') {
    const toggle = (i: number) => {
      setSelected((prev) => {
        const next = new Set(prev)
        if (next.has(i)) next.delete(i)
        else next.add(i)
        return next
      })
    }

    const confirm = () => {
      if (selected.size === 0) return
      const chosen = [...selected].map((i) => options[i])
      setInteraction(blockId, { submitted: true, chosen })
      onAction(`我选择：${chosen.join('、')}`)
    }

    return (
      <div className="bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 space-y-2 max-w-[80%]">
        <p className="text-slate-300 text-sm font-medium">{prompt}</p>
        <div className="space-y-1">
          {options.map((opt, i) => (
            <label
              key={i}
              className="flex items-center gap-2 cursor-pointer text-sm text-slate-200 hover:text-white"
            >
              <input
                type="checkbox"
                checked={selected.has(i)}
                onChange={() => toggle(i)}
                className="accent-cyan-500"
              />
              {opt}
            </label>
          ))}
        </div>
        <button
          onClick={confirm}
          disabled={selected.size === 0}
          className="text-xs px-3 py-1.5 bg-cyan-700 hover:bg-cyan-600 disabled:opacity-40 disabled:cursor-not-allowed text-white rounded transition-colors"
        >
          确认选择
        </button>
      </div>
    )
  }

  // single select — buttons
  const handleClick = (opt: string, i: number) => {
    setSelected(new Set([i]))
    setInteraction(blockId, { submitted: true, chosen: [opt] })
    onAction(`我选择：${opt}`)
  }

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-xl px-4 py-3 space-y-2 max-w-[80%]">
      <p className="text-slate-300 text-sm font-medium">{prompt}</p>
      <div className="flex flex-wrap gap-2">
        {options.map((opt, i) => (
          <button
            key={i}
            onClick={() => handleClick(opt, i)}
            className="text-sm px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-slate-200 rounded-lg transition-colors"
          >
            {opt}
          </button>
        ))}
      </div>
    </div>
  )
}
