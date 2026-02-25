from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from backend.app.db.engine import get_session
from backend.app.models.character import Character
from backend.app.models.session import GameSession

router = APIRouter(prefix="/api", tags=["characters"])


class CharacterUpdate(BaseModel):
    name: str | None = None
    role: str | None = None
    description: str | None = None
    personality: str | None = None
    attributes_json: str | None = None
    inventory_json: str | None = None


def _serialize_character(char: Character) -> dict:
    from backend.app.core.json_utils import safe_json_loads

    d = char.model_dump()
    d["attributes"] = safe_json_loads(char.attributes_json, {}) if char.attributes_json else {}
    d["inventory"] = safe_json_loads(char.inventory_json, []) if char.inventory_json else []
    d.pop("attributes_json", None)
    d.pop("inventory_json", None)
    return d


@router.get("/sessions/{session_id}/characters")
async def list_characters(
    session_id: str,
    session: AsyncSession = Depends(get_session),
):
    game_session = await session.get(GameSession, session_id)
    if not game_session:
        raise HTTPException(status_code=404, detail="Session not found")

    stmt = (
        select(Character)
        .where(Character.session_id == session_id)
        .order_by(Character.created_at.asc())  # type: ignore[arg-type]
    )
    result = await session.exec(stmt)
    return [_serialize_character(c) for c in result.all()]


@router.put("/characters/{character_id}", response_model=Character)
async def update_character(
    character_id: str,
    body: CharacterUpdate,
    session: AsyncSession = Depends(get_session),
):
    character = await session.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="Character not found")

    _MUTABLE_FIELDS = {"name", "role", "description", "personality", "attributes_json", "inventory_json"}
    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        if key in _MUTABLE_FIELDS:
            setattr(character, key, value)

    from datetime import datetime, timezone

    character.updated_at = datetime.now(timezone.utc)
    session.add(character)
    await session.commit()
    await session.refresh(character)
    return character
