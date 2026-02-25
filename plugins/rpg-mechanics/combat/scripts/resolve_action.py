#!/usr/bin/env python3
"""Combat action resolver: roll attack, calculate damage, return round result.

Reads JSON from stdin:
  {"actor": "Hero", "action_type": "attack", "target": "Goblin",
   "weapon": "sword", "attack_bonus": 5, "defense": 12,
   "damage_dice": "1d8+3"}
Writes JSON to stdout:
  {"actor": "Hero", "action_type": "attack", "target": "Goblin",
   "hit": true, "attack_roll": 17, "damage": 8, "damage_roll": "1d8+3",
   "effects": [], "hp_changes": [], "description": "..."}
"""
from __future__ import annotations

import json
import random
import re
import sys

DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$", re.IGNORECASE)


def roll_dice(expr: str) -> tuple[int, list[int], int]:
    """Roll a dice expression, return (total, individual_rolls, modifier)."""
    m = DICE_RE.match(expr.strip())
    if not m:
        return 0, [], 0
    count = min(int(m.group(1)), 100)
    sides = max(int(m.group(2)), 2)
    mod = int(m.group(3)) if m.group(3) else 0
    rolls = [random.randint(1, sides) for _ in range(count)]
    return sum(rolls) + mod, rolls, mod


def resolve_attack(data: dict) -> dict:
    actor = data.get("actor", "unknown")
    target = data.get("target", "unknown")
    attack_bonus = int(data.get("attack_bonus", 0))
    defense = int(data.get("defense", 10))
    damage_dice = data.get("damage_dice", "1d6")
    weapon = data.get("weapon", "")

    attack_natural = random.randint(1, 20)
    attack_total = attack_natural + attack_bonus
    hit = attack_total >= defense

    damage = 0
    damage_detail = ""
    effects = []

    if attack_natural == 20:
        hit = True
        effects.append("暴击")
    elif attack_natural == 1:
        hit = False
        effects.append("失手")

    if hit:
        dmg_total, dmg_rolls, dmg_mod = roll_dice(damage_dice)
        if "暴击" in effects:
            crit_rolls = [random.randint(1, max(int(DICE_RE.match(damage_dice.strip()).group(2)) if DICE_RE.match(damage_dice.strip()) else 6, 2))
                          for _ in dmg_rolls]
            dmg_total += sum(crit_rolls)
            damage_detail = f"{damage_dice} (暴击加骰)"
        else:
            damage_detail = damage_dice
        damage = max(dmg_total, 0)

    weapon_text = f"用{weapon}" if weapon else ""
    if hit:
        desc = f"{actor}{weapon_text}攻击{target}：命中（{attack_natural}+{attack_bonus}={attack_total} vs AC {defense}），造成 {damage} 点伤害"
    else:
        desc = f"{actor}{weapon_text}攻击{target}：未命中（{attack_natural}+{attack_bonus}={attack_total} vs AC {defense}）"

    return {
        "actor": actor,
        "action_type": "attack",
        "target": target,
        "hit": hit,
        "attack_roll": attack_total,
        "damage": damage,
        "damage_roll": damage_detail or damage_dice,
        "effects": effects,
        "hp_changes": [],
        "description": desc,
    }


def resolve_defend(data: dict) -> dict:
    actor = data.get("actor", "unknown")
    target = data.get("target", actor)
    return {
        "actor": actor,
        "action_type": "defend",
        "target": target,
        "hit": False,
        "attack_roll": 0,
        "damage": 0,
        "damage_roll": "",
        "effects": ["防御姿态", "AC+2"],
        "hp_changes": [],
        "description": f"{actor}采取防御姿态，AC 暂时提升 2 点",
    }


def resolve_flee(data: dict) -> dict:
    actor = data.get("actor", "unknown")
    target = data.get("target", "")
    roll = random.randint(1, 20)
    success = roll >= 10
    return {
        "actor": actor,
        "action_type": "flee",
        "target": target,
        "hit": False,
        "attack_roll": roll,
        "damage": 0,
        "damage_roll": "",
        "effects": ["逃跑成功"] if success else ["逃跑失败"],
        "hp_changes": [],
        "description": f"{actor}尝试逃跑（掷出 {roll}）：{'成功脱离战斗' if success else '未能逃脱'}",
    }


def resolve_skill(data: dict) -> dict:
    actor = data.get("actor", "unknown")
    target = data.get("target", "unknown")
    skill_name = data.get("skill", "特殊技能")
    attack_bonus = int(data.get("attack_bonus", 0))
    defense = int(data.get("defense", 10))
    damage_dice = data.get("damage_dice", "1d6")

    roll = random.randint(1, 20)
    total = roll + attack_bonus
    hit = total >= defense

    damage = 0
    if hit:
        damage, _, _ = roll_dice(damage_dice)
        damage = max(damage, 0)

    desc = f"{actor}对{target}使用{skill_name}：{'命中' if hit else '未命中'}（{roll}+{attack_bonus}={total} vs DC {defense}）"
    if hit:
        desc += f"，造成 {damage} 点伤害"

    return {
        "actor": actor,
        "action_type": "skill",
        "target": target,
        "hit": hit,
        "attack_roll": total,
        "damage": damage,
        "damage_roll": damage_dice if hit else "",
        "effects": [skill_name],
        "hp_changes": [],
        "description": desc,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    action_type = data.get("action_type", "attack")
    resolvers = {
        "attack": resolve_attack,
        "defend": resolve_defend,
        "flee": resolve_flee,
        "skill": resolve_skill,
    }
    resolver = resolvers.get(action_type, resolve_attack)
    result = resolver(data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
