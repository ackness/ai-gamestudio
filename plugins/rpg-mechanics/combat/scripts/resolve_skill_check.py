#!/usr/bin/env python3
"""Skill check resolver: roll 1d20 + modifiers vs difficulty class.

Reads JSON from stdin:
  {"skill": "stealth", "difficulty": 15, "modifier": 3, "attribute_bonus": 2}
Writes JSON to stdout:
  {"dice": "1d20", "roll": 14, "modifier": 3, "attribute_bonus": 2,
   "total": 19, "difficulty": 15, "success_level": "success",
   "skill": "stealth", "description": "..."}
"""
from __future__ import annotations

import json
import random
import sys


def resolve_check(data: dict) -> dict:
    skill = data.get("skill", "unknown")
    difficulty = int(data.get("difficulty", 10))
    modifier = int(data.get("modifier", 0))
    attribute_bonus = int(data.get("attribute_bonus", 0))

    roll = random.randint(1, 20)
    total = roll + modifier + attribute_bonus

    if roll == 20:
        success_level = "critical_success"
    elif roll == 1:
        success_level = "critical_failure"
    elif total >= difficulty:
        success_level = "success"
    else:
        success_level = "failure"

    level_labels = {
        "critical_success": "大成功",
        "success": "成功",
        "failure": "失败",
        "critical_failure": "大失败",
    }

    calc = str(roll)
    if modifier:
        calc += f" {modifier:+d}".replace("+", "+ ").replace("-", "- ")
    if attribute_bonus:
        calc += f" {attribute_bonus:+d}".replace("+", "+ ").replace("-", "- ")

    description = (
        f"{skill} 检定：掷出 {calc} = {total} vs DC {difficulty}，"
        f"{level_labels[success_level]}！"
    )

    return {
        "dice": "1d20",
        "roll": roll,
        "modifier": modifier,
        "attribute_bonus": attribute_bonus,
        "total": total,
        "difficulty": difficulty,
        "success_level": success_level,
        "skill": skill,
        "description": description,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    result = resolve_check(data)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
