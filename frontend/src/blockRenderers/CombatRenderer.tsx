import type { BlockRendererProps } from '../services/blockRenderers'

/* ── combat_start ── */
interface Combatant {
  name: string
  hp: number
  initiative: number
}
interface CombatStartData {
  combatants?: Combatant[]
  description?: string
}

export function CombatStartRenderer({ data }: BlockRendererProps) {
  if (!data || typeof data !== 'object') return null
  const d = data as CombatStartData
  const sorted = [...(d.combatants || [])].sort((a, b) => b.initiative - a.initiative)

  return (
    <div className="bg-red-900/20 border border-red-500/40 rounded-xl px-4 py-3 max-w-[80%] space-y-2">
      <p className="text-sm font-medium text-red-300">战斗开始</p>
      {d.description && <p className="text-xs text-slate-300">{d.description}</p>}
      <div className="space-y-1">
        {sorted.map((c, i) => (
          <div key={i} className="flex items-center justify-between text-xs">
            <span className="text-slate-200">{c.name}</span>
            <span className="text-slate-400">
              HP {c.hp} | 先攻 {c.initiative}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── combat_round ── */
interface HpChange {
  name: string
  current_hp: number
  max_hp?: number
  change: number
}
interface CombatRoundData {
  actor?: string
  action_type?: string
  target?: string
  hit?: boolean
  attack_roll?: number
  damage?: number
  damage_roll?: string
  effects?: string[]
  hp_changes?: HpChange[]
  description?: string
}

export function CombatRoundRenderer({ data }: BlockRendererProps) {
  if (!data || typeof data !== 'object') return null
  const d = data as CombatRoundData
  const isHit = d.hit === true

  return (
    <div className={`${isHit ? 'bg-orange-900/20 border-orange-500/40' : 'bg-slate-800/60 border-slate-600/50'} border rounded-xl px-4 py-3 max-w-[80%] space-y-2`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-200">
          {d.actor} → {d.target}
        </p>
        <span className={`text-[10px] px-2 py-0.5 rounded ${isHit ? 'bg-orange-500/30 text-orange-300' : 'bg-slate-600/30 text-slate-400'}`}>
          {d.action_type === 'defend' ? '防御' : d.action_type === 'flee' ? '逃跑' : isHit ? '命中' : '未命中'}
        </span>
      </div>

      <div className="flex items-baseline gap-3 text-xs text-slate-300 flex-wrap">
        {d.attack_roll !== undefined && d.attack_roll > 0 && (
          <span>攻击骰: <span className="font-mono font-semibold text-slate-100">{d.attack_roll}</span></span>
        )}
        {isHit && d.damage !== undefined && (
          <span>伤害: <span className="font-mono font-semibold text-red-300">{d.damage}</span>
            {d.damage_roll && <span className="text-slate-500 ml-1">({d.damage_roll})</span>}
          </span>
        )}
        {d.effects && d.effects.length > 0 && (
          <span className="text-amber-400">{d.effects.join(', ')}</span>
        )}
      </div>

      {d.hp_changes && d.hp_changes.length > 0 && (
        <div className="space-y-1">
          {d.hp_changes.map((h, i) => (
            <div key={i} className="flex items-center justify-between text-xs">
              <span className="text-slate-200">{h.name}</span>
              <span className="font-mono">
                <span className={h.change < 0 ? 'text-red-400' : 'text-emerald-400'}>
                  {h.change > 0 ? `+${h.change}` : h.change}
                </span>
                <span className="text-slate-500 ml-1">→ HP {h.current_hp}{h.max_hp ? `/${h.max_hp}` : ''}</span>
              </span>
            </div>
          ))}
        </div>
      )}

      {d.description && <p className="text-xs text-slate-400">{d.description}</p>}
    </div>
  )
}

/* ── combat_end ── */
interface CombatEndData {
  outcome?: 'victory' | 'defeat' | 'flee' | 'truce'
  survivors?: string[]
  rewards?: { xp?: number; items?: string[] }
  description?: string
}

const outcomeConfig = {
  victory: { label: '胜利', bg: 'bg-emerald-900/30', border: 'border-emerald-500/50', text: 'text-emerald-300' },
  defeat: { label: '失败', bg: 'bg-red-900/30', border: 'border-red-500/50', text: 'text-red-300' },
  flee: { label: '逃跑', bg: 'bg-amber-900/30', border: 'border-amber-500/50', text: 'text-amber-300' },
  truce: { label: '休战', bg: 'bg-blue-900/30', border: 'border-blue-500/50', text: 'text-blue-300' },
} as const

export function CombatEndRenderer({ data }: BlockRendererProps) {
  if (!data || typeof data !== 'object') return null
  const d = data as CombatEndData
  const outcome = d.outcome && outcomeConfig[d.outcome] ? d.outcome : 'victory'
  const config = outcomeConfig[outcome]

  return (
    <div className={`${config.bg} border ${config.border} rounded-xl px-4 py-3 max-w-[80%] space-y-2`}>
      <div className="flex items-center justify-between gap-2">
        <p className="text-sm font-medium text-slate-200">战斗结束</p>
        <span className={`text-[10px] px-2 py-0.5 rounded ${config.text} bg-black/20`}>
          {config.label}
        </span>
      </div>

      {d.description && <p className="text-xs text-slate-300">{d.description}</p>}

      {d.survivors && d.survivors.length > 0 && (
        <p className="text-xs text-slate-400">存活: {d.survivors.join(', ')}</p>
      )}

      {d.rewards && (d.rewards.xp || (d.rewards.items && d.rewards.items.length > 0)) && (
        <div className="text-xs text-amber-300 space-x-3">
          {d.rewards.xp && <span>+{d.rewards.xp} XP</span>}
          {d.rewards.items && d.rewards.items.length > 0 && (
            <span>获得: {d.rewards.items.join(', ')}</span>
          )}
        </div>
      )}
    </div>
  )
}
