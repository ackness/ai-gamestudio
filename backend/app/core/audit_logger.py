"""AuditLogger: JSON-lines audit trail for plugin capability invocations.

Appends structured entries to daily files in data/audit/.
"""
from __future__ import annotations

import json
import pathlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from loguru import logger

_DEFAULT_AUDIT_DIR = "data/audit"


@dataclass
class AuditEntry:
    invocation_id: str
    plugin: str
    capability: str
    script: str
    args: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 0
    duration_ms: int = 0
    stdout: str = ""
    stderr: str = ""
    timestamp: str = ""

    def __post_init__(self) -> None:
        if not self.timestamp:
            self.timestamp = datetime.now(timezone.utc).isoformat()


class AuditLogger:
    """Append-only JSON-lines logger for plugin invocations."""

    def __init__(self, audit_dir: str | None = None) -> None:
        self._audit_dir = pathlib.Path(audit_dir or _DEFAULT_AUDIT_DIR)

    def _ensure_dir(self) -> None:
        self._audit_dir.mkdir(parents=True, exist_ok=True)

    def _daily_file(self) -> pathlib.Path:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        return self._audit_dir / f"audit_{today}.jsonl"

    def log(self, entry: AuditEntry) -> None:
        """Append an audit entry to today's log file."""
        try:
            self._ensure_dir()
            line = json.dumps(asdict(entry), ensure_ascii=False) + "\n"
            with open(self._daily_file(), "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            logger.warning("Failed to write audit entry for {}.{}", entry.plugin, entry.capability)

    def query(
        self,
        *,
        plugin: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Read recent audit entries, optionally filtered by plugin name."""
        entries: list[dict[str, Any]] = []

        if not self._audit_dir.is_dir():
            return entries

        # Read files in reverse chronological order
        files = sorted(self._audit_dir.glob("audit_*.jsonl"), reverse=True)
        for f in files:
            if len(entries) >= limit:
                break
            try:
                lines = f.read_text(encoding="utf-8").strip().split("\n")
                for line in reversed(lines):
                    if len(entries) >= limit:
                        break
                    if not line.strip():
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if plugin and entry.get("plugin") != plugin:
                        continue
                    entries.append(entry)
            except OSError:
                continue

        return entries
