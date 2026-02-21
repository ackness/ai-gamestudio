"""Novel generation API — streams chapter-by-chapter novel from game session."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.services.novel_service import (
    NovelConfig,
    collect_novel_material,
    generate_chapter,
    generate_outline,
)

router = APIRouter(prefix="/api/sessions", tags=["novel"])


class GenerateNovelRequest(BaseModel):
    style: str | None = None
    chapter_count: int | None = None
    language: str | None = None


@router.post("/{session_id}/novel/generate")
async def generate_novel(
    session_id: str,
    body: GenerateNovelRequest,
    db: AsyncSession = Depends(get_session),
    x_llm_model: str | None = Header(default=None),
    x_llm_api_key: str | None = Header(default=None),
    x_llm_api_base: str | None = Header(default=None),
):
    """Stream-generate a novel from game session data (JSON Lines)."""
    try:
        material = await collect_novel_material(db, session_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    if not material.messages:
        raise HTTPException(status_code=400, detail="Session has no messages")

    config = NovelConfig(
        style=body.style or "轻小说",
        chapter_count=body.chapter_count or 5,
        language=body.language or "zh",
    )
    llm_kwargs = dict(model=x_llm_model, api_key=x_llm_api_key, api_base=x_llm_api_base)

    async def _stream():
        # Phase 1: generate outline
        try:
            outline = await generate_outline(material, config, **llm_kwargs)
        except Exception:
            logger.exception("Novel outline generation failed")
            yield json.dumps({"type": "error", "message": "大纲生成失败"}, ensure_ascii=False) + "\n"
            return

        yield json.dumps(
            {"type": "outline", "chapters": outline}, ensure_ascii=False
        ) + "\n"

        # Phase 2: generate each chapter
        for idx, chapter in enumerate(outline):
            content_parts: list[str] = []
            try:
                async for chunk in generate_chapter(
                    material, outline, idx, config, **llm_kwargs
                ):
                    content_parts.append(chunk)
                    yield json.dumps(
                        {"type": "chapter_chunk", "index": idx, "text": chunk},
                        ensure_ascii=False,
                    ) + "\n"
            except Exception:
                logger.exception(f"Chapter {idx} generation failed")
                yield json.dumps(
                    {"type": "error", "message": f"第{idx+1}章生成失败"},
                    ensure_ascii=False,
                ) + "\n"
                continue

            yield json.dumps(
                {
                    "type": "chapter",
                    "index": idx,
                    "title": chapter["title"],
                    "content": "".join(content_parts),
                },
                ensure_ascii=False,
            ) + "\n"

        yield json.dumps({"type": "done"}, ensure_ascii=False) + "\n"

    return StreamingResponse(_stream(), media_type="application/x-ndjson")
