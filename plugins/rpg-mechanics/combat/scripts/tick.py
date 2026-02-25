#!/usr/bin/env python3
"""Status effect tick script: process active effects at turn end.

Reads JSON from stdin:
  {"effects": [{"effect_name": "中毒", "effect_type": "dot", "duration": 3, "damage_per_turn": 5, "target": "玩家"}, ...]}

Writes JSON to stdout:
  {"ticked": [...], "expired": [...], "total_damage": N, "total_healing": N}
"""
from __future__ import annotations

import json
import sys


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    effects = data.get("effects", [])
    ticked = []
    expired = []
    total_damage = 0
    total_healing = 0

    for e in effects:
        name = e.get("effect_name", "unknown")
        etype = e.get("effect_type", "buff")
        duration = e.get("duration", 0)
        dpt = e.get("damage_per_turn", 0)
        hpt = e.get("heal_per_turn", 0)

        remaining = max(0, duration - 1)
        damage_dealt = dpt if etype == "dot" else 0
        healing_dealt = hpt if etype == "hot" else 0

        total_damage += damage_dealt
        total_healing += healing_dealt

        entry = {
            "effect_name": name,
            "remaining_duration": remaining,
        }
        if damage_dealt:
            entry["damage_dealt"] = damage_dealt
        if healing_dealt:
            entry["healing_dealt"] = healing_dealt

        if remaining <= 0:
            expired.append(entry)
        else:
            ticked.append(entry)

    result = {
        "ticked": ticked,
        "expired": expired,
        "total_damage": total_damage,
        "total_healing": total_healing,
    }
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
