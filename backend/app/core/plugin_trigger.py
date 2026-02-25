"""Plugin and block trigger policy helpers."""
from __future__ import annotations

from typing import Any

PLUGIN_TRIGGER_ALWAYS = "always"
PLUGIN_TRIGGER_INTERVAL = "interval"
PLUGIN_TRIGGER_MANUAL = "manual"

KNOWN_PLUGIN_TRIGGER_MODES = {
    PLUGIN_TRIGGER_ALWAYS,
    PLUGIN_TRIGGER_INTERVAL,
    PLUGIN_TRIGGER_MANUAL,
}

BLOCK_TRIGGER_ALWAYS = "always"
BLOCK_TRIGGER_ONCE_PER_SESSION = "once_per_session"

KNOWN_BLOCK_TRIGGER_MODES = {
    BLOCK_TRIGGER_ALWAYS,
    BLOCK_TRIGGER_ONCE_PER_SESSION,
}


def _parse_positive_int(raw: Any, default: int) -> int:
    try:
        value = int(raw)
    except Exception:
        return default
    return value if value > 0 else default


def normalize_plugin_trigger_policy(raw: Any) -> dict[str, Any]:
    """Normalize plugin trigger config into a stable shape."""
    defaults: dict[str, Any] = {
        "mode": PLUGIN_TRIGGER_ALWAYS,
        "interval_turns": 1,
        "mode_setting_key": None,
        "interval_setting_key": None,
        "mode_map": {},
    }
    if not isinstance(raw, dict):
        return dict(defaults)

    mode = str(raw.get("mode") or PLUGIN_TRIGGER_ALWAYS).strip().lower()
    if mode not in KNOWN_PLUGIN_TRIGGER_MODES:
        mode = PLUGIN_TRIGGER_ALWAYS

    interval_turns = _parse_positive_int(raw.get("interval_turns"), 1)

    mode_setting_key = str(raw.get("mode_setting_key") or "").strip() or None
    interval_setting_key = str(raw.get("interval_setting_key") or "").strip() or None

    mode_map: dict[str, str] = {}
    raw_mode_map = raw.get("mode_map")
    if isinstance(raw_mode_map, dict):
        for source, target in raw_mode_map.items():
            source_key = str(source or "").strip().lower()
            target_mode = str(target or "").strip().lower()
            if not source_key or target_mode not in KNOWN_PLUGIN_TRIGGER_MODES:
                continue
            mode_map[source_key] = target_mode

    return {
        "mode": mode,
        "interval_turns": interval_turns,
        "mode_setting_key": mode_setting_key,
        "interval_setting_key": interval_setting_key,
        "mode_map": mode_map,
    }


def validate_plugin_trigger_policy(raw: Any) -> list[str]:
    """Validate plugin trigger config in manifest source shape."""
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return ["trigger must be an object"]

    errors: list[str] = []

    mode = str(raw.get("mode") or PLUGIN_TRIGGER_ALWAYS).strip().lower()
    if mode not in KNOWN_PLUGIN_TRIGGER_MODES:
        errors.append(
            "trigger.mode must be one of: " + ", ".join(sorted(KNOWN_PLUGIN_TRIGGER_MODES))
        )

    if "interval_turns" in raw:
        try:
            interval_turns = int(raw["interval_turns"])
            if interval_turns <= 0:
                errors.append("trigger.interval_turns must be >= 1")
        except Exception:
            errors.append("trigger.interval_turns must be an integer")

    if "mode_setting_key" in raw:
        key = str(raw.get("mode_setting_key") or "").strip()
        if not key:
            errors.append("trigger.mode_setting_key must be a non-empty string")

    if "interval_setting_key" in raw:
        key = str(raw.get("interval_setting_key") or "").strip()
        if not key:
            errors.append("trigger.interval_setting_key must be a non-empty string")

    mode_map = raw.get("mode_map")
    if mode_map is not None:
        if not isinstance(mode_map, dict):
            errors.append("trigger.mode_map must be an object")
        else:
            for source, target in mode_map.items():
                source_key = str(source or "").strip()
                target_mode = str(target or "").strip().lower()
                if not source_key:
                    errors.append("trigger.mode_map keys must be non-empty strings")
                    continue
                if target_mode not in KNOWN_PLUGIN_TRIGGER_MODES:
                    errors.append(
                        "trigger.mode_map values must map to: "
                        + ", ".join(sorted(KNOWN_PLUGIN_TRIGGER_MODES))
                    )
                    break

    return errors


def normalize_block_trigger_policy(raw: Any) -> dict[str, str]:
    """Normalize block trigger config into a stable shape."""
    if not isinstance(raw, dict):
        return {"mode": BLOCK_TRIGGER_ALWAYS}
    mode = str(raw.get("mode") or BLOCK_TRIGGER_ALWAYS).strip().lower()
    if mode not in KNOWN_BLOCK_TRIGGER_MODES:
        mode = BLOCK_TRIGGER_ALWAYS
    return {"mode": mode}


def validate_block_trigger_policy(raw: Any, *, path: str = "trigger") -> list[str]:
    """Validate block-level trigger policy shape."""
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]

    errors: list[str] = []
    mode = str(raw.get("mode") or BLOCK_TRIGGER_ALWAYS).strip().lower()
    if mode not in KNOWN_BLOCK_TRIGGER_MODES:
        errors.append(
            f"{path}.mode must be one of: " + ", ".join(sorted(KNOWN_BLOCK_TRIGGER_MODES))
        )
    return errors
