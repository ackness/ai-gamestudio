"""Novel generation service — collects game material and orchestrates LLM calls."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.core.llm_gateway import completion
from backend.app.models.character import Character
from backend.app.models.game_event import GameEvent
from backend.app.models.message import Message
from backend.app.models.project import Project
from backend.app.models.session import GameSession


@dataclass
class NovelMaterial:
    world_doc: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)
    characters: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class NovelConfig:
    style: str = "轻小说"
    chapter_count: int = 5
    language: str = "zh"


async def collect_novel_material(
    db: AsyncSession, session_id: str
) -> NovelMaterial:
    """Gather all game data needed for novel generation."""
    game_session = await db.get(GameSession, session_id)
    if not game_session:
        raise ValueError(f"Session {session_id} not found")

    project = await db.get(Project, game_session.project_id)
    world_doc = project.world_doc or "" if project else ""

    # Messages
    result = await db.exec(
        select(Message)
        .where(Message.session_id == session_id)
        .where(Message.role.in_(["user", "assistant"]))  # type: ignore[attr-defined]
        .order_by(Message.created_at)  # type: ignore[arg-type]
    )
    messages = [
        {"role": m.role, "content": m.content}
        for m in result.all()
        if m.content and m.content.strip()
    ]

    # Characters
    char_result = await db.exec(
        select(Character).where(Character.session_id == session_id)
    )
    characters = [
        {"name": c.name, "role": c.role, "attributes": c.attributes_json}
        for c in char_result.all()
    ]

    # Events
    event_result = await db.exec(
        select(GameEvent)
        .where(GameEvent.session_id == session_id)
        .order_by(GameEvent.created_at)  # type: ignore[arg-type]
    )
    events = [
        {"type": e.event_type, "name": e.name, "description": e.description, "status": e.status}
        for e in event_result.all()
    ]

    return NovelMaterial(
        world_doc=world_doc,
        messages=messages,
        characters=characters,
        events=events,
    )


def _build_material_text(material: NovelMaterial, max_messages: int = 200) -> str:
    """Serialize material into a compact text block for LLM context."""
    parts: list[str] = []
    if material.world_doc:
        parts.append(f"## 世界设定\n{material.world_doc[:3000]}")
    if material.characters:
        chars = "\n".join(
            f"- {c['name']}（{c['role']}）" for c in material.characters
        )
        parts.append(f"## 角色\n{chars}")
    if material.events:
        evts = "\n".join(
            f"- [{e['status']}] {e['name']}: {e['description']}"
            for e in material.events
        )
        parts.append(f"## 事件\n{evts}")
    if material.messages:
        msgs = material.messages[-max_messages:]
        dialogue = "\n".join(
            f"{'玩家' if m['role'] == 'user' else 'DM'}: {m['content'][:500]}"
            for m in msgs
        )
        parts.append(f"## 对话记录（最近 {len(msgs)} 条）\n{dialogue}")
    return "\n\n".join(parts)


async def generate_outline(
    material: NovelMaterial,
    config: NovelConfig,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> list[dict[str, str]]:
    """Ask LLM to produce a chapter outline from game material."""
    material_text = _build_material_text(material)
    system_prompt = (
        "你是一位专业的小说编辑。根据以下游戏记录，规划一部小说的章节大纲。\n"
        f"要求：{config.chapter_count} 个章节，风格为「{config.style}」，"
        f"语言为 {config.language}。\n"
        "请严格以 JSON 数组格式返回，每个元素包含 title 和 summary 字段。\n"
        "只返回 JSON，不要其他内容。"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": material_text},
    ]
    raw = await completion(
        messages, stream=False, model=model, api_key=api_key, api_base=api_base
    )
    # Parse JSON from response (handle markdown code fences)
    text = raw.strip() if isinstance(raw, str) else ""
    if text.startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
    try:
        outline = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Failed to parse outline JSON, using fallback")
        outline = [{"title": f"第{i+1}章", "summary": ""} for i in range(config.chapter_count)]
    return outline


async def generate_chapter(
    material: NovelMaterial,
    outline: list[dict[str, str]],
    chapter_index: int,
    config: NovelConfig,
    model: str | None = None,
    api_key: str | None = None,
    api_base: str | None = None,
) -> AsyncIterator[str]:
    """Stream-generate a single chapter."""
    material_text = _build_material_text(material)
    outline_text = "\n".join(
        f"{i+1}. {ch['title']}: {ch.get('summary', '')}"
        for i, ch in enumerate(outline)
    )
    chapter = outline[chapter_index]
    system_prompt = (
        "你是一位才华横溢的小说作家。根据游戏素材和大纲，撰写指定章节的正文。\n"
        f"风格：{config.style}，语言：{config.language}。\n"
        "要求：情节连贯，人物鲜活，场景描写生动。直接输出正文，不要标题。"
    )
    user_prompt = (
        f"# 素材\n{material_text}\n\n"
        f"# 大纲\n{outline_text}\n\n"
        f"# 当前任务\n请撰写第 {chapter_index + 1} 章「{chapter['title']}」的正文。\n"
        f"章节摘要：{chapter.get('summary', '无')}"
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
    result = await completion(
        messages, stream=True, model=model, api_key=api_key, api_base=api_base
    )
    async for chunk in result:
        yield chunk
