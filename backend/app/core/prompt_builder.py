from __future__ import annotations

from dataclasses import dataclass, field

POSITIONS = [
    "system",
    "character",
    "world-state",
    "memory",
    "chat-history",
    "pre-response",
]


@dataclass
class PromptBuilder:
    """Assembles an ordered list of messages for the LLM.

    Injection positions (in order):
        1. system        -- world doc + global plugin instructions
        2. character     -- character definitions / persona
        3. world-state   -- current game state from plugins
        4. memory        -- long/short term memory context
        5. chat-history  -- recent user/assistant messages
        6. pre-response  -- last-minute injections before the model responds

    Call ``inject(position, priority, content)`` to add content.
    Call ``build()`` to produce the final ``[{role, content}]`` list.
    """

    _buckets: dict[str, list[tuple[int, str]]] = field(default_factory=dict)

    def inject(self, position: str, priority: int, content: str) -> None:
        if position not in POSITIONS:
            raise ValueError(f"Invalid position {position!r}. Must be one of {POSITIONS}")
        self._buckets.setdefault(position, []).append((priority, content))

    def build(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []

        # 1-4: combine system / character / world-state / memory into a single
        # system message, each section separated by blank lines.
        system_parts: list[str] = []
        for pos in ("system", "character", "world-state", "memory"):
            items = self._buckets.get(pos, [])
            if items:
                items.sort(key=lambda t: t[0])
                system_parts.extend(text for _, text in items)

        if system_parts:
            messages.append({"role": "system", "content": "\n\n".join(system_parts)})

        # 5: chat-history -- entries are expected to already carry their role
        # encoded as "user: ..." or "assistant: ...", but for simplicity the
        # caller should inject pre-formatted messages.  We insert them as-is
        # sorted by priority (which doubles as chronological order).
        history_items = self._buckets.get("chat-history", [])
        if history_items:
            history_items.sort(key=lambda t: t[0])
            for _, text in history_items:
                # Expect text formatted as "role:content"
                if ":" in text:
                    role, _, content = text.partition(":")
                    role = role.strip().lower()
                    if role in ("user", "assistant", "system"):
                        messages.append({"role": role, "content": content.strip()})
                    else:
                        messages.append({"role": "user", "content": text})
                else:
                    messages.append({"role": "user", "content": text})

        # 6: pre-response -- append as system message(s) right before generation
        pre_items = self._buckets.get("pre-response", [])
        if pre_items:
            pre_items.sort(key=lambda t: t[0])
            pre_text = "\n\n".join(text for _, text in pre_items)
            messages.append({"role": "system", "content": pre_text})

        return messages
