from __future__ import annotations

from typing import Any

import pytest

import backend.app.services.command_handlers as handlers


class _Sink:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    async def send_json(self, data: dict[str, Any]) -> None:
        self.events.append(data)


@pytest.mark.asyncio
async def test_force_trigger_guide_routes_to_plugin_path(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = _Sink()
    called = {"guide_path": False}

    async def _fake_guide_path(
        sink: Any,
        session_id: str,
        data: dict[str, Any],
        llm_overrides: dict[str, str] | None = None,
    ) -> None:
        called["guide_path"] = True

    async def _fake_stream(*args: Any, **kwargs: Any) -> None:  # noqa: ARG001
        raise AssertionError("guide trigger should not call narrative stream path")

    monkeypatch.setattr(handlers, "_handle_force_trigger_guide_plugin", _fake_guide_path)
    monkeypatch.setattr(handlers, "_stream_process_message", _fake_stream)

    await handlers._handle_force_trigger(
        sink,
        "session-1",
        {"block_type": "guide", "lang": "en"},
    )

    assert called["guide_path"] is True
    assert sink.events == []


@pytest.mark.asyncio
async def test_force_trigger_state_update_keeps_stream_path(monkeypatch: pytest.MonkeyPatch) -> None:
    sink = _Sink()
    captured: dict[str, Any] = {}

    async def _fake_stream(
        sink: Any,
        session_id: str,
        prompt: str,
        *,
        save_user_msg: bool = True,
        save_assistant_msg: bool = True,
        llm_overrides: dict[str, str] | None = None,
        image_overrides: dict[str, str] | None = None,
    ) -> None:
        captured["session_id"] = session_id
        captured["prompt"] = prompt
        captured["save_user_msg"] = save_user_msg
        captured["save_assistant_msg"] = save_assistant_msg
        captured["llm_overrides"] = llm_overrides
        captured["image_overrides"] = image_overrides

    monkeypatch.setattr(handlers, "_stream_process_message", _fake_stream)

    await handlers._handle_force_trigger(
        sink,
        "session-2",
        {"block_type": "state_update"},
        llm_overrides={"model": "test"},
        image_overrides={"model": "image-test"},
    )

    assert captured["session_id"] == "session-2"
    assert captured["save_user_msg"] is False
    assert captured["save_assistant_msg"] is False
    assert "角色状态的变化" in captured["prompt"]
    assert captured["llm_overrides"] == {"model": "test"}
    assert captured["image_overrides"] == {"model": "image-test"}
    assert sink.events == []


@pytest.mark.asyncio
async def test_force_trigger_unknown_type_returns_error() -> None:
    sink = _Sink()

    await handlers._handle_force_trigger(
        sink,
        "session-3",
        {"block_type": "not-exist"},
    )

    assert len(sink.events) == 1
    assert sink.events[0]["type"] == "error"
    assert "Unknown trigger type" in sink.events[0]["content"]
