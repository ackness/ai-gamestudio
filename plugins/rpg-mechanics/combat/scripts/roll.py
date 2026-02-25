#!/usr/bin/env python3
"""Dice roll script: parse dice expressions and return random results.

Reads JSON from stdin: {"expr": "2d6+3"}
Writes JSON to stdout: {"dice": "2d6+3", "result": 11, "detail": [4, 4], "mod": 3, "success": null, "description": "..."}
"""
from __future__ import annotations

import json
import random
import re
import sys

# Dice expression pattern: NdM[+/-K]
DICE_RE = re.compile(r"^(\d+)d(\d+)([+-]\d+)?$", re.IGNORECASE)


def parse_and_roll(expr: str) -> dict:
    """Parse a dice expression like '2d6+3' and roll it."""
    expr = expr.strip()
    m = DICE_RE.match(expr)
    if not m:
        return {
            "dice": expr,
            "result": 0,
            "detail": [],
            "mod": 0,
            "success": None,
            "description": f"Invalid dice expression: {expr}",
        }

    count = int(m.group(1))
    sides = int(m.group(2))
    mod_str = m.group(3)
    mod = int(mod_str) if mod_str else 0

    if count < 1 or count > 100:
        return {
            "dice": expr,
            "result": 0,
            "detail": [],
            "mod": mod,
            "success": None,
            "description": f"Dice count out of range: {count}",
        }
    if sides < 2 or sides > 1000:
        return {
            "dice": expr,
            "result": 0,
            "detail": [],
            "mod": mod,
            "success": None,
            "description": f"Dice sides out of range: {sides}",
        }

    rolls = [random.randint(1, sides) for _ in range(count)]
    total = sum(rolls) + mod

    mod_text = ""
    if mod > 0:
        mod_text = f"+{mod}"
    elif mod < 0:
        mod_text = str(mod)

    roll_text = "+".join(str(r) for r in rolls)
    if mod:
        description = f"Rolled {expr} = {roll_text}{mod_text} = {total}"
    else:
        description = f"Rolled {expr} = {roll_text} = {total}"

    return {
        "dice": expr,
        "result": total,
        "detail": rolls,
        "mod": mod,
        "success": None,
        "description": description,
    }


def main() -> None:
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        print(json.dumps({"error": "Invalid JSON input"}))
        sys.exit(1)

    expr = data.get("expr") or data.get("dice") or "1d20"
    result = parse_and_roll(expr)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
