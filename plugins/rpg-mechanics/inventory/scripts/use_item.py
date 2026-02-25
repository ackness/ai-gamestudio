#!/usr/bin/env python3
"""Use item script: calculate consumable/equipment effects.

Reads JSON from stdin:
  {"item_name": "Health Potion", "item_type": "consumable",
   "stats": {"hp": 20}, "character_hp": 45, "character_max_hp": 100}

Writes JSON to stdout:
  {"item_name": "Health Potion", "effect_description": "恢复 20 点生命值",
   "stat_changes": {"hp": {"before": 45, "after": 65, "change": 20}},
   "consumed": true}
"""
from __future__ import annotations

import json
import sys


def calculate_effect(data: dict) -> dict:
    """Calculate the effect of using an item."""
    item_name = data.get("item_name", "Unknown Item")
    item_type = data.get("item_type", "misc")
    stats = data.get("stats") or {}
    character_hp = data.get("character_hp", 100)
    character_max_hp = data.get("character_max_hp", 100)

    stat_changes = {}
    effects = []

    # Process HP effect
    if "hp" in stats:
        hp_delta = stats["hp"]
        new_hp = min(character_hp + hp_delta, character_max_hp)
        actual_change = new_hp - character_hp
        stat_changes["hp"] = {
            "before": character_hp,
            "after": new_hp,
            "change": actual_change,
        }
        if actual_change > 0:
            effects.append(f"恢复 {actual_change} 点生命值")
        elif actual_change < 0:
            effects.append(f"失去 {abs(actual_change)} 点生命值")

    # Process other stat effects
    for stat, value in stats.items():
        if stat == "hp":
            continue
        stat_changes[stat] = {"change": value}
        if value > 0:
            effects.append(f"{stat} +{value}")
        elif value < 0:
            effects.append(f"{stat} {value}")

    consumed = item_type == "consumable"
    effect_desc = "，".join(effects) if effects else "无明显效果"

    return {
        "item_name": item_name,
        "effect_description": effect_desc,
        "stat_changes": stat_changes,
        "consumed": consumed,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    result = calculate_effect(data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
